#!/usr/bin/env python3
"""20-case flow test: ProTrek text→seq + UniProt enrich (ProtDAP search_protrek).

Requires:
  - ProTrek FastAPI running (default http://127.0.0.1:8090)
  - PROTREK_BASE_URL set (or defaults below)
  - Network access to UniProt

Usage (from ProtDAP root, any env with httpx + app on PYTHONPATH):
  cd ProtDAP
  PROTREK_BASE_URL=http://127.0.0.1:8090 \\
    /home/asus/miniconda3/envs/protrek/bin/python -m app.eval.protrek_flow_eval

Or with ProtDAP venv if present.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path

# ProtDAP root on path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("PROTREK_BASE_URL", "http://127.0.0.1:8090")

# Avoid config.validate requiring LLM keys for this script
os.environ.setdefault("OPENROUTER_API_KEY", os.environ.get("OPENROUTER_API_KEY", "eval-dummy"))
os.environ.setdefault("BIOLMAI_TOKEN", os.environ.get("BIOLMAI_TOKEN", "eval-dummy"))

from app.tools.protrek import (  # noqa: E402
    ProTrekConfigError,
    ProTrekRequestError,
    search_protrek,
)

CASES = [
    "small human cytokine involved in inflammation",
    "insulin receptor tyrosine kinase",
    "hemoglobin oxygen transport",
    "DNA polymerase processivity clamp",
    "ribosomal protein large subunit",
    "serine protease digestive enzyme",
    "G-protein coupled receptor rhodopsin-like",
    "heat shock protein molecular chaperone",
    "cytochrome c electron transfer",
    "antibody immunoglobulin constant domain",
    "zinc finger transcription factor DNA binding",
    "ATP synthase proton channel",
    "collagen extracellular matrix structural",
    "kinase involved in cell cycle regulation",
    "ion channel voltage-gated sodium",
    "ubiquitin conjugating enzyme",
    "lysosomal hydrolase glycosidase",
    "membrane transporter ABC family",
    "antioxidant enzyme superoxide dismutase",
    "peptide hormone involved in glucose homeostasis",
]


async def run_case(description: str, k: int = 5) -> dict:
    try:
        bundle = await search_protrek(description=description, k=k, organism_id=None)
    except (ProTrekConfigError, ProTrekRequestError) as exc:
        return {"description": description, "ok": False, "error": str(exc)}

    proteins = bundle.get("proteins") or []
    skipped = bundle.get("skipped_accessions") or []
    organisms = [p.get("organism") or "?" for p in proteins]
    human = sum(1 for p in proteins if p.get("organism_id") == "9606")
    return {
        "description": description,
        "ok": len(proteins) > 0,
        "protrek_hit_count": bundle.get("protrek_hit_count"),
        "enriched": len(proteins),
        "skipped": len(skipped),
        "skipped_detail": skipped,
        "human_9606": human,
        "organisms": organisms,
        "top": [
            {
                "accession": p.get("accession"),
                "name": p.get("protein_name"),
                "organism": p.get("organism"),
                "organism_id": p.get("organism_id"),
                "score": p.get("score"),
            }
            for p in proteins[:3]
        ],
    }


async def main() -> int:
    print(f"PROTREK_BASE_URL={os.environ.get('PROTREK_BASE_URL')}")
    print(f"Running {len(CASES)} cases (k=5, no organism filter)…\n")

    results = []
    for i, desc in enumerate(CASES, 1):
        print(f"[{i:02d}/20] {desc[:60]}…", flush=True)
        result = await run_case(desc, k=5)
        results.append(result)
        if not result.get("ok"):
            print(f"       FAIL: {result.get('error')}")
        else:
            print(
                f"       enriched={result['enriched']} skipped={result['skipped']} "
                f"human={result['human_9606']} top={result['top'][0]['accession'] if result['top'] else None}"
            )

    ok_n = sum(1 for r in results if r.get("ok"))
    org_counter: Counter = Counter()
    for r in results:
        for o in r.get("organisms") or []:
            org_counter[o] += 1

    print("\n======== SUMMARY ========")
    print(f"cases_ok={ok_n}/{len(CASES)}")
    print(f"organism_counts (top 15): {org_counter.most_common(15)}")
    human_hits = sum(r.get("human_9606") or 0 for r in results)
    total_enriched = sum(r.get("enriched") or 0 for r in results)
    print(f"human_9606_hits={human_hits}/{total_enriched} enriched proteins")
    print(
        "NOTE: Swiss-Prot ProTrek index is multi-organism. "
        "Do NOT assume Homo sapiens; use organism_id='9606' post-filter when needed."
    )

    out = ROOT / "app" / "eval" / "protrek_flow_eval_last.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {out}")

    return 0 if ok_n == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
