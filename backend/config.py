"""Application settings, loaded from environment / .env.

Uses pydantic-settings so every value is typed and validated at startup.
Run the backend from the backend/ directory so the import paths below
(`from config import settings`) resolve as flat modules.
"""

from enum import Enum
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Edition(str, Enum):
    """How this deployment is run, from one config-driven codebase.

    `standalone` — a single person on their own server: no public sign-up
        surface; the one account is the owner.
    `server` — a host running many users' decks: public (invite-gated)
        sign-up, and the multi-user controls (moderation, per-deck
        visibility, quotas) are enabled.

    The edition drives the derived feature flags on Settings below; nothing in
    the app branches on the raw EDITION value directly.
    """

    STANDALONE = "standalone"
    SERVER = "server"


class Settings(BaseSettings):
    # .env lives at the repo root, one level above backend/.
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str
    SECRET_KEY: str
    UPLOAD_DIR: Path
    BASE_URL: str = "http://localhost:4321"
    ENVIRONMENT: str = "development"

    # Which edition this deployment runs as (see Edition above). Defaults to
    # standalone — the right default for a fresh clone. A multi-user host sets
    # EDITION=server in its .env.
    EDITION: Edition = Edition.STANDALONE

    # Shared-token gate for the /admin web surface, and the account that
    # token-gated (and CLI) uploads are attributed to. Required.
    UPLOAD_TOKEN: str
    UPLOAD_OWNER_EMAIL: str

    # JWT defaults — not in .env yet; promote to env vars if they need tuning.
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day

    # Passwordless (magic-link) signup/login. NEW_USER_CODE gates account
    # creation during the testing phase; existing users skip it. Email is
    # sent via the Resend HTTP API.
    NEW_USER_CODE: str
    RESEND_API_KEY: str
    EMAIL_FROM_ADDRESS: str
    EMAIL_FROM_NAME: str = "Vibedeck"
    # Magic links are short-lived signed JWTs (no DB token table).
    MAGIC_LINK_EXPIRE_MINUTES: int = 15

    # Per-IP rate limits on POST /api/auth/request-link (sliding 1-hour
    # window). The overall cap blunts email-spam and general hammering; the
    # tighter bad-code cap specifically throttles invite-code guessing.
    RATE_LIMIT_REQUESTS_PER_HOUR: int = 12
    RATE_LIMIT_BAD_CODE_PER_HOUR: int = 5

    # Where the daily moderation digest goes (see jobs/daily_digest.py).
    # Blank → falls back to the owner/admin account email.
    ADMIN_DIGEST_EMAIL: str = ""

    # Per-user creation caps (server edition only; admins and the owner are
    # exempt). Deck files are individually capped at 256 KB, so the deck
    # count also bounds per-user storage (50 × 256 KB ≈ 13 MB).
    QUOTA_MAX_DECKS: int = 50
    QUOTA_MAX_THEMES: int = 20

    # Reader reports: a deck reported by this many DISTINCT reporters is
    # auto-quarantined (hidden, into the admin review queue) until a human
    # rules. Reports are rate-limited per client IP.
    REPORT_QUARANTINE_THRESHOLD: int = 3
    RATE_LIMIT_REPORTS_PER_HOUR: int = 5

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    # ── Derived edition feature flags ─────────────────────────────────────
    # Computed from EDITION so the editions differ by configuration, not by a
    # code fork. The /api/meta endpoint exposes these (non-secret) to the
    # frontend so it can adapt its UI without a rebuild.

    @property
    def is_server(self) -> bool:
        return self.EDITION == Edition.SERVER

    @property
    def allow_public_signup(self) -> bool:
        """Whether strangers may request an account. Standalone is single-user,
        so the (invite-gated) sign-up surface is off; server allows it."""
        return self.is_server

    @property
    def allow_anon_read(self) -> bool:
        """Whether decks are readable without a session. True in both editions
        today; this is the seam for requiring auth on private decks later."""
        return True

    @property
    def moderation_enabled(self) -> bool:
        """Server-only: content moderation on user-submitted decks."""
        return self.is_server

    @property
    def visibility_enabled(self) -> bool:
        """Server-only: per-deck public/private/unlisted visibility."""
        return self.is_server

    @property
    def quotas_enabled(self) -> bool:
        """Server-only: per-user deck/storage quotas and abuse controls."""
        return self.is_server

    @property
    def user_spaces_enabled(self) -> bool:
        """Server-only: namespaced /u/{handle}/… canonical URLs. Standalone
        keeps flat /{topic}/{deck} URLs (one owner — no ambiguity). The data
        model is identical in both editions; only URL shape differs (see
        services/urls.py)."""
        return self.is_server

    @property
    def admin_digest_email(self) -> str:
        """Recipient of the daily moderation digest; defaults to the owner."""
        return self.ADMIN_DIGEST_EMAIL or self.UPLOAD_OWNER_EMAIL


# Single import-time instance; FastAPI dependencies read from this.
settings = Settings()  # type: ignore[call-arg]
