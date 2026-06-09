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


class ModerationSummary(BaseModel):
    """Moderation counts for the admin surface and the daily digest email."""

    queue_size: int  # flagged decks currently awaiting review
    blocked_24h: int  # decks rejected outright in the last 24 hours
    flagged_24h: int  # decks newly quarantined in the last 24 hours
