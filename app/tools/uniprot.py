"""UniProt REST API client.

Free, keyless search/retrieval against https://rest.uniprot.org. This
replaces the legacy Elasticsearch + OpenAI text-embedding index entirely -
UniProt is treated as the source of truth for "what proteins exist and
what do they do", not a private re-embedded copy of it.

Confirmed response shapes (verified against the live API):

    GET /uniprotkb/search?query=...&fields=...&format=json&size=N
        -> {"results": [ {entry}, {entry}, ... ]}

    GET /uniprotkb/{accession}.json?fields=...
        -> {entry}   (a single entry object, not wrapped in "results")

Each `entry` looks like:
    {
      "entryType": "UniProtKB reviewed (Swiss-Prot)",
      "primaryAccession": "P01308",
      "organism": {"scientificName": "Homo sapiens", ...},
      "proteinDescription": {"recommendedName": {"fullName": {"value": "Insulin"}}},
      "genes": [{"geneName": {"value": "INS"}, ...}],
      "comments": [{"commentType": "FUNCTION", "texts": [{"value": "..."}]}],
      "features": [{"type": "Domain", "description": "...", "location": {...}}],
      "uniProtKBCrossReferences": [{"database": "GO", "id": "GO:...", ...}],
      "sequence": {"value": "...", "length": 110, ...}
    }
"""

from typing import Any, Dict, List, Optional

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt

from app.config import config

DEFAULT_FIELDS = (
    "accession,id,protein_name,gene_names,organism_name,organism_id,"
    "length,sequence,cc_function,cc_subcellular_location,go,cc_disease,ft_domain"
)
REQUEST_TIMEOUT_SECONDS = 30.0
# Safety net independent of prompt-level guidance: caps how many full protein
# records (each including a full sequence) can be pulled into the agent's
# context in one search_uniprot call, regardless of what size the LLM asks for.
MAX_RESULT_SIZE = 20

# Keep agent/API payloads compact when UniProt returns huge annotation lists.
MAX_GENE_NAMES = 5
MAX_SUBCELLULAR_LOCATIONS = 8
MAX_GO_TERMS = 10
MAX_DISEASES = 5
MAX_DOMAINS = 8


class UniProtResponseError(Exception):
    """Raised when UniProt returns a response that doesn't match the expected shape."""


class UniProtRateLimitError(Exception):
    """Internal signal used to trigger a single retry on HTTP 429."""

    def __init__(self, retry_after_seconds: float):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"UniProt rate limited; retry after {retry_after_seconds}s")


def _wait_retry_after(retry_state) -> float:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, UniProtRateLimitError):
        return exc.retry_after_seconds
    return 1.0


def build_query(
    text: Optional[str] = None,
    query: Optional[str] = None,
    reviewed: bool = True,
    organism_id: Optional[str] = None,
) -> str:
    """Build a UniProt Lucene-style query from plain text or a raw query fragment."""
    if not text and not query:
        raise ValueError("Either 'text' or 'query' must be provided")

    parts: List[str] = []
    if query:
        parts.append(f"({query})")
    else:
        parts.append(f"({text})")

    if reviewed:
        parts.append("(reviewed:true)")

    if organism_id:
        parts.append(f"(organism_id:{organism_id})")

    return " AND ".join(parts)


def _first_function_comment(entry: Dict[str, Any]) -> Optional[str]:
    for comment in entry.get("comments", []) or []:
        if comment.get("commentType") == "FUNCTION":
            texts = comment.get("texts") or []
            if texts:
                return texts[0].get("value")
    return None


def _parse_gene_names(entry: Dict[str, Any]) -> List[str]:
    names: List[str] = []
    seen: set = set()
    for gene in entry.get("genes") or []:
        for key in ("geneName",):
            value = ((gene.get(key) or {}).get("value") or "").strip()
            if value and value not in seen:
                seen.add(value)
                names.append(value)
        for synonym in gene.get("synonyms") or []:
            value = (synonym.get("value") or "").strip()
            if value and value not in seen:
                seen.add(value)
                names.append(value)
        if len(names) >= MAX_GENE_NAMES:
            break
    return names[:MAX_GENE_NAMES]


def _parse_subcellular_locations(entry: Dict[str, Any]) -> List[str]:
    locations: List[str] = []
    seen: set = set()
    for comment in entry.get("comments") or []:
        if comment.get("commentType") != "SUBCELLULAR LOCATION":
            continue
        for item in comment.get("subcellularLocations") or []:
            value = ((item.get("location") or {}).get("value") or "").strip()
            if value and value not in seen:
                seen.add(value)
                locations.append(value)
            if len(locations) >= MAX_SUBCELLULAR_LOCATIONS:
                return locations
    return locations


def _go_term_label(xref: Dict[str, Any]) -> Optional[str]:
    go_id = (xref.get("id") or "").strip()
    term = None
    for prop in xref.get("properties") or []:
        if prop.get("key") == "GoTerm":
            term = (prop.get("value") or "").strip() or None
            break
    if go_id and term:
        # UniProt GoTerm often looks like "C:centrosome" — keep as-is.
        return f"{go_id} {term}"
    if go_id:
        return go_id
    return term


def _parse_go_terms(entry: Dict[str, Any]) -> List[str]:
    terms: List[str] = []
    seen: set = set()
    for xref in entry.get("uniProtKBCrossReferences") or []:
        if xref.get("database") != "GO":
            continue
        label = _go_term_label(xref)
        if not label or label in seen:
            continue
        seen.add(label)
        terms.append(label)
        if len(terms) >= MAX_GO_TERMS:
            break
    return terms


def _parse_diseases(entry: Dict[str, Any]) -> List[str]:
    diseases: List[str] = []
    seen: set = set()
    for comment in entry.get("comments") or []:
        if comment.get("commentType") != "DISEASE":
            continue
        disease = comment.get("disease") or {}
        name = (disease.get("diseaseId") or "").strip()
        if not name:
            texts = (comment.get("note") or {}).get("texts") or []
            if texts:
                name = (texts[0].get("value") or "").strip()
                if len(name) > 160:
                    name = name[:157] + "..."
        if name and name not in seen:
            seen.add(name)
            diseases.append(name)
        if len(diseases) >= MAX_DISEASES:
            break
    return diseases


def _parse_domains(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    domains: List[Dict[str, Any]] = []
    for feature in entry.get("features") or []:
        if feature.get("type") != "Domain":
            continue
        location = feature.get("location") or {}
        start = (location.get("start") or {}).get("value")
        end = (location.get("end") or {}).get("value")
        name = (feature.get("description") or "").strip() or "Domain"
        domains.append(
            {
                "name": name,
                "start": int(start) if start is not None else None,
                "end": int(end) if end is not None else None,
            }
        )
        if len(domains) >= MAX_DOMAINS:
            break
    return domains


def _parse_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    protein_description = entry.get("proteinDescription", {}) or {}
    recommended_name = protein_description.get("recommendedName", {}) or {}
    full_name = recommended_name.get("fullName", {}) or {}

    organism = entry.get("organism", {}) or {}
    sequence = entry.get("sequence", {}) or {}
    entry_type = entry.get("entryType", "") or ""

    taxon_id = organism.get("taxonId")
    gene_names = _parse_gene_names(entry)
    subcellular_locations = _parse_subcellular_locations(entry)
    go_terms = _parse_go_terms(entry)
    diseases = _parse_diseases(entry)
    domains = _parse_domains(entry)

    return {
        "accession": entry.get("primaryAccession"),
        "protein_name": full_name.get("value"),
        "gene_names": gene_names or None,
        "organism": organism.get("scientificName"),
        "organism_id": str(taxon_id) if taxon_id is not None else None,
        "length": sequence.get("length"),
        "sequence": sequence.get("value"),
        "function": _first_function_comment(entry),
        "subcellular_locations": subcellular_locations or None,
        "go_terms": go_terms or None,
        "diseases": diseases or None,
        "domains": domains or None,
        "reviewed": entry_type.startswith("UniProtKB reviewed"),
    }


@retry(
    stop=stop_after_attempt(2),
    wait=_wait_retry_after,
    retry=retry_if_exception_type(UniProtRateLimitError),
    reraise=True,
)
async def _get_json(client: httpx.AsyncClient, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    response = await client.get(url, params=params)
    if response.status_code == 429:
        retry_after = float(response.headers.get("Retry-After", "1"))
        raise UniProtRateLimitError(retry_after)
    response.raise_for_status()
    return response.json()


async def search_uniprot(
    text: Optional[str] = None,
    query: Optional[str] = None,
    size: Optional[int] = None,
    reviewed: bool = True,
    organism_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search UniProtKB and return a list of parsed protein records.

    Provide either `text` (plain-language keywords) or `query` (a raw
    UniProt Lucene query fragment) - not both. Defaults to Swiss-Prot only
    (`reviewed=True`) so results aren't drowned in unreviewed TrEMBL entries.
    `size` is clamped to `MAX_RESULT_SIZE` regardless of what's requested.
    """
    effective_size = size if size is not None else config.default_result_size
    effective_size = max(1, min(effective_size, MAX_RESULT_SIZE))
    final_query = build_query(text=text, query=query, reviewed=reviewed, organism_id=organism_id)

    params = {
        "query": final_query,
        "fields": DEFAULT_FIELDS,
        "format": "json",
        "size": effective_size,
    }

    async with httpx.AsyncClient(
        base_url=config.uniprot_base_url, timeout=REQUEST_TIMEOUT_SECONDS
    ) as client:
        data = await _get_json(client, "/uniprotkb/search", params)

    if "results" not in data:
        raise UniProtResponseError(
            "Malformed UniProt search response: missing 'results' key"
        )

    return [_parse_entry(entry) for entry in data["results"]]


async def get_uniprot_entry(accession: str) -> Dict[str, Any]:
    """Fetch a single UniProtKB entry by accession."""
    params = {"fields": DEFAULT_FIELDS}

    async with httpx.AsyncClient(
        base_url=config.uniprot_base_url, timeout=REQUEST_TIMEOUT_SECONDS
    ) as client:
        data = await _get_json(client, f"/uniprotkb/{accession}.json", params)

    if "primaryAccession" not in data:
        raise UniProtResponseError(
            f"Malformed UniProt entry response for accession '{accession}': "
            "missing 'primaryAccession' key"
        )

    return _parse_entry(data)
