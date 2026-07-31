"""UniProt ID Mapping client (external IDs → UniProtKB accessions).

Async job API against https://rest.uniprot.org/idmapping:
  POST /run → poll /status/{jobId} → GET /uniprotkb/results/{jobId}

MVP maps **to UniProtKB only**. When the UniProtKB results endpoint returns
full entries in `to`, we parse them in-process (no per-id GET). String-only
`to` values fall back to `get_uniprot_entry` (soft-fail per id).

The LLM chooses `from_db` from a whitelist enum — no code auto-detect.
Optional `organism_id` is sent as UniProt `taxId` on submit (important for
Gene_Name) and re-checked after parse.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Literal, Optional, Sequence

import httpx

from app.config import config
from app.tools.uniprot import UniProtResponseError, _parse_entry, get_uniprot_entry

logger = logging.getLogger(__name__)

FromDb = Literal[
    "Gene_Name",
    "Ensembl_Protein",
    "RefSeq_Protein",
    "PDB",
    "UniProtKB_AC-ID",
]

ALLOWED_FROM_DB: tuple[str, ...] = (
    "Gene_Name",
    "Ensembl_Protein",
    "RefSeq_Protein",
    "PDB",
    "UniProtKB_AC-ID",
)

TO_DB = "UniProtKB"
MAX_IDS = 20
POLL_INTERVAL_SECONDS = 2.0
JOB_TIMEOUT_SECONDS = 60.0
HTTP_TIMEOUT_SECONDS = 60.0

RETRIEVAL_METHOD = "uniprot_idmapping"


class IdMappingError(Exception):
    """Raised when the ID Mapping job fails or times out."""


def _normalize_ids(ids: Sequence[str]) -> List[str]:
    cleaned: List[str] = []
    seen: set[str] = set()
    for raw in ids:
        value = (raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        cleaned.append(value)
        if len(cleaned) >= MAX_IDS:
            break
    return cleaned


def _extract_accession(to_value: Any) -> Optional[str]:
    if isinstance(to_value, str) and to_value.strip():
        # UniProt entries sometimes return "P01308" or "P01308|INS_HUMAN"
        return to_value.split("|")[0].strip()
    if isinstance(to_value, dict):
        acc = to_value.get("primaryAccession") or to_value.get("uniProtkbId")
        if isinstance(acc, str) and acc.strip():
            return acc.split("|")[0].strip()
    return None


async def _submit_job(
    client: httpx.AsyncClient,
    from_db: str,
    ids: List[str],
    tax_id: Optional[str] = None,
) -> str:
    payload: Dict[str, str] = {
        "from": from_db,
        "to": TO_DB,
        "ids": ",".join(ids),
    }
    if tax_id:
        payload["taxId"] = str(tax_id)
    response = await client.post("/idmapping/run", data=payload)
    if response.status_code == 429:
        raise IdMappingError("UniProt ID Mapping rate limited (429)")
    response.raise_for_status()
    data = response.json()
    job_id = data.get("jobId")
    if not job_id:
        raise IdMappingError(f"ID Mapping submit missing jobId: {data}")
    return str(job_id)


async def _wait_for_job(client: httpx.AsyncClient, job_id: str) -> None:
    deadline = time.monotonic() + JOB_TIMEOUT_SECONDS
    while True:
        if time.monotonic() > deadline:
            raise IdMappingError(
                f"ID Mapping job {job_id} timed out after {JOB_TIMEOUT_SECONDS:.0f}s"
            )
        # UniProt returns 303 → results URL when the job is done; do not follow.
        response = await client.get(
            f"/idmapping/status/{job_id}", follow_redirects=False
        )
        if response.status_code in (303, 302):
            return
        response.raise_for_status()
        data = response.json()

        # Finished payloads sometimes embed results / failedIds directly.
        if "results" in data or "failedIds" in data:
            return

        status = data.get("jobStatus")
        if status == "FINISHED":
            return
        if status in ("ERROR", "FAILED", "NOT_FOUND"):
            raise IdMappingError(f"ID Mapping job {job_id} failed: {data}")
        if status == "RUNNING":
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            continue
        # Unknown shape — brief wait and retry until timeout.
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _fetch_results(
    client: httpx.AsyncClient, job_id: str
) -> Dict[str, Any]:
    # When to=UniProtKB, the dedicated uniprotkb results endpoint is preferred.
    for path in (
        f"/idmapping/uniprotkb/results/{job_id}",
        f"/idmapping/results/{job_id}",
    ):
        response = await client.get(path, params={"size": MAX_IDS})
        if response.status_code == 404:
            continue
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            return data
    raise IdMappingError(f"No results endpoint available for job {job_id}")


async def run_id_mapping(
    ids: Sequence[str],
    from_db: str,
    tax_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run ID Mapping to UniProtKB. Returns raw mappings + failed ids.

    Each mapping is ``{"from", "to", "entry"}`` where ``entry`` is a parsed
    UniProt record when the results payload embedded a full ``to`` object,
    otherwise ``None`` (caller should fetch).
    """
    if from_db not in ALLOWED_FROM_DB:
        raise ValueError(
            f"Unsupported from_db={from_db!r}. Allowed: {list(ALLOWED_FROM_DB)}"
        )
    normalized = _normalize_ids(ids)
    if not normalized:
        raise ValueError("At least one non-empty id is required")

    async with httpx.AsyncClient(
        base_url=config.uniprot_base_url, timeout=HTTP_TIMEOUT_SECONDS
    ) as client:
        try:
            job_id = await _submit_job(
                client, from_db, normalized, tax_id=tax_id
            )
            await _wait_for_job(client, job_id)
            data = await _fetch_results(client, job_id)
        except httpx.HTTPError as exc:
            raise IdMappingError(f"ID Mapping HTTP error: {exc}") from exc

    mappings: List[Dict[str, Any]] = []
    mapped_from: set[str] = set()
    for row in data.get("results") or []:
        src = str(row.get("from") or "").strip()
        to_value = row.get("to")
        acc = _extract_accession(to_value)
        if not src or not acc:
            continue
        entry = _parse_entry(to_value) if isinstance(to_value, dict) else None
        mappings.append({"from": src, "to": acc, "entry": entry})
        mapped_from.add(src)

    failed = list(data.get("failedIds") or [])
    for src in normalized:
        if src not in mapped_from and src not in failed:
            failed.append(src)

    return {
        "job_id": job_id,
        "from_db": from_db,
        "mappings": mappings,
        "failed_ids": failed,
    }


async def map_to_uniprot(
    ids: Sequence[str],
    from_db: str,
    organism_id: Optional[str] = None,
    reviewed: bool = True,
) -> Dict[str, Any]:
    """Map ids → UniProtKB, enrich hits, soft-skip misses / filters.

    By default keeps Swiss-Prot only (`reviewed=True`), matching
    `search_uniprot`. Set ``reviewed=False`` to also keep TrEMBL.

    Returns:
        {
          "proteins": [...],
          "mappings": [{"from","to"}, ...],
          "failed_ids": [...],
          "skipped_accessions": [{"accession","reason"}, ...],
        }
    """
    raw = await run_id_mapping(ids, from_db, tax_id=organism_id)
    proteins: List[Dict[str, Any]] = []
    skipped: List[Dict[str, str]] = []
    seen_accessions: set[str] = set()

    for mapping in raw["mappings"]:
        accession = mapping["to"]
        if accession in seen_accessions:
            continue
        seen_accessions.add(accession)

        entry = mapping.get("entry")
        if entry is None:
            try:
                entry = await get_uniprot_entry(accession)
            except (UniProtResponseError, httpx.HTTPError, Exception) as exc:
                logger.warning("UniProt enrich failed for %s: %s", accession, exc)
                skipped.append({"accession": accession, "reason": "uniprot_miss"})
                continue

        if organism_id:
            entry_tax = entry.get("organism_id")
            if entry_tax is not None and str(entry_tax) != str(organism_id):
                skipped.append(
                    {
                        "accession": accession,
                        "reason": f"organism_mismatch:{entry_tax}",
                    }
                )
                continue

        if reviewed and not entry.get("reviewed"):
            skipped.append({"accession": accession, "reason": "unreviewed"})
            continue

        protein = dict(entry)
        protein.update(
            {
                "retrieval_method": RETRIEVAL_METHOD,
                "mapped_from": mapping["from"],
                "mapped_from_db": from_db,
            }
        )
        proteins.append(protein)

    public_mappings = [
        {"from": m["from"], "to": m["to"]} for m in raw["mappings"]
    ]
    return {
        "proteins": proteins,
        "mappings": public_mappings,
        "failed_ids": raw["failed_ids"],
        "skipped_accessions": skipped,
        "from_db": from_db,
        "job_id": raw.get("job_id"),
    }
