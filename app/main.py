"""ProtDAP FastAPI app: POST /chat, GET /structures/{id}, GET /liveness.

Request flow: a session cookie identifies an in-memory conversation history
-> the ReAct agent (app/agent/graph.py) runs with that history and produces
a natural-language reply plus a raw tool-call trace -> the deterministic
assembler (app/agent/assembler.py) turns that trace into schema-conformant
`retrieved_proteins` / `candidates` -> the response is returned and the
session history is updated for the next turn.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.agent.assembler import assemble_response, summarize_trace
from app.agent.graph import run_agent
from app.config import config
from app.models import ChatRequest, ChatResponse, FoldRequest, StructureInfo
from app.session import SESSION_COOKIE_NAME, get_session_store
from app.structure_cache import get_structure
from app.tools.biolm_mcp import get_biolm_client
from app.tools.generation import VALID_AMINO_ACIDS

logger = logging.getLogger("protdap")


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.validate()
    # One-off connectivity check at startup (spawn, handshake, close) so
    # misconfiguration (bad token, missing npx) is visible in the logs
    # early. Each fold_sequence/score_variant call still opens its own
    # fresh connection - see app/tools/biolm_mcp.py's module docstring for
    # why a single persisted connection isn't safe across LangGraph's
    # per-tool-call asyncio Tasks.
    biolm_check_timeout_seconds = 20
    client = get_biolm_client(config.biolm_token)
    try:
        ok = await asyncio.wait_for(client.check_connection(), timeout=biolm_check_timeout_seconds)
        if ok:
            logger.info("BioLM MCP server connectivity check passed.")
        else:
            logger.warning("BioLM MCP server connectivity check failed; continuing anyway.")
    except asyncio.TimeoutError:
        logger.warning(
            "BioLM MCP connectivity check did not respond within %ss at startup; continuing anyway.",
            biolm_check_timeout_seconds,
        )

    yield


app = FastAPI(
    title="ProtDAP",
    description=(
        "ReAct agent that searches UniProt and diversifies proteins via "
        "BioLM (ESMFold / ESM-1v), with schema-enforced, provenance-labeled "
        "output."
    ),
    lifespan=lifespan,
)

# The session id travels as an httponly cookie (see app/session.py), so the
# frontend's fetch calls need credentials: 'include' and this middleware
# needs allow_credentials=True - which in turn means allow_origins can't be
# "*" and must list the frontend's exact origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/liveness")
async def liveness():
    biolm_client = get_biolm_client(config.biolm_token)
    return {
        "status": "ok",
        "biolm_mcp_last_check_ok": biolm_client.last_check_ok,
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(chat_request: ChatRequest, request: Request, response: Response) -> ChatResponse:
    session_store = get_session_store(config.session_ttl_seconds)
    incoming_session_id = request.cookies.get(SESSION_COOKIE_NAME)
    session_id, session_data = session_store.get_or_create(incoming_session_id)

    history = session_store.get_history(session_id)

    reply_text, trace = await run_agent(
        user_message=chat_request.message,
        history=history,
        session_id=session_id,
    )

    retrieved_proteins, candidates, highlighted_accessions = assemble_response(trace)
    tool_trace_summary = summarize_trace(trace)

    session_store.append_history(session_id, "user", chat_request.message)
    session_store.append_history(session_id, "assistant", reply_text)
    if retrieved_proteins:
        session_store.set_last_retrieved_proteins(
            session_id, [protein.model_dump() for protein in retrieved_proteins]
        )

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=config.session_ttl_seconds,
        httponly=True,
        samesite="lax",
    )

    return ChatResponse(
        reply=reply_text,
        retrieved_proteins=retrieved_proteins,
        candidates=candidates,
        tool_trace_summary=tool_trace_summary,
        highlighted_accessions=highlighted_accessions,
    )


@app.post("/fold", response_model=StructureInfo)
async def fold_route(fold_request: FoldRequest) -> StructureInfo:
    """On-demand fold of an arbitrary sequence, outside the chat/agent loop
    and outside any session - used by the frontend to let the user fold a
    retrieved (non-candidate) protein directly. The result is not stored
    server-side beyond the structure cache backing GET /structures/{id};
    it is not attached to any conversation's retrieved_proteins/candidates."""
    sequence = "".join(fold_request.sequence.split()).upper()
    if len(sequence) < 10 or any(residue not in VALID_AMINO_ACIDS for residue in sequence):
        raise HTTPException(
            status_code=400,
            detail="sequence must be at least 10 residues of valid amino acid letters.",
        )

    biolm_client = get_biolm_client(config.biolm_token)
    fold_result = await biolm_client.fold_sequence(
        sequence=sequence, name=fold_request.name or "protein"
    )
    return StructureInfo(
        available=bool(fold_result.get("structure_available")),
        mean_plddt=fold_result.get("mean_plddt"),
        model_source=fold_result.get("model_source"),
        structure_id=fold_result.get("structure_id"),
    )


@app.get("/structures/{structure_id}")
async def get_structure_route(structure_id: str):
    pdb_text = get_structure(structure_id)
    if pdb_text is None:
        return PlainTextResponse(
            f"Structure '{structure_id}' not found (it may have expired or never existed).",
            status_code=404,
        )
    return PlainTextResponse(pdb_text, media_type="chemical/x-pdb")
