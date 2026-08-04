"""Builds and runs the ProtDAP ReAct agent.

Reliability design: rather than trying to reconstruct structured results by
re-parsing LangGraph's serialized `ToolMessage` content (which is meant for
the LLM to read, not for a program to parse), each tool wrapper here
records its raw Python return value into a `trace` list that is private to
this one request. `app/agent/assembler.py` then builds `retrieved_proteins`
and `candidates` purely from that trace - the LLM's prose never becomes
structured data.
"""

import json
import logging
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import httpx
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from app.agent.assembler import summarize_trace
from app.agent.prompts import MAX_TOOL_ITERATIONS, SYSTEM_PROMPT
from app.config import config
from app.tools.biolm_mcp import get_biolm_client
from app.tools.generation import propose_variants
from app.tools.protrek import search_protrek
from app.tools.uniprot import (
    UniProtRateLimitError,
    UniProtResponseError,
    get_uniprot_entry,
    search_uniprot,
)
from app.tools.uniprot_idmapping import ALLOWED_FROM_DB, IdMappingError, map_to_uniprot

TraceEntry = Dict[str, Any]

logger = logging.getLogger("protdap.agent")

# Sequence fields are long and noisy in logs; keep length only.
_SEQUENCE_ARG_KEYS = frozenset({"sequence", "parent_sequence"})

# Network / UniProt API failures: return JSON to the LLM instead of 500'ing /chat.
_UNIPROT_SOFT_FAIL = (
    IdMappingError,
    UniProtResponseError,
    UniProtRateLimitError,
    httpx.TimeoutException,
    httpx.HTTPError,
)

# LangGraph counts each node execution (agent, tools, structured response) as
# one recursion step. Cap generously above the intended iteration count so
# hitting the limit is always a real runaway loop, not a normal multi-tool turn.
RECURSION_LIMIT = 2 * MAX_TOOL_ITERATIONS + 8

# create_react_agent graph node that owns the ReAct LLM (not tools / nested LLMs).
_AGENT_NODE = "agent"

# LangChain @tool names are the wrapper function names (*_tool); map to UI status.
_TOOL_STATUS_MESSAGES: Dict[str, str] = {
    "search_uniprot_tool": "Searching UniProt…",
    "get_uniprot_entry_tool": "Fetching UniProt entry…",
    "map_to_uniprot_tool": "Mapping identifiers to UniProt…",
    "search_protrek_tool": "Searching ProTrek…",
    "propose_variants_tool": "Proposing sequence variants…",
    "fold_sequence_tool": "Folding sequence…",
    "score_variant_tool": "Scoring variant…",
    "recommend_proteins_tool": "Selecting recommended proteins…",
}


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _sanitize_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """Copy tool args for logging; replace raw sequences with length markers."""
    out: Dict[str, Any] = {}
    for key, value in args.items():
        if key in _SEQUENCE_ARG_KEYS and isinstance(value, str):
            out[key] = f"<seq len={len(value)}>"
        else:
            out[key] = value
    return out


def _record_tool(
    trace: List[TraceEntry],
    entry: TraceEntry,
    session_id: Optional[str],
    *,
    duration_ms: Optional[int] = None,
) -> None:
    """Append to the request trace; INFO summary + DEBUG sanitized args."""
    trace.append(entry)
    summary = summarize_trace([entry])[0]
    sid = session_id or "-"
    if duration_ms is None:
        logger.info("session=%s %s", sid, summary)
    else:
        logger.info("session=%s duration_ms=%s %s", sid, duration_ms, summary)
    logger.debug(
        "session=%s tool=%s args=%s result=%s",
        sid,
        entry.get("tool"),
        _sanitize_args(entry.get("args") or {}),
        summary,
    )


def _log_tool_error(
    session_id: Optional[str],
    tool_name: str,
    args: Dict[str, Any],
    exc: BaseException,
) -> None:
    logger.error(
        "session=%s tool=%s args=%s failed: %s",
        session_id or "-",
        tool_name,
        _sanitize_args(args),
        exc,
        exc_info=True,
    )


def _format_soft_error(exc: BaseException) -> str:
    message = str(exc).strip()
    name = type(exc).__name__
    return f"{name}: {message}" if message else name


def _soft_fail_uniprot(
    trace: List[TraceEntry],
    session_id: Optional[str],
    tool_name: str,
    args: Dict[str, Any],
    exc: BaseException,
    *,
    empty_result: Any,
    llm_payload: Dict[str, Any],
    extra_meta: Optional[Dict[str, Any]] = None,
    duration_ms: Optional[int] = None,
) -> str:
    """Log, record empty/error trace entry, return JSON for the LLM (no raise)."""
    _log_tool_error(session_id, tool_name, args, exc)
    error = _format_soft_error(exc)
    meta = {"error": error}
    if extra_meta:
        meta.update(extra_meta)
    _record_tool(
        trace,
        {
            "tool": tool_name,
            "args": args,
            "result": empty_result,
            "meta": meta,
        },
        session_id,
        duration_ms=duration_ms,
    )
    payload = dict(llm_payload)
    payload["error"] = error
    return json.dumps(payload)


def _build_tools(
    trace: List[TraceEntry], session_id: Optional[str] = None
):
    biolm_client = get_biolm_client(config.biolm_token)

    @tool
    async def search_uniprot_tool(
        text: str,
        size: Optional[int] = None,
        reviewed: bool = True,
        organism_id: Optional[str] = None,
    ) -> str:
        """Search UniProtKB for real, existing proteins matching plain-text
        keywords (e.g. 'human proteins involved in immune response'). Do not
        pass UniProt Lucene operators or field:value clauses in text — use
        organism_id for taxonomy filters instead. Returns a JSON list of hits
        with accession, protein_name, gene_names, organism, length, sequence,
        function, subcellular_locations, go_terms, diseases, domains."""
        args = {
            "text": text,
            "size": size,
            "reviewed": reviewed,
            "organism_id": organism_id,
        }
        started = time.perf_counter()
        try:
            result = await search_uniprot(
                text=text, size=size, reviewed=reviewed, organism_id=organism_id
            )
        except _UNIPROT_SOFT_FAIL as exc:
            return _soft_fail_uniprot(
                trace,
                session_id,
                "search_uniprot",
                args,
                exc,
                empty_result=[],
                llm_payload={"results": []},
                duration_ms=_elapsed_ms(started),
            )
        _record_tool(
            trace,
            {"tool": "search_uniprot", "args": args, "result": result},
            session_id,
            duration_ms=_elapsed_ms(started),
        )
        return json.dumps(result)

    @tool
    async def get_uniprot_entry_tool(accession: str) -> str:
        """Fetch one specific UniProtKB entry by accession (e.g. 'P01308')."""
        args = {"accession": accession}
        started = time.perf_counter()
        try:
            result = await get_uniprot_entry(accession)
        except _UNIPROT_SOFT_FAIL as exc:
            return _soft_fail_uniprot(
                trace,
                session_id,
                "get_uniprot_entry",
                args,
                exc,
                empty_result=None,
                llm_payload={"accession": accession},
                duration_ms=_elapsed_ms(started),
            )
        _record_tool(
            trace,
            {"tool": "get_uniprot_entry", "args": args, "result": result},
            session_id,
            duration_ms=_elapsed_ms(started),
        )
        return json.dumps(result)

    @tool
    async def map_to_uniprot_tool(
        ids: List[str],
        from_db: str,
        organism_id: Optional[str] = None,
        reviewed: bool = True,
    ) -> str:
        """Map external identifiers / gene symbols to UniProtKB and return
        enriched protein records. Use when the user gives clear IDs such as
        gene symbols (INS, BRCA1), Ensembl protein IDs (ENSP...), RefSeq
        (NP_...), PDB ids (4HHB), or UniProt accessions to resolve — NOT for
        free-text descriptions (use search_uniprot / search_protrek instead).

        from_db MUST be one of: Gene_Name, Ensembl_Protein, RefSeq_Protein,
        PDB, UniProtKB_AC-ID. If unsure which from_db applies, ask the user
        instead of guessing. Optional organism_id (e.g. '9606') filters by
        taxonomy. Defaults to Swiss-Prot only (reviewed=True)."""
        args = {
            "ids": ids,
            "from_db": from_db,
            "organism_id": organism_id,
            "reviewed": reviewed,
        }
        if from_db not in ALLOWED_FROM_DB:
            raise ValueError(
                f"from_db must be one of {list(ALLOWED_FROM_DB)}, got {from_db!r}"
            )
        started = time.perf_counter()
        try:
            bundle = await map_to_uniprot(
                ids=ids,
                from_db=from_db,
                organism_id=organism_id,
                reviewed=reviewed,
            )
        except _UNIPROT_SOFT_FAIL as exc:
            return _soft_fail_uniprot(
                trace,
                session_id,
                "map_to_uniprot",
                args,
                exc,
                empty_result=[],
                llm_payload={
                    "proteins": [],
                    "mappings": [],
                    "failed_ids": list(ids or []),
                    "skipped_accessions": [],
                },
                extra_meta={
                    "mappings": [],
                    "failed_ids": list(ids or []),
                    "skipped_accessions": [],
                },
                duration_ms=_elapsed_ms(started),
            )
        proteins = bundle.get("proteins") or []
        _record_tool(
            trace,
            {
                "tool": "map_to_uniprot",
                "args": args,
                "result": proteins,
                "meta": {
                    "mappings": bundle.get("mappings") or [],
                    "failed_ids": bundle.get("failed_ids") or [],
                    "skipped_accessions": bundle.get("skipped_accessions") or [],
                },
            },
            session_id,
            duration_ms=_elapsed_ms(started),
        )
        return json.dumps(bundle)

    @tool
    async def search_protrek_tool(
        description: str,
        k: Optional[int] = None,
        organism_id: Optional[str] = None,
    ) -> str:
        """Semantic text→protein search via local ProTrek (Swiss-Prot FAISS).
        Use for vague functional descriptions (e.g. 'small cytokine involved
        in inflammation') when UniProt keyword search is a poor fit.
        Returns enriched UniProt protein records plus ProTrek similarity
        scores. Optional organism_id (e.g. '9606') post-filters after enrich —
        the ProTrek index is multi-organism, not human-only."""
        args = {
            "description": description,
            "k": k,
            "organism_id": organism_id,
        }
        started = time.perf_counter()
        try:
            bundle = await search_protrek(
                description=description, k=k, organism_id=organism_id
            )
        except Exception as exc:
            _log_tool_error(session_id, "search_protrek", args, exc)
            raise
        proteins = bundle.get("proteins") or []
        _record_tool(
            trace,
            {
                "tool": "search_protrek",
                "args": args,
                "result": proteins,
                "meta": {
                    "skipped_accessions": bundle.get("skipped_accessions") or [],
                    "protrek_hit_count": bundle.get("protrek_hit_count"),
                },
            },
            session_id,
            duration_ms=_elapsed_ms(started),
        )
        return json.dumps(bundle)

    @tool
    async def propose_variants_tool(
        parent_sequence: str,
        parent_name: str,
        instruction: str,
        n: int = 3,
    ) -> str:
        """Generate up to n LLM-proposed sequence variants of a parent protein
        according to `instruction` (e.g. 'increase thermal stability'). These
        are computational proposals only, never validated designs.

        Every returned candidate is automatically folded with BioLM ESMFold
        right here in code (not left to a separate fold_sequence call from
        you) - each candidate's `fold_result` is included below. This
        guarantees pLDDT is always attributed to the exact candidate it was
        computed for, so do NOT call fold_sequence again for these
        sequences. Only call fold_sequence yourself for a different
        sequence not returned here (e.g. the parent, for comparison)."""
        args = {
            "parent_sequence": parent_sequence,
            "parent_name": parent_name,
            "instruction": instruction,
            "n": n,
        }
        started = time.perf_counter()
        try:
            candidates = await propose_variants(
                parent_sequence=parent_sequence,
                parent_name=parent_name,
                instruction=instruction,
                n=n,
            )
        except Exception as exc:
            _log_tool_error(session_id, "propose_variants", args, exc)
            raise
        _record_tool(
            trace,
            {"tool": "propose_variants", "args": args, "result": candidates},
            session_id,
            duration_ms=_elapsed_ms(started),
        )

        # Fold every candidate deterministically here, using the exact
        # sequence string propose_variants returned - never a sequence the
        # LLM retypes/copies into a separate tool call - so the assembler's
        # exact-string match against this trace entry can never miss or
        # mismatch. See app/tools/biolm_mcp.py for why these run one at a
        # time (serialized) rather than concurrently.
        for index, candidate in enumerate(candidates, start=1):
            sequence = candidate.get("sequence", "")
            if not sequence:
                continue
            fold_name = f"{parent_name}_candidate_{index}"
            fold_args = {"sequence": sequence, "name": fold_name}
            fold_started = time.perf_counter()
            try:
                fold_result = await biolm_client.fold_sequence(
                    sequence=sequence, name=fold_name
                )
            except Exception as exc:
                _log_tool_error(session_id, "fold_sequence", fold_args, exc)
                raise
            _record_tool(
                trace,
                {
                    "tool": "fold_sequence",
                    "args": fold_args,
                    "result": fold_result,
                },
                session_id,
                duration_ms=_elapsed_ms(fold_started),
            )
            candidate["fold_result"] = fold_result

        return json.dumps(candidates)

    @tool
    async def fold_sequence_tool(sequence: str, name: str = "candidate") -> str:
        """Predict a 3D structure for `sequence` using BioLM ESMFold. Returns
        JSON with structure_available, mean_plddt (a confidence filter, not
        proof of function), model_source, and structure_id."""
        args = {"sequence": sequence, "name": name}
        started = time.perf_counter()
        try:
            result = await biolm_client.fold_sequence(sequence=sequence, name=name)
        except Exception as exc:
            _log_tool_error(session_id, "fold_sequence", args, exc)
            raise
        _record_tool(
            trace,
            {"tool": "fold_sequence", "args": args, "result": result},
            session_id,
            duration_ms=_elapsed_ms(started),
        )
        return json.dumps(result)

    @tool
    async def score_variant_tool(sequence: str) -> str:
        """Get a best-effort ESM-1v variant-effect score for `sequence`.
        Returns JSON with a `score` field, which may be null if scoring
        failed - this never blocks the rest of the pipeline."""
        args = {"sequence": sequence}
        started = time.perf_counter()
        try:
            result = await biolm_client.score_variant(sequence=sequence)
        except Exception as exc:
            _log_tool_error(session_id, "score_variant", args, exc)
            raise
        _record_tool(
            trace,
            {"tool": "score_variant", "args": args, "result": result},
            session_id,
            duration_ms=_elapsed_ms(started),
        )
        return json.dumps(result)

    @tool
    async def recommend_proteins_tool(
        accessions: List[str],
        reason: Optional[str] = None,
    ) -> str:
        """Recommend a shortlist of UniProt accessions from proteins already
        retrieved in this turn. Call whenever this turn returned more than one
        protein. Only pass accessions that search_uniprot / search_protrek /
        map_to_uniprot / get_uniprot_entry actually returned — never invent.
        Does not remove other hits from the full retrieved list; it only marks
        recommendations for the UI."""
        started = time.perf_counter()
        cleaned: List[str] = []
        seen: set = set()
        for raw in accessions or []:
            acc = (raw or "").strip()
            if not acc or acc in seen:
                continue
            seen.add(acc)
            cleaned.append(acc)
        args = {"accessions": cleaned, "reason": reason}
        _record_tool(
            trace,
            {"tool": "recommend_proteins", "args": args, "result": cleaned},
            session_id,
            duration_ms=_elapsed_ms(started),
        )
        return json.dumps({"recommended": cleaned, "reason": reason})

    tools = [
        search_uniprot_tool,
        get_uniprot_entry_tool,
        map_to_uniprot_tool,
        recommend_proteins_tool,
        propose_variants_tool,
        fold_sequence_tool,
        score_variant_tool,
    ]
    if config.protrek_base_url:
        # After get_uniprot_entry / before map_to_uniprot keeps retrieval tools grouped.
        tools.insert(2, search_protrek_tool)
    return tools


def _build_model(*, streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=config.openrouter_model,
        api_key=config.openrouter_api_key,
        base_url=config.openrouter_base_url,
        temperature=0.2,
        streaming=streaming,
    )


def _chunk_text(chunk: Any) -> str:
    """Extract displayable text from an AIMessageChunk (skip tool-call JSON)."""
    text_attr = getattr(chunk, "text", None)
    if isinstance(text_attr, str) and text_attr:
        return text_attr

    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                block_type = block.get("type")
                if block_type in ("tool_use", "tool_call", "tool_call_chunk"):
                    continue
                if isinstance(block.get("text"), str):
                    parts.append(block["text"])
        return "".join(parts)
    return ""


def _tool_call_name(tool_call: Any) -> Optional[str]:
    if isinstance(tool_call, dict):
        name = tool_call.get("name")
        return name if isinstance(name, str) else None
    name = getattr(tool_call, "name", None)
    return name if isinstance(name, str) else None


def _status_events_from_update(update: Dict[str, Any]) -> List[Dict[str, str]]:
    """Map agent-node updates that request tools into human-friendly status events."""
    events: List[Dict[str, str]] = []
    agent_update = update.get(_AGENT_NODE)
    if not isinstance(agent_update, dict):
        return events
    messages = agent_update.get("messages") or []
    for message in messages:
        tool_calls = getattr(message, "tool_calls", None) or []
        if isinstance(message, dict):
            tool_calls = message.get("tool_calls") or tool_calls
        for tool_call in tool_calls:
            name = _tool_call_name(tool_call)
            if not name:
                continue
            status = _TOOL_STATUS_MESSAGES.get(name)
            if status:
                events.append({"type": "status", "message": status})
            else:
                events.append({"type": "status", "message": f"Running {name}…"})
    return events


async def run_agent(
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
    session_id: Optional[str] = None,
) -> Tuple[str, List[TraceEntry]]:
    """Run one ProtDAP agent turn.

    Returns (reply_text, tool_trace). Highlights come from recommend_proteins
    entries in the trace (assembler validates against retrieved proteins).
    Session history should store only ``reply_text``.
    """
    trace: List[TraceEntry] = []
    tools = _build_tools(trace, session_id=session_id)
    model = _build_model(streaming=False)
    agent = create_react_agent(model, tools, prompt=SYSTEM_PROMPT)

    messages = list(history or [])
    messages.append({"role": "user", "content": user_message})

    final_state = await agent.ainvoke(
        {"messages": messages},
        config={"recursion_limit": RECURSION_LIMIT},
    )

    reply_text = _extract_reply(final_state.get("messages") or [])
    return reply_text, trace


async def run_agent_stream(
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
    session_id: Optional[str] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """Stream one ProtDAP agent turn for SSE.

    Yields dict events:
      - ``{"type": "status", "message": "..."}`` tool / thinking progress
      - ``{"type": "token", "delta": "..."}`` ReAct agent text only
      - ``{"type": "final", "reply": "...", "trace": [...]}`` end of turn

    Nested LLMs (e.g. ``propose_variants``) are filtered out by only
    forwarding ``messages`` chunks from the ``agent`` graph node.
    """
    trace: List[TraceEntry] = []
    tools = _build_tools(trace, session_id=session_id)
    model = _build_model(streaming=True)
    agent = create_react_agent(model, tools, prompt=SYSTEM_PROMPT)

    messages = list(history or [])
    messages.append({"role": "user", "content": user_message})

    yield {"type": "status", "message": "Thinking…"}

    final_state: Optional[Dict[str, Any]] = None
    async for mode, chunk in agent.astream(
        {"messages": messages},
        config={"recursion_limit": RECURSION_LIMIT},
        stream_mode=["messages", "updates", "values"],
    ):
        if mode == "messages":
            message_chunk, metadata = chunk
            if not isinstance(metadata, dict):
                continue
            if metadata.get("langgraph_node") != _AGENT_NODE:
                continue
            # Skip pure tool-call chunks; only forward visible assistant text.
            if getattr(message_chunk, "tool_call_chunks", None) and not _chunk_text(
                message_chunk
            ):
                continue
            delta = _chunk_text(message_chunk)
            if delta:
                yield {"type": "token", "delta": delta}
        elif mode == "updates":
            if isinstance(chunk, dict):
                for event in _status_events_from_update(chunk):
                    yield event
        elif mode == "values":
            if isinstance(chunk, dict):
                final_state = chunk

    reply_text = _extract_reply((final_state or {}).get("messages") or [])
    yield {"type": "final", "reply": reply_text, "trace": trace}


def _extract_reply(messages: List[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            text = _chunk_text(message)
            if text.strip():
                return text
        if isinstance(message, dict) and message.get("role") == "assistant":
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content
            text = _chunk_text(message)
            if text.strip():
                return text
    return "I wasn't able to produce a response for that request."
