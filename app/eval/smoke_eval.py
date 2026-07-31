"""ProtDAP smoke eval: 5 fixed end-to-end cases exercising the real ReAct
agent loop (real OpenRouter LLM calls - this is an integration smoke test,
not an offline unit test; see app/tools/test_uniprot.py for that).

EVAL_LIVE=0 (default): UniProt search/entry and BioLM fold/score calls are
replaced with recorded fixtures from app/eval/fixtures/, so only the LLM
call itself needs network + OPENROUTER_API_KEY. This keeps the eval fast,
free of UniProt/BioLM rate limits, and independent of BioLM credentials.

EVAL_LIVE=1: UniProt and BioLM calls hit the real APIs (needs a valid
BIOLMAI_TOKEN and Node/npx installed).

Run with:  python -m app.eval.smoke_eval
Exits 0 if all cases pass, 1 otherwise (also prints a pass/fail table).
"""

import asyncio
import re
import sys
from dataclasses import dataclass, field
from typing import List

import httpx
import respx

import app.agent.graph as graph_module
from app.agent.assembler import assemble_response
from app.config import config
from app.eval import FIXTURES_DIR
from app.structure_cache import store_structure
from app.tools import biolm_mcp as biolm_module
from app.tools.uniprot import UniProtResponseError, _parse_entry, search_uniprot

SEQUENCE_PATTERN = re.compile(r"^[ACDEFGHIKLMNPQRSTVWY]+$")
FORBIDDEN_PHRASES = [
    "guaranteed to function",
    "proven to function",
    "confirmed to function",
    "guarantees function",
    "proven function",
]


@dataclass
class CaseResult:
    name: str
    passed: bool
    details: List[str] = field(default_factory=list)


def _load_json_fixture(name: str):
    import json

    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


def _install_fixture_mocks() -> None:
    """Monkeypatch UniProt + BioLM calls used by the agent's tools with
    recorded fixtures, so cases 1-4 don't need live UniProt/BioLM access."""
    immune_raw = _load_json_fixture("uniprot_search_human_immune.json")["results"]
    small_raw = _load_json_fixture("uniprot_search_small_human_protein.json")["results"]
    esmfold_fixture = _load_json_fixture("biolm_esmfold_sample.json")

    parsed_immune = [_parse_entry(e) for e in immune_raw]
    parsed_small = [_parse_entry(e) for e in small_raw]
    all_parsed = parsed_immune + parsed_small

    async def fake_search_uniprot(text=None, query=None, size=None, reviewed=True, organism_id=None):
        effective_size = size if size is not None else config.default_result_size
        haystack = f"{text or ''} {query or ''}".lower()
        if "small" in haystack or "insulin" in haystack or "stable" in haystack:
            return parsed_small[:effective_size]
        return parsed_immune[:effective_size]

    async def fake_get_uniprot_entry(accession):
        for entry in all_parsed:
            if entry["accession"] == accession:
                return entry
        raise LookupError(f"No fixture entry for accession {accession!r}")

    async def fake_fold_sequence(self, sequence, name):
        structure_id = store_structure(esmfold_fixture["pdb"], name_hint=name)
        return {
            "structure_available": True,
            "model_source": "BioLM ESMFold (fixture)",
            "mean_plddt": esmfold_fixture["mean_plddt"],
            "structure_id": structure_id,
        }

    async def fake_score_variant(self, sequence):
        return {"score": None}

    graph_module.search_uniprot = fake_search_uniprot
    graph_module.get_uniprot_entry = fake_get_uniprot_entry
    biolm_module.BioLMMCPClient.fold_sequence = fake_fold_sequence
    biolm_module.BioLMMCPClient.score_variant = fake_score_variant


async def run_case_1_search_only() -> CaseResult:
    """Case 1: pure search request -> retrieved hits, no candidates."""
    from app.agent.graph import run_agent

    _, trace = await run_agent("Find human proteins involved in immune response.")
    retrieved, candidates, _ = assemble_response(trace)
    tool_names = {entry["tool"] for entry in trace}

    details = [
        f"retrieved_proteins: {len(retrieved)}",
        f"candidates: {len(candidates)}",
        f"tools called: {sorted(tool_names)}",
    ]
    passed = len(retrieved) >= 1 and len(candidates) == 0 and "propose_variants" not in tool_names
    return CaseResult("1. search-only returns hits, no candidates", passed, details)


async def run_case_2_and_3_diversify() -> List[CaseResult]:
    """Case 2: diversify request -> schema-conformant llm_proposed candidates.
    Case 3: at least one candidate was folded (or clearly warned), and the
    reply never claims proven function."""
    from app.agent.graph import run_agent

    reply, trace = await run_agent(
        "Find a small human protein and propose 3 more stable variants of it."
    )
    retrieved, candidates, _ = assemble_response(trace)
    propose_calls = [entry for entry in trace if entry["tool"] == "propose_variants"]

    case2_details = [
        f"retrieved_proteins: {len(retrieved)}",
        f"candidates: {len(candidates)}",
        f"propose_variants calls: {len(propose_calls)}",
    ]
    case2_passed = bool(propose_calls) and 0 < len(candidates) <= 5
    for candidate in candidates:
        if candidate.origin != "llm_proposed":
            case2_passed = False
            case2_details.append(f"unexpected origin: {candidate.origin}")
        if candidate.parent is None:
            case2_passed = False
            case2_details.append("candidate missing parent")
        if candidate.identity_to_parent is None or not (0 < candidate.identity_to_parent <= 1.0):
            case2_passed = False
            case2_details.append(f"identity_to_parent out of range: {candidate.identity_to_parent}")
        if not SEQUENCE_PATTERN.match(candidate.sequence or ""):
            case2_passed = False
            case2_details.append(f"invalid sequence alphabet: {candidate.sequence!r}")
    case2 = CaseResult("2. diversify returns valid llm_proposed candidates", case2_passed, case2_details)

    any_folded = any(
        c.structure.available and c.structure.mean_plddt is not None for c in candidates
    )
    any_warned = any("fold_failed_or_skipped" in c.warnings for c in candidates)
    forbidden_hit = next((p for p in FORBIDDEN_PHRASES if p in reply.lower()), None)

    case3_details = [
        f"any_folded: {any_folded}",
        f"any_warned_if_not_folded: {any_warned}",
        f"forbidden phrase found: {forbidden_hit!r}",
    ]
    case3_passed = (any_folded or any_warned) and forbidden_hit is None
    case3 = CaseResult("3. fold step reported/warned, no proven-function claim", case3_passed, case3_details)

    return [case2, case3]


async def run_case_4_default_result_size() -> CaseResult:
    """Case 4: an unqualified search returns more than a single hit."""
    from app.agent.graph import run_agent

    _, trace = await run_agent("Find proteins involved in immune response.")
    retrieved, _, _ = assemble_response(trace)

    details = [f"retrieved_proteins: {len(retrieved)}", f"DEFAULT_RESULT_SIZE: {config.default_result_size}"]
    passed = len(retrieved) > 1
    return CaseResult("4. default (unqualified) search returns >1 hit", passed, details)


async def run_case_5_uniprot_429_retry() -> CaseResult:
    """Case 5: a mocked 429-then-200 sequence results in a successful retry,
    not a failure. This exercises app/tools/uniprot.py directly (no agent)."""
    success_body = _load_json_fixture("uniprot_search_minimal.json")
    host = httpx.URL(config.uniprot_base_url).host

    details = []
    try:
        with respx.mock:
            route = respx.get(host=host, path="/uniprotkb/search")
            route.side_effect = [
                httpx.Response(429, headers={"Retry-After": "0"}),
                httpx.Response(200, json=success_body),
            ]
            hits = await search_uniprot(text="insulin", organism_id="9606")
        details.append(f"call_count: {route.call_count}")
        details.append(f"hits: {len(hits)}")
        passed = route.call_count == 2 and len(hits) == 1
    except UniProtResponseError as exc:
        details.append(f"unexpected error: {exc}")
        passed = False

    return CaseResult("5. UniProt 429 triggers exactly one retry, then succeeds", passed, details)


async def _run_safely(name: str, coro) -> List[CaseResult]:
    """Run a case coroutine (which may return one or more CaseResults) and
    turn any raised exception into a failed CaseResult instead of crashing
    the whole eval run - e.g. a missing/invalid API key should show up as a
    clear FAIL row, not an unhandled traceback."""
    try:
        result = await coro
    except Exception as exc:  # noqa: BLE001 - eval script must never crash
        return [CaseResult(name, False, [f"raised {type(exc).__name__}: {exc}"])]
    return result if isinstance(result, list) else [result]


def _print_report(results: List[CaseResult]) -> None:
    print()
    print(f"{'STATUS':<8} CASE")
    print("-" * 78)
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"{status:<8} {result.name}")
        for detail in result.details:
            print(f"         - {detail}")
    print("-" * 78)
    passed_count = sum(1 for r in results if r.passed)
    print(f"{passed_count}/{len(results)} cases passed"
          f" (mode: {'LIVE' if config.eval_live else 'FIXTURE'})")
    print()


async def main() -> int:
    config.validate()

    if not config.eval_live:
        _install_fixture_mocks()

    results: List[CaseResult] = []
    results.extend(await _run_safely("1. search-only returns hits, no candidates", run_case_1_search_only()))
    results.extend(await _run_safely("2/3. diversify + fold", run_case_2_and_3_diversify()))
    results.extend(await _run_safely("4. default result size", run_case_4_default_result_size()))
    results.extend(await _run_safely("5. UniProt 429 retry", run_case_5_uniprot_429_retry()))

    _print_report(results)

    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
