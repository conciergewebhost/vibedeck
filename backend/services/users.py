"""Users service — public author profiles (/u/{handle})."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import Deck, User
from schemas.user import PublicUserProfile


def get_public_profile(db: Session, handle: str) -> PublicUserProfile | None:
    """An author's public profile, or None. Counts only the decks a
    stranger could actually read in listings (public + approved)."""
    user = db.scalar(select(User).where(User.handle == handle))
    if user is None or not user.is_active:
        return None
    deck_count = db.scalar(
        select(func.count())
        .select_from(Deck)
        .where(
            Deck.owner_id == user.id,
            Deck.visibility == "public",
            Deck.moderation_status == "approved",
        )
    )
    return PublicUserProfile(
        handle=user.handle, deck_count=deck_count or 0, created_at=user.created_at
    )
