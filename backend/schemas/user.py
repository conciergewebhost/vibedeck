"""User schemas (no password fields are ever serialised out)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    handle: str
    is_active: bool
    created_at: datetime


class PublicUserProfile(BaseModel):
    """An author's public profile (/u/{handle}) — no email or account state."""

    handle: str
    deck_count: int  # public + approved decks only
    created_at: datetime
