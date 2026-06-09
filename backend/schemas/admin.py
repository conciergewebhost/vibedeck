"""Admin-only API schemas."""

from datetime import datetime

from pydantic import BaseModel


class AdminUserItem(BaseModel):
    """A user row for the admin monitoring list."""

    id: int
    email: str
    created_at: datetime
    last_login_at: datetime | None = None
    deck_count: int
    last_deck_at: datetime | None = None  # most recent deck this user added
    is_admin: bool = False  # True for the owner too (config-derived)
    is_owner: bool = False  # the UPLOAD_OWNER_EMAIL account
    is_active: bool = True  # False == banned (content hidden, login refused)


class ModerationSummary(BaseModel):
    """Moderation counts for the admin surface and the daily digest email."""

    queue_size: int  # flagged decks currently awaiting review
    blocked_24h: int  # decks rejected outright in the last 24 hours
    flagged_24h: int  # decks newly quarantined in the last 24 hours
    open_reports: int = 0  # decks with at least one standing reader report
    reports_24h: int = 0  # report rows filed in the last 24 hours


class ReportedDeckItem(BaseModel):
    """One reported deck in the admin Reports queue (reports grouped)."""

    deck_id: int
    title: str
    url: str
    owner_email: str | None = None
    moderation_status: str
    report_count: int  # distinct reporters
    reasons: dict[str, int]  # reason -> count
    details: list[str]  # recent non-empty free-text details
    latest_at: datetime
