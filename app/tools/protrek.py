"""ProTrek semantic search client for ProtDAP (text → sequence MVP).

Calls the local ProTrek FastAPI service, then hydrates every hit via
`get_uniprot_entry`. Soft-fails per accession if UniProt misses it.

The Swiss-Prot FAISS index is **multi-organism** (not human-only). Optional
`organism_id` post-filters after enrichment (e.g. "9606" for Homo sapiens).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from app.config import config
from app.tools.uniprot import UniProtResponseError, get_uniprot_entry

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 120.0
MAX_K = 20


class ProTrekConfigError(Exception):
    """Raised when PROTREK_BASE_URL is not configured."""


class ProTrekRequestError(Exception):
    """Raised when the ProTrek HTTP service fails."""


def _clamp_k(k: Optional[int]) -> int:
    default = config.default_result_size
    value = default if k is None else int(k)
    return max(1, min(value, MAX_K))


async def _search_raw(description: str, k: int) -> List[Dict[str, Any]]:
    base = (config.protrek_base_url or "").rstrip("/")
    if not base:
        raise ProTrekConfigError(
            "PROTREK_BASE_URL is not set. Start the ProTrek service and set "
            "PROTREK_BASE_URL=http://127.0.0.1:8090 in .env"
        )

    payload = {
        "input": description,
        "input_type": "text",
        "query_type": "sequence",
        "topk": k,
        "nprobe": 1,
        "exclude_self": True,
    }

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(f"{base}/search", json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        raise ProTrekRequestError(f"ProTrek /search failed: {exc}") from exc

    hits = data.get("hits")
    if not isinstance(hits, list):
        raise ProTrekRequestError("ProTrek /search returned no hits list")
    return hits


async def search_protrek(
    description: str,
    k: Optional[int] = None,
    organism_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Text→sequence ProTrek search + UniProt enrichment for all hits.

    Returns:
        {
          "proteins": [ProteinHit-like dicts + score + retrieval_method],
          "skipped_accessions": [...],
          "protrek_hit_count": int,
        }
    """
    effective_k = _clamp_k(k)
    raw_hits = await _search_raw(description, effective_k)

    proteins: List[Dict[str, Any]] = []
    skipped: List[Dict[str, str]] = []

    for hit in raw_hits:
        accession = hit.get("id")
        score = hit.get("score")
        if not accession:
            skipped.append({"accession": "", "reason": "missing_id"})
            continue
        try:
            entry = await get_uniprot_entry(str(accession))
        except (UniProtResponseError, httpx.HTTPError, Exception) as exc:
            logger.warning("UniProt enrich failed for %s: %s", accession, exc)
            skipped.append({"accession": str(accession), "reason": "uniprot_miss"})
            continue

        if organism_id:
            entry_tax = entry.get("organism_id")
            if entry_tax is not None and str(entry_tax) != str(organism_id):
                skipped.append(
                    {
                        "accession": str(accession),
                        "reason": f"organism_mismatch:{entry_tax}",
                    }
                )
                continue

        # Preserve all parsed UniProt fields; overlay ProTrek provenance.
        protein = dict(entry)
        protein["score"] = float(score) if score is not None else None
        protein["retrieval_method"] = "protrek_text"
        proteins.append(protein)

    return {
        "proteins": proteins,
        "skipped_accessions": skipped,
        "protrek_hit_count": len(raw_hits),
    }
