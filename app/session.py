"""In-memory, cookie-backed session store.

Fresh implementation (no code ported from the legacy ProteinSearch repo),
but the same general shape: a session id lives in an HTTP cookie, and the
server keeps a small in-memory record per session (conversation history +
the most recently retrieved proteins) so a "diversify this" follow-up
message can refer back to an earlier search without the client resending
everything.
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SESSION_COOKIE_NAME = "protdap_session"


@dataclass
class SessionData:
    created_at: float = field(default_factory=time.time)
    last_access: float = field(default_factory=time.time)
    # LangChain/LangGraph-style role+content history for conversation continuity.
    history: List[Dict[str, str]] = field(default_factory=list)
    last_retrieved_proteins: List[Dict[str, Any]] = field(default_factory=list)


class SessionStore:
    def __init__(self, ttl_seconds: int = 3600):
        self._sessions: Dict[str, SessionData] = {}
        self._ttl_seconds = ttl_seconds

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired = [
            sid
            for sid, data in self._sessions.items()
            if now - data.last_access > self._ttl_seconds
        ]
        for sid in expired:
            del self._sessions[sid]

    def get_or_create(self, session_id: Optional[str]) -> tuple[str, SessionData]:
        self._cleanup_expired()

        if session_id and session_id in self._sessions:
            data = self._sessions[session_id]
            data.last_access = time.time()
            return session_id, data

        new_id = str(uuid.uuid4())
        data = SessionData()
        self._sessions[new_id] = data
        return new_id, data

    def append_history(self, session_id: str, role: str, content: str) -> None:
        if session_id not in self._sessions:
            return
        self._sessions[session_id].history.append({"role": role, "content": content})
        self._sessions[session_id].last_access = time.time()

    def set_last_retrieved_proteins(
        self, session_id: str, proteins: List[Dict[str, Any]]
    ) -> None:
        if session_id not in self._sessions:
            return
        self._sessions[session_id].last_retrieved_proteins = proteins
        self._sessions[session_id].last_access = time.time()

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        data = self._sessions.get(session_id)
        return list(data.history) if data else []

    def get_last_retrieved_proteins(self, session_id: str) -> List[Dict[str, Any]]:
        data = self._sessions.get(session_id)
        return list(data.last_retrieved_proteins) if data else []


# Module-level singleton used by the FastAPI app.
session_store: Optional[SessionStore] = None


def get_session_store(ttl_seconds: int = 3600) -> SessionStore:
    global session_store
    if session_store is None:
        session_store = SessionStore(ttl_seconds=ttl_seconds)
    return session_store
