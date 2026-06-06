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
