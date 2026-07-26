"""Deterministic candidate/retrieved-protein assembly from the tool trace.

This module never looks at the agent's natural-language reply. It only
looks at `app/agent/graph.py`'s `trace` list - the raw Python return values
of every `search_uniprot` / `get_uniprot_entry` / `propose_variants` /
`fold_sequence` / `score_variant` call made during the turn - so the
`retrieved_proteins` and `candidates` fields in the API response are always
schema-correct regardless of what the model says.

Matching between a proposed candidate sequence and its `fold_sequence` /
`score_variant` result is done by exact sequence-string equality, since the
agent always folds/scores the literal sequence text `propose_variants`
returned.
"""

from typing import Any, Dict, List, Optional

from app.models import Candidate, ParentInfo, ProteinHit, StructureInfo
from app.tools.identity import compute_identity


def _collect_retrieved_proteins(trace: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flatten every search_uniprot/get_uniprot_entry result, deduplicated by
    accession (first occurrence wins), preserving call order."""
    seen_accessions: set = set()
    proteins: List[Dict[str, Any]] = []

    for entry in trace:
        if entry["tool"] == "search_uniprot":
            hits = entry["result"] or []
        elif entry["tool"] == "get_uniprot_entry":
            hits = [entry["result"]] if entry["result"] else []
        else:
            continue

        for hit in hits:
            accession = hit.get("accession")
            if accession and accession in seen_accessions:
                continue
            if accession:
                seen_accessions.add(accession)
            proteins.append(hit)

    return proteins


def _find_parent_metadata(
    parent_sequence: str, retrieved_proteins: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    for protein in retrieved_proteins:
        if protein.get("sequence") == parent_sequence:
            return protein
    return None


def _find_by_sequence(
    trace: List[Dict[str, Any]], tool_name: str, sequence: str
) -> Optional[Dict[str, Any]]:
    for entry in trace:
        if entry["tool"] == tool_name and entry["args"].get("sequence") == sequence:
            return entry["result"]
    return None


def _build_structure_info(fold_result: Optional[Dict[str, Any]]) -> StructureInfo:
    if not fold_result:
        return StructureInfo(available=False)

    return StructureInfo(
        available=bool(fold_result.get("structure_available")),
        mean_plddt=fold_result.get("mean_plddt"),
        model_source=fold_result.get("model_source"),
        structure_id=fold_result.get("structure_id"),
    )


def _build_llm_proposed_candidates(
    trace: List[Dict[str, Any]], retrieved_proteins: List[Dict[str, Any]]
) -> List[Candidate]:
    candidates: List[Candidate] = []

    for entry in trace:
        if entry["tool"] != "propose_variants":
            continue

        parent_sequence = entry["args"].get("parent_sequence", "")
        parent_name = entry["args"].get("parent_name")
        parent_meta = _find_parent_metadata(parent_sequence, retrieved_proteins)

        for proposal in entry["result"] or []:
            sequence = proposal.get("sequence", "")
            warnings: List[str] = []

            if parent_meta is None:
                warnings.append("parent_sequence_not_found_in_retrieved_proteins")

            parent_info = ParentInfo(
                accession=parent_meta.get("accession") if parent_meta else None,
                protein_name=(parent_meta.get("protein_name") if parent_meta else parent_name),
                organism=parent_meta.get("organism") if parent_meta else None,
                sequence=parent_sequence,
            )

            identity_to_parent = (
                compute_identity(parent_sequence, sequence) if parent_sequence and sequence else None
            )

            fold_result = _find_by_sequence(trace, "fold_sequence", sequence)
            score_result = _find_by_sequence(trace, "score_variant", sequence)

            if fold_result is None:
                warnings.append("fold_failed_or_skipped")
            elif not fold_result.get("structure_available"):
                warnings.append("fold_failed_or_skipped")

            candidates.append(
                Candidate(
                    sequence=sequence,
                    origin="llm_proposed",
                    parent=parent_info,
                    identity_to_parent=identity_to_parent,
                    method="llm_propose",
                    model_version=proposal.get("model_version"),
                    structure=_build_structure_info(fold_result),
                    esm1v_score=(score_result or {}).get("score"),
                    warnings=warnings,
                    modifications=proposal.get("modifications") or [],
                    explanation=proposal.get("explanation") or None,
                )
            )

    return candidates


def assemble_response(
    trace: List[Dict[str, Any]],
) -> tuple[List[ProteinHit], List[Candidate]]:
    """Build the schema-conformant retrieved_proteins and candidates lists
    from a single agent turn's tool-call trace."""
    retrieved_raw = _collect_retrieved_proteins(trace)
    retrieved_proteins = [ProteinHit(**protein) for protein in retrieved_raw]

    candidates = _build_llm_proposed_candidates(trace, retrieved_raw)

    return retrieved_proteins, candidates


def summarize_trace(trace: List[Dict[str, Any]]) -> List[str]:
    """Human-readable one-line-per-call summary of the tool trace, useful for
    debugging/transparency in the API response (`tool_trace_summary`)."""
    lines: List[str] = []

    for entry in trace:
        tool_name = entry["tool"]
        args = entry["args"]
        result = entry["result"]

        if tool_name == "search_uniprot":
            lines.append(f"search_uniprot(text={args.get('text')!r}) -> {len(result or [])} hit(s)")
        elif tool_name == "get_uniprot_entry":
            found = "found" if result else "not found"
            lines.append(f"get_uniprot_entry({args.get('accession')!r}) -> {found}")
        elif tool_name == "propose_variants":
            lines.append(
                f"propose_variants(parent={args.get('parent_name')!r}, n={args.get('n')}) "
                f"-> {len(result or [])} candidate(s)"
            )
        elif tool_name == "fold_sequence":
            plddt = (result or {}).get("mean_plddt")
            available = (result or {}).get("structure_available")
            lines.append(f"fold_sequence(name={args.get('name')!r}) -> available={available}, mean_plddt={plddt}")
        elif tool_name == "score_variant":
            score = (result or {}).get("score")
            lines.append(f"score_variant(...) -> score={score}")
        else:
            lines.append(f"{tool_name}(...)")

    return lines
