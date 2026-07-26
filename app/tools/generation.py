"""LLM-based sequence proposal tool (v1 generation backend).

This is explicitly NOT protein design in the ProteinMPNN/RFdiffusion sense.
It is a targeted LLM call that proposes candidate amino-acid sequences
based on a parent sequence and an instruction. Every output is labeled
`origin="llm_proposed"` and must never be presented as a validated or
functionally-proven design - see the "Future work" note in ARCHITECTURE.md
for the planned ProteinMPNN-based upgrade path.

This tool makes its own dedicated LLM call (via the same OpenRouter model
used by the ReAct agent) with a narrow system prompt, rather than letting
the agent's main reasoning turn improvise a sequence inline as free text.
"""

import json
import re
from typing import Any, Dict, List

from langchain_openai import ChatOpenAI

from app.config import config

VALID_AMINO_ACIDS = set("ACDEFGHIKLMNPQRSTVWY")
MAX_CANDIDATES = 5

_SYSTEM_PROMPT = """You are a protein-sequence proposal assistant.

You will be given a parent protein sequence and an instruction describing
a desired change. Propose amino-acid sequence variants that follow the
instruction as best as possible.

Hard rules:
1. Every proposed sequence MUST use ONLY the standard 20 amino-acid
   one-letter codes: ACDEFGHIKLMNPQRSTVWY. No other characters, no gaps,
   no whitespace, no numbers.
2. Do NOT claim the sequence is guaranteed to work, is experimentally
   validated, or has any proven function. These are computational
   proposals only.
3. Prefer targeted, explainable changes over wholesale rewrites unless the
   instruction explicitly asks for something very different.
4. Return ONLY a JSON object (no markdown fences, no extra prose) with this
   exact shape:
   {
     "candidates": [
       {
         "modifications": [
           {
             "context_before": "GERG",
             "original": "F",
             "new": "Y",
             "context_after": "FYTP",
             "reason": "..."
           }
         ],
         "explanation": "short rationale"
       }
     ]
   }
5. Do NOT count or guess a numeric position for a modification - counting
   character positions in a long sequence is unreliable. Instead, locate
   each mutated residue by exact surrounding context: `context_before`
   (3-6 residues immediately before it) and `context_after` (3-6 residues
   immediately after it), both copied VERBATIM from the parent sequence
   you were given, plus the single `original` residue between them.
   `context_before` + `original` + `context_after` concatenated MUST
   appear in the parent sequence, and only once - if that exact context
   could match more than one place, use longer or more distinctive
   context. The final candidate sequence is constructed in code from these
   exact matches, not from anything else you write.
6. Every candidate MUST be unique (a different set of modifications /
   resulting sequence than every other candidate), and every candidate
   must have at least one modification that actually changes the parent
   sequence - never propose a "variant" identical to the parent.
"""


def _clean_sequence(raw_sequence: str) -> str:
    return "".join(ch for ch in raw_sequence.upper() if ch in VALID_AMINO_ACIDS)


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    # Strip markdown code fences if the model added them despite instructions.
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    return json.loads(text)


def _find_all(haystack: str, needle: str) -> List[int]:
    """All (possibly overlapping) start indices where `needle` occurs in
    `haystack`."""
    if not needle:
        return []
    positions = []
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx == -1:
            break
        positions.append(idx)
        start = idx + 1
    return positions


def _apply_modifications(
    parent_sequence: str, modifications: List[Dict[str, Any]]
) -> "tuple[str, List[Dict[str, Any]]]":
    """Deterministically construct a candidate sequence by applying each
    claimed (context_before, original, new, context_after) substitution to
    the parent sequence in code, instead of trusting the LLM's own
    "sequence" field or a numeric position it claims.

    LLMs are unreliable at counting exact character positions in a long
    string, which in practice caused frequent silent mismatches (a claimed
    "original" residue not matching the real parent at that "position").
    Exact-text pattern matching is something LLMs are comparatively good
    at, so each modification is instead located by its exact flanking
    context: `context_before + original + context_after` must occur in the
    parent sequence exactly once. All lookups are done against the
    original, unmodified parent sequence (matching what the model actually
    saw), then applied together.

    A modification is skipped entirely (not the whole candidate) if it's
    malformed, or its context+original pattern doesn't match exactly one
    place in the parent - the remaining valid modifications for that
    candidate still apply.

    Returns (constructed_sequence, applied_modifications). Only
    modifications that actually passed validation and were applied appear
    in `applied_modifications`, each annotated with a `position` (1-indexed)
    computed from where its context matched - never taken from the LLM
    directly, so it's always consistent with the real returned sequence.
    """
    haystack = parent_sequence.upper()
    residues = list(parent_sequence)
    applied: List[Dict[str, Any]] = []
    for mod in modifications if isinstance(modifications, list) else []:
        if not isinstance(mod, dict):
            continue
        original = mod.get("original")
        new = mod.get("new")
        context_before = mod.get("context_before", "")
        context_after = mod.get("context_after", "")
        reason = mod.get("reason")
        if not isinstance(original, str) or not isinstance(new, str):
            continue
        if not isinstance(context_before, str):
            context_before = ""
        if not isinstance(context_after, str):
            context_after = ""
        if len(original) != 1 or len(new) != 1 or new.upper() not in VALID_AMINO_ACIDS:
            continue

        pattern = (context_before + original + context_after).upper()
        occurrences = _find_all(haystack, pattern)
        if len(occurrences) != 1:
            continue  # not found, or ambiguous (multiple matches) - skip

        residue_index = occurrences[0] + len(context_before)
        residues[residue_index] = new.upper()
        applied.append(
            {
                "position": residue_index + 1,
                "original": original.upper(),
                "new": new.upper(),
                "context_before": context_before.upper() or None,
                "context_after": context_after.upper() or None,
                "reason": reason if isinstance(reason, str) else None,
            }
        )
    return "".join(residues), applied


async def propose_variants(
    parent_sequence: str,
    parent_name: str,
    instruction: str,
    n: int = 3,
) -> List[Dict[str, Any]]:
    """Propose up to `n` LLM-generated sequence variants of a parent protein.

    Returns a list of dicts, each already carrying the fixed provenance
    fields (`origin`, `method`, `model_version`) required by the candidate
    schema. `identity_to_parent` and `structure` are NOT set here - those
    are filled in later by the deterministic assembler.
    """
    n = max(1, min(n, MAX_CANDIDATES))

    llm = ChatOpenAI(
        model=config.openrouter_model,
        api_key=config.openrouter_api_key,
        base_url=config.openrouter_base_url,
        temperature=0.7,
    )

    user_prompt = f"""Parent protein: {parent_name}
Parent sequence:
{parent_sequence}

Instruction: {instruction}

Propose exactly {n} candidate sequence(s) following the required JSON format.
For each modification, copy `context_before`/`context_after` VERBATIM from
the parent sequence above (do not paraphrase or guess) so that
`context_before` + `original` + `context_after` matches exactly one place
in it - this exact match is how the real candidate sequence will be
constructed, not anything else you write."""

    response = await llm.ainvoke(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
    )

    raw_content = response.content if isinstance(response.content, str) else str(response.content)

    try:
        parsed = _extract_json(raw_content)
        raw_candidates = parsed.get("candidates", [])
    except (json.JSONDecodeError, AttributeError):
        raw_candidates = []

    cleaned_parent_sequence = _clean_sequence(parent_sequence)
    seen_sequences = set()
    candidates: List[Dict[str, Any]] = []
    for raw_candidate in raw_candidates[:n]:
        modifications = raw_candidate.get("modifications", [])
        if not isinstance(modifications, list):
            modifications = []

        # The candidate's sequence is constructed here from `modifications`,
        # not read from the LLM's own "sequence" field - see
        # _apply_modifications for why.
        constructed_sequence, applied_modifications = _apply_modifications(parent_sequence, modifications)
        cleaned_sequence = _clean_sequence(constructed_sequence)

        if len(cleaned_sequence) < 10:
            continue

        # Reject exact duplicates (within this batch) and no-op "variants"
        # that are identical to the parent - the LLM occasionally repeats
        # itself, proposes zero changes, or lists modifications that fail
        # validation in _apply_modifications and so have no real effect.
        if cleaned_sequence in seen_sequences or cleaned_sequence == cleaned_parent_sequence:
            continue
        seen_sequences.add(cleaned_sequence)

        candidates.append(
            {
                "sequence": cleaned_sequence,
                "modifications": applied_modifications,
                "explanation": raw_candidate.get("explanation", ""),
                "origin": "llm_proposed",
                "method": "llm_propose",
                "model_version": config.openrouter_model,
            }
        )

    return candidates
