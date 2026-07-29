"""Environment-based configuration for ProtDAP.

No secrets are hardcoded here; everything is read from the environment
(optionally via a local .env file loaded with python-dotenv). Required
variables are validated eagerly so misconfiguration fails fast at startup
instead of surfacing as a confusing runtime error deep in a tool call.
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class Config:
    # OpenRouter / LLM
    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    openrouter_model: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")
    )
    openrouter_base_url: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    )

    # BioLM MCP
    biolm_token: str = field(default_factory=lambda: os.getenv("BIOLMAI_TOKEN", ""))

    # UniProt
    uniprot_base_url: str = field(
        default_factory=lambda: os.getenv("UNIPROT_BASE_URL", "https://rest.uniprot.org")
    )

    # ProTrek local FastAPI (optional — tool registered only when set)
    protrek_base_url: str = field(
        default_factory=lambda: os.getenv("PROTREK_BASE_URL", "").rstrip("/")
    )

    # Search / generation defaults
    default_result_size: int = field(default_factory=lambda: _get_int("DEFAULT_RESULT_SIZE", 5))
    session_ttl_seconds: int = field(default_factory=lambda: _get_int("SESSION_TTL_SECONDS", 3600))

    # Frontend (CORS)
    frontend_origin: str = field(
        default_factory=lambda: os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
    )

    # Eval mode
    eval_live: bool = field(default_factory=lambda: _get_bool("EVAL_LIVE", False))

    def validate(self) -> None:
        missing = []
        if not self.openrouter_api_key:
            missing.append("OPENROUTER_API_KEY")
        if not self.biolm_token:
            missing.append("BIOLMAI_TOKEN")
        if missing:
            raise EnvironmentError(
                "Missing required environment variable(s): "
                + ", ".join(missing)
                + ". Copy .env.example to .env and fill them in."
            )


config = Config()
