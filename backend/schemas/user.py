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
    # Role flags for the session's own /me payload — how the frontend learns
    # whether to show admin affordances. is_admin is true for the owner too;
    # is_owner additionally marks the UPLOAD_OWNER_EMAIL account (role
    # management is owner-only). Computed in the router, not stored.
    is_admin: bool = False
    is_owner: bool = False


class PublicUserProfile(BaseModel):
    """An author's public profile (/u/{handle}) — no email or account state."""

    handle: str
    deck_count: int  # public + approved decks only
    created_at: datetime
