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
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from app.agent.prompts import MAX_TOOL_ITERATIONS, SYSTEM_PROMPT
from app.config import config
from app.tools.biolm_mcp import get_biolm_client
from app.tools.generation import propose_variants
from app.tools.uniprot import search_uniprot, get_uniprot_entry

TraceEntry = Dict[str, Any]

# LangGraph counts each node execution (agent, tools) as one recursion step.
# Cap generously above the intended iteration count so hitting the limit is
# always a real runaway loop, not a normal multi-tool turn.
RECURSION_LIMIT = 2 * MAX_TOOL_ITERATIONS + 5


def _build_tools(trace: List[TraceEntry]):
    biolm_client = get_biolm_client(config.biolm_token)

    @tool
    async def search_uniprot_tool(
        text: str,
        size: Optional[int] = None,
        reviewed: bool = True,
        organism_id: Optional[str] = None,
    ) -> str:
        """Search UniProtKB for real, existing proteins matching a plain-text
        description (e.g. 'human proteins involved in immune response').
        Returns a JSON list of hits with accession, protein_name, organism,
        length, sequence, function."""
        result = await search_uniprot(
            text=text, size=size, reviewed=reviewed, organism_id=organism_id
        )
        trace.append(
            {
                "tool": "search_uniprot",
                "args": {
                    "text": text,
                    "size": size,
                    "reviewed": reviewed,
                    "organism_id": organism_id,
                },
                "result": result,
            }
        )
        return json.dumps(result)

    @tool
    async def get_uniprot_entry_tool(accession: str) -> str:
        """Fetch one specific UniProtKB entry by accession (e.g. 'P01308')."""
        result = await get_uniprot_entry(accession)
        trace.append(
            {
                "tool": "get_uniprot_entry",
                "args": {"accession": accession},
                "result": result,
            }
        )
        return json.dumps(result)

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
        candidates = await propose_variants(
            parent_sequence=parent_sequence,
            parent_name=parent_name,
            instruction=instruction,
            n=n,
        )
        trace.append(
            {
                "tool": "propose_variants",
                "args": {
                    "parent_sequence": parent_sequence,
                    "parent_name": parent_name,
                    "instruction": instruction,
                    "n": n,
                },
                "result": candidates,
            }
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
            fold_result = await biolm_client.fold_sequence(sequence=sequence, name=fold_name)
            trace.append(
                {
                    "tool": "fold_sequence",
                    "args": {"sequence": sequence, "name": fold_name},
                    "result": fold_result,
                }
            )
            candidate["fold_result"] = fold_result

        return json.dumps(candidates)

    @tool
    async def fold_sequence_tool(sequence: str, name: str = "candidate") -> str:
        """Predict a 3D structure for `sequence` using BioLM ESMFold. Returns
        JSON with structure_available, mean_plddt (a confidence filter, not
        proof of function), model_source, and structure_id."""
        result = await biolm_client.fold_sequence(sequence=sequence, name=name)
        trace.append(
            {
                "tool": "fold_sequence",
                "args": {"sequence": sequence, "name": name},
                "result": result,
            }
        )
        return json.dumps(result)

    @tool
    async def score_variant_tool(sequence: str) -> str:
        """Get a best-effort ESM-1v variant-effect score for `sequence`.
        Returns JSON with a `score` field, which may be null if scoring
        failed - this never blocks the rest of the pipeline."""
        result = await biolm_client.score_variant(sequence=sequence)
        trace.append(
            {
                "tool": "score_variant",
                "args": {"sequence": sequence},
                "result": result,
            }
        )
        return json.dumps(result)

    return [
        search_uniprot_tool,
        get_uniprot_entry_tool,
        propose_variants_tool,
        fold_sequence_tool,
        score_variant_tool,
    ]


def _build_model() -> ChatOpenAI:
    return ChatOpenAI(
        model=config.openrouter_model,
        api_key=config.openrouter_api_key,
        base_url=config.openrouter_base_url,
        temperature=0.2,
    )


async def run_agent(
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> Tuple[str, List[TraceEntry]]:
    """Run one ProtDAP agent turn.

    Returns (reply_text, tool_trace) where tool_trace is a list of
    {"tool": str, "args": dict, "result": <raw python object>} entries in
    call order - the ground truth the assembler builds candidates from.
    """
    trace: List[TraceEntry] = []
    tools = _build_tools(trace)
    model = _build_model()
    agent = create_react_agent(model, tools, prompt=SYSTEM_PROMPT)

    messages = list(history or [])
    messages.append({"role": "user", "content": user_message})

    final_state = await agent.ainvoke(
        {"messages": messages},
        config={"recursion_limit": RECURSION_LIMIT},
    )

    reply_text = _extract_reply(final_state["messages"])
    return reply_text, trace


def _extract_reply(messages: List[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and isinstance(message.content, str) and message.content.strip():
            return message.content
        if isinstance(message, dict) and message.get("role") == "assistant":
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content
    return "I wasn't able to produce a response for that request."
