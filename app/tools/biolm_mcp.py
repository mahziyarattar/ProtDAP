"""Real MCP client for BioLM (https://biolm.ai), used for folding and scoring.

This spawns the official `@biolm/biolm-mcp` Node package as a subprocess
over stdio (via the official `mcp` Python SDK) and calls its tools
directly - this is a genuine MCP client/server connection, not a REST
wrapper dressed up as one. Requires Node.js/npx to be installed alongside
Python; see README.md for setup.

BioLM tool names used (confirmed live against https://biolm.ai):
    predict_v3_esmfold      - protein structure prediction (fold_sequence)
    predict_v3_esm1v_all    - variant effect scoring (score_variant, best-effort)

pLDDT returned by fold_sequence is a structure-confidence *filter/report*
signal only - it is never treated as proof that a sequence is functional.

Connection lifetime - IMPORTANT: a *fresh* stdio connection (spawn npx,
initialize, call, close) is opened for every single fold_sequence/
score_variant call, rather than keeping one long-lived connection open for
the whole app and reusing it across calls. This was a deliberate fix after
hitting a real bug: `mcp`'s stdio transport is built on anyio task groups,
whose cancel scopes are pinned to the asyncio Task that entered them.
LangGraph's ToolNode dispatches each tool call as its own `asyncio.create_task`,
so a single persisted session ends up being entered in one Task and later
torn down/GC'd from another, raising
`RuntimeError: Attempted to exit cancel scope in a different task than it
was entered in`. Scoping the whole connection lifecycle to one `async with`
block inside a single coroutine call sidesteps this entirely. The
per-call `npx` startup cost (a few seconds once npm's local cache is warm)
is an acceptable trade-off for a prototype where folding is not a hot path.
"""

import asyncio
import json
import os
from typing import Any, Dict, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent

from app.structure_cache import store_structure

FOLD_TOOL_NAME = "predict_v3_esmfold"
SCORE_TOOL_NAME = "predict_v3_esm1v_all"

# Pinned so every `npx` spawn uses a cached local install instead of hitting
# the npm registry to resolve "latest" on every single fold_sequence/
# score_variant call - that per-call registry round trip was eating into the
# fixed client-side timeout below (see MAX_CALL_ATTEMPTS).
BIOLM_MCP_PACKAGE = "@biolm/biolm-mcp@0.9.1"

# The Node `@biolm/biolm` SDK inside @biolm/biolm-mcp has a fixed 60s
# client-side timeout that ProtDAP cannot configure (no CLI/env override
# exists). Retrying once after a timeout-shaped failure recovers most
# transient misses without masking a real, persistent outage.
MAX_CALL_ATTEMPTS = 2
RETRY_BACKOFF_SECONDS = 2.0


def _is_retryable(exc: Exception) -> bool:
    return "timed out" in str(exc).lower() or "timeout" in str(exc).lower()


class BioLMConnectionError(Exception):
    """Raised when the BioLM MCP subprocess can't be started or initialized."""


class BioLMToolError(Exception):
    """Raised when a BioLM MCP tool call returns an error result."""


class BioLMMCPClient:
    """Opens a fresh stdio connection to the BioLM MCP server per call.

    See the module docstring for why this doesn't reuse one long-lived
    connection across calls.

    Calls are serialized via `_call_lock`: LangGraph's ToolNode dispatches
    every tool call the agent makes in one turn concurrently (as separate
    asyncio tasks), so folding N proposed candidates used to spawn N
    simultaneous `npx` subprocesses. That concurrent cold-start load
    reliably pushed the fixed 60s client-side timeout in the Node BioLM SDK
    over budget, even for short sequences that fold in ~15s in isolation.
    Running fold/score calls one at a time trades a bit of wall-clock time
    per turn for calls that actually succeed.
    """

    def __init__(self, biolm_token: str):
        self._token = biolm_token
        self._last_check_ok: Optional[bool] = None
        self._call_lock = asyncio.Lock()

    @property
    def last_check_ok(self) -> Optional[bool]:
        """Result of the most recent `check_connection()` call, if any.
        None means no check has been made yet."""
        return self._last_check_ok

    def _server_params(self) -> StdioServerParameters:
        return StdioServerParameters(
            command="npx",
            args=["-y", BIOLM_MCP_PACKAGE],
            env={**os.environ, "BIOLMAI_TOKEN": self._token},
        )

    async def check_connection(self) -> bool:
        """One-off connectivity check (used at app startup / GET /liveness):
        spawns the server, completes the MCP handshake, and closes it again
        immediately. Does not keep anything open."""
        try:
            async with stdio_client(self._server_params()) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
            self._last_check_ok = True
        except Exception:
            self._last_check_ok = False
        return self._last_check_ok

    async def _call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Serialized, retrying entry point used by fold_sequence/score_variant.

        See the class docstring for why calls are serialized via `_call_lock`
        and MAX_CALL_ATTEMPTS for why a single timeout gets one retry.
        """
        async with self._call_lock:
            last_exc: Optional[Exception] = None
            for attempt in range(1, MAX_CALL_ATTEMPTS + 1):
                try:
                    return await self._call_tool_once(name, arguments)
                except (BioLMConnectionError, BioLMToolError) as exc:
                    last_exc = exc
                    if attempt >= MAX_CALL_ATTEMPTS or not _is_retryable(exc):
                        raise
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
            raise last_exc  # pragma: no cover - loop always returns or raises

    async def _call_tool_once(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            async with stdio_client(self._server_params()) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments)
        except FileNotFoundError as exc:
            raise BioLMConnectionError(
                "Could not spawn 'npx'. Node.js/npx must be installed to run the "
                "BioLM MCP server (@biolm/biolm-mcp)."
            ) from exc
        except (BioLMConnectionError, BioLMToolError):
            raise
        except Exception as exc:
            raise BioLMConnectionError(f"Failed to call BioLM MCP tool '{name}': {exc}") from exc

        if result.isError:
            error_text = _first_text(result) or "unknown error"
            raise BioLMToolError(f"BioLM tool '{name}' returned an error: {error_text}")

        if result.structuredContent:
            return result.structuredContent

        text = _first_text(result)
        if text is None:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}

    @staticmethod
    def _unwrap_results(raw: Dict[str, Any]) -> Dict[str, Any]:
        """BioLM's item-batch APIs wrap a single prediction in results[0]."""
        results = raw.get("results")
        if isinstance(results, list) and results:
            return results[0]
        return raw

    async def fold_sequence(self, sequence: str, name: str) -> Dict[str, Any]:
        """Fold a sequence with BioLM ESMFold. Never raises - failures are reported
        as structure_available=False so a fold failure never blocks the pipeline."""
        try:
            raw = await self._call_tool(FOLD_TOOL_NAME, {"items": [{"sequence": sequence}]})
        except (BioLMConnectionError, BioLMToolError) as exc:
            return {
                "structure_available": False,
                "model_source": f"BioLM ESMFold unavailable: {exc}",
                "mean_plddt": None,
                "structure_id": None,
            }

        result = self._unwrap_results(raw)
        pdb_text = result.get("pdb")
        mean_plddt = result.get("mean_plddt")

        if not pdb_text:
            return {
                "structure_available": False,
                "model_source": "BioLM ESMFold: no PDB returned",
                "mean_plddt": mean_plddt,
                "structure_id": None,
            }

        structure_id = store_structure(pdb_text, name_hint=name)
        return {
            "structure_available": True,
            "model_source": "BioLM ESMFold",
            "mean_plddt": mean_plddt,
            "structure_id": structure_id,
        }

    async def score_variant(self, sequence: str) -> Dict[str, Any]:
        """Best-effort ESM-1v variant effect score. Never raises; returns
        score=None on any failure so scoring never blocks the pipeline.

        Confirmed against the live BioLM API: predict_v3_esm1v_all is a
        masked-language-model point-mutation scorer - it requires exactly
        one literal '<mask>' token in `sequence` marking the position to
        score, and returns per-residue log-likelihoods from the 5-model
        ensemble at that position. A plain full candidate sequence (with no
        masked position) is rejected with a 400 error, which is caught here
        and reported as score=None. Future work: use each candidate's
        `modifications` (position/original/new, from propose_variants) to
        build a masked sequence per mutated position and aggregate a real
        score, instead of always falling back to None.
        """
        try:
            raw = await self._call_tool(SCORE_TOOL_NAME, {"items": [{"sequence": sequence}]})
        except (BioLMConnectionError, BioLMToolError):
            return {"score": None}

        result = self._unwrap_results(raw)
        score = (
            result.get("score")
            or result.get("mean_score")
            or result.get("pseudo_log_likelihood")
        )
        return {"score": score}


def _first_text(result) -> Optional[str]:
    for block in result.content or []:
        if isinstance(block, TextContent):
            return block.text
    return None


# Module-level singleton used by the FastAPI app / agent tools. Safe to
# share across asyncio Tasks since it no longer holds any persistent
# connection state - see the module docstring.
_client: Optional[BioLMMCPClient] = None


def get_biolm_client(biolm_token: str) -> BioLMMCPClient:
    global _client
    if _client is None:
        _client = BioLMMCPClient(biolm_token)
    return _client


def reset_biolm_client() -> None:
    global _client
    _client = None
