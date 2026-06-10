"""Application settings, loaded from environment / .env.

Uses pydantic-settings so every value is typed and validated at startup.
Run the backend from the backend/ directory so the import paths below
(`from config import settings`) resolve as flat modules.
"""

from enum import Enum
from pathlib import Path

from pydantic import model_validator
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
    # creation during the testing phase; existing users skip it.
    NEW_USER_CODE: str
    # Magic-link email delivery is optional and auto-detected (see
    # email_delivery below): set RESEND_API_KEY for Resend, or SMTP_HOST for
    # any SMTP server. With neither, sign-in links are written to the server
    # log instead of emailed — fine for single-user or dev deployments.
    RESEND_API_KEY: str = ""
    EMAIL_FROM_ADDRESS: str = ""
    EMAIL_FROM_NAME: str = "Vibedeck"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TLS: bool = True  # STARTTLS; disable only for a trusted local relay
    # Magic links are short-lived signed JWTs (no DB token table).
    MAGIC_LINK_EXPIRE_MINUTES: int = 15

    # Optional shared password for the login page; signing in with it issues
    # a session as the UPLOAD_OWNER_EMAIL account. Meant for single-user
    # deployments that don't want email or per-user passwords. Blank = the
    # login method is disabled (and hidden from the UI via /api/meta).
    SITE_PASSWORD: str = ""

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

    @model_validator(mode="after")
    def _check_email_config(self) -> "Settings":
        """Fail fast on contradictory email settings instead of failing on
        the first send. Having neither provider is fine (log delivery)."""
        if self.RESEND_API_KEY and self.SMTP_HOST:
            raise ValueError(
                "Configure either RESEND_API_KEY or SMTP_HOST, not both — "
                "Vibedeck can't tell which provider should deliver email."
            )
        if (self.RESEND_API_KEY or self.SMTP_HOST) and not self.EMAIL_FROM_ADDRESS:
            raise ValueError(
                "EMAIL_FROM_ADDRESS is required when an email provider "
                "(RESEND_API_KEY or SMTP_HOST) is configured."
            )
        if (self.SMTP_USERNAME or self.SMTP_PASSWORD) and not self.SMTP_HOST:
            raise ValueError(
                "SMTP_USERNAME/SMTP_PASSWORD are set but SMTP_HOST is not — "
                "set SMTP_HOST or remove the SMTP credentials."
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def email_delivery(self) -> str:
        """Which backend services/email.py sends through: "resend", "smtp",
        or "log" (no provider configured — links go to the server log).
        A property, not a stored field, so tests can flip the singleton's
        provider settings at runtime (same pattern as the EDITION flags)."""
        if self.RESEND_API_KEY:
            return "resend"
        if self.SMTP_HOST:
            return "smtp"
        return "log"

    @property
    def site_password_enabled(self) -> bool:
        """Whether the shared site-password login method is available."""
        return bool(self.SITE_PASSWORD)

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
