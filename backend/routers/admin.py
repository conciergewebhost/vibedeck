"""Admin router — owner-only user monitoring (mounted at /api/admin).

Deck management (list all / delete any / upload) lives on the decks router,
gated by the same get_current_admin dependency.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from database import get_db
from models import User
from schemas.admin import AdminUserItem, ModerationSummary
from schemas.deck import AdminDeckItem
from services import admin as admin_service
from services import decks as decks_service
from services.auth import get_current_admin

router = APIRouter()


@router.get("/users", response_model=list[AdminUserItem])
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> list[AdminUserItem]:
    """All users (most recent first) with deck count, created/last-login/last-deck dates."""
    return admin_service.list_users(db)


@router.get("/users/{user_id}/decks", response_model=list[AdminDeckItem])
def list_user_decks(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> list[AdminDeckItem]:
    """Decks owned by a given user — for the admin per-user view."""
    return decks_service.list_user_decks(db, user_id)


@router.get("/flagged", response_model=list[AdminDeckItem])
def list_flagged(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> list[AdminDeckItem]:
    """The moderation review queue: quarantined decks, oldest flag first."""
    return decks_service.list_flagged_decks(db)


@router.post(
    "/decks/{topic_slug}/{deck_slug}/approve",
    status_code=status.HTTP_204_NO_CONTENT,
)
def approve_deck(
    topic_slug: str,
    deck_slug: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> Response:
    """Approve a flagged deck — it becomes visible per its visibility setting.

    Rejecting a deck is the existing DELETE /api/decks/{topic}/{slug}.
    """
    if not decks_service.approve_deck_by_slugs(db, topic_slug, deck_slug):
        raise HTTPException(status_code=404, detail="Deck not found")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/decks/{topic_slug}/{deck_slug}/source")
def get_deck_source(
    topic_slug: str,
    deck_slug: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> Response:
    """Raw markdown of any deck — for reviewing quarantined content."""
    markdown = decks_service.get_deck_source_by_slugs(db, topic_slug, deck_slug)
    if markdown is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    return Response(content=markdown, media_type="text/markdown")


@router.get("/moderation-summary", response_model=ModerationSummary)
def moderation_summary(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> ModerationSummary:
    """Queue size + last-24h block/flag counts (also used by the digest)."""
    return admin_service.moderation_summary(db)
