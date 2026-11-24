from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


@dataclass(frozen=True)
class Settings:
    """Application settings loaded strictly from environment variables."""

    fireworks_api_key: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str | None = None

    default_provider: str = "fireworks"
    fireworks_model: str = "accounts/fireworks/models/kimi-k2-instruct-0905"
    openai_model: str = "gpt-4o-mini"

    auth_secret: str = ""
    allow_registration: bool = True
    token_ttl_minutes: int = 1440

    db_path: str = "data/jarvis.db"
    log_level: str = "INFO"
    allowed_origins: List[str] = field(default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"])
    ephemeral_auth_secret: bool = False

    def registered_secrets(self) -> List[str]:
        """Return non-empty secret values so the logger can redact them automatically."""
        candidates = [self.fireworks_api_key, self.openai_api_key, self.auth_secret]
        return [s for s in candidates if s and len(s) >= 6]

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> "Settings":
        if load_dotenv is not None:
            if env_file is not None:
                load_dotenv(dotenv_path=env_file, override=False)
            else:
                load_dotenv(override=False)

        raw_secret = os.getenv("JARVIS_AUTH_SECRET", "").strip()
        ephemeral = False
        if not raw_secret:
            raw_secret = secrets.token_urlsafe(32)
            ephemeral = True

        origins_raw = os.getenv("JARVIS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173")
        origins = [o.strip() for o in origins_raw.split(",") if o.strip()]

        ttl_raw = os.getenv("JARVIS_TOKEN_TTL_MINUTES", "1440").strip() or "1440"
        allow_reg_raw = os.getenv("JARVIS_ALLOW_REGISTRATION", "true").strip().lower()

        return cls(
            fireworks_api_key=os.getenv("FIREWORKS_API_KEY", "").strip() or None,
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip() or None,
            openai_base_url=os.getenv("OPENAI_BASE_URL", "").strip() or None,
            default_provider=(os.getenv("JARVIS_DEFAULT_PROVIDER", "fireworks").strip() or "fireworks").lower(),
            fireworks_model=os.getenv("FIREWORKS_MODEL", "accounts/fireworks/models/kimi-k2-instruct-0905").strip()
            or "accounts/fireworks/models/kimi-k2-instruct-0905",
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
            auth_secret=raw_secret,
            allow_registration=allow_reg_raw in {"1", "true", "yes", "on"},
            token_ttl_minutes=max(5, int(ttl_raw)),
            db_path=os.getenv("JARVIS_DB_PATH", "data/jarvis.db").strip() or "data/jarvis.db",
            log_level=os.getenv("JARVIS_LOG_LEVEL", "INFO").strip().upper() or "INFO",
            allowed_origins=origins,
            ephemeral_auth_secret=ephemeral,
        )