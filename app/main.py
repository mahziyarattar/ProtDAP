"""ProtDAP FastAPI app: POST /chat, POST /chat/stream, GET /structures/{id}, GET /liveness.

Request flow: a session cookie identifies an in-memory conversation history
-> the ReAct agent (app/agent/graph.py) runs with that history and produces
a natural-language reply plus a raw tool-call trace -> the deterministic
assembler (app/agent/assembler.py) turns that trace into schema-conformant
`retrieved_proteins` / `candidates` -> the response is returned and the
session history is updated for the next turn.

`POST /chat` returns one JSON `ChatResponse`. `POST /chat/stream` streams
the same turn as SSE (`status` / `token` / `done` / `error`) and ends with
a `done` event whose payload matches `ChatResponse`.
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse

from app.agent.assembler import assemble_response, summarize_trace
from app.agent.graph import run_agent, run_agent_stream
from app.config import config
from app.models import ChatRequest, ChatResponse, FoldRequest, StructureInfo
from app.session import SESSION_COOKIE_NAME, get_session_store
from app.structure_cache import get_structure
from app.tools.biolm_mcp import get_biolm_client
from app.tools.generation import VALID_AMINO_ACIDS

logger = logging.getLogger("protdap")


def _configure_logging() -> None:
    """Attach stderr handler for protdap.* (uvicorn --log-level alone won't)."""
    env_level = os.getenv("LOG_LEVEL")
    if env_level:
        level = getattr(logging, env_level.upper(), logging.INFO)
    else:
        uvicorn_level = logging.getLogger("uvicorn").level
        level = uvicorn_level if uvicorn_level != logging.NOTSET else logging.INFO

    root = logging.getLogger("protdap")
    root.setLevel(level)
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(levelname)s:     %(name)s - %(message)s")
        )
        root.addHandler(handler)
    root.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
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


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=config.session_ttl_seconds,
        httponly=True,
        samesite="lax",
    )


def _commit_chat_turn(
    session_id: str,
    user_message: str,
    reply_text: str,
    retrieved_proteins: list,
) -> None:
    session_store = get_session_store(config.session_ttl_seconds)
    session_store.append_history(session_id, "user", user_message)
    session_store.append_history(session_id, "assistant", reply_text)
    if retrieved_proteins:
        session_store.set_last_retrieved_proteins(
            session_id, [protein.model_dump() for protein in retrieved_proteins]
        )


def _sse_event(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


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

    _commit_chat_turn(session_id, chat_request.message, reply_text, retrieved_proteins)
    _set_session_cookie(response, session_id)

    return ChatResponse(
        reply=reply_text,
        retrieved_proteins=retrieved_proteins,
        candidates=candidates,
        tool_trace_summary=tool_trace_summary,
        highlighted_accessions=highlighted_accessions,
    )


@app.post("/chat/stream")
async def chat_stream(chat_request: ChatRequest, request: Request) -> StreamingResponse:
    """SSE stream for one chat turn. Same body as POST /chat.

    Events:
      - status: ``{"message": "..."}``
      - token: ``{"delta": "..."}``
      - done: full ``ChatResponse`` JSON (structured lists only here)
      - error: ``{"detail": "..."}``
    """
    session_store = get_session_store(config.session_ttl_seconds)
    incoming_session_id = request.cookies.get(SESSION_COOKIE_NAME)
    session_id, _session_data = session_store.get_or_create(incoming_session_id)
    history = session_store.get_history(session_id)

    async def event_generator() -> AsyncIterator[str]:
        reply_text = ""
        trace: list = []
        try:
            async for event in run_agent_stream(
                user_message=chat_request.message,
                history=history,
                session_id=session_id,
            ):
                etype = event.get("type")
                if etype == "status":
                    yield _sse_event("status", {"message": event["message"]})
                elif etype == "token":
                    yield _sse_event("token", {"delta": event["delta"]})
                elif etype == "final":
                    reply_text = event["reply"]
                    trace = event["trace"]

            retrieved_proteins, candidates, highlighted_accessions = assemble_response(trace)
            tool_trace_summary = summarize_trace(trace)
            _commit_chat_turn(
                session_id, chat_request.message, reply_text, retrieved_proteins
            )

            done_payload = ChatResponse(
                reply=reply_text,
                retrieved_proteins=retrieved_proteins,
                candidates=candidates,
                tool_trace_summary=tool_trace_summary,
                highlighted_accessions=highlighted_accessions,
            ).model_dump()
            yield _sse_event("done", done_payload)
        except Exception as exc:
            logger.exception("chat/stream failed (session_id=%s)", session_id)
            yield _sse_event("error", {"detail": str(exc) or exc.__class__.__name__})

    response = StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
    _set_session_cookie(response, session_id)
    return response


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
