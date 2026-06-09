"""Users router — own profile + public author pages.

`/me` returns the authenticated user's own profile (used to confirm a
token is valid). The `/{handle}` routes are the public author surface
behind /u/{handle} pages: profile, decks, and per-topic listings. `/me`
is registered first and "me" is a reserved handle, so the param route
can never shadow it.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import User
from schemas.deck import PublicDeckItem
from schemas.topic import TopicDetail
from schemas.user import PublicUserProfile, UserOut
from services import decks as decks_service
from services import topics as topics_service
from services import users as users_service
from services.auth import get_current_user

router = APIRouter()


@router.get("/me", response_model=UserOut)
def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    """Return the authenticated user's profile."""
    return current_user


@router.get("/{handle}", response_model=PublicUserProfile)
def public_profile(handle: str, db: Session = Depends(get_db)) -> PublicUserProfile:
    """An author's public profile (no auth)."""
    profile = users_service.get_public_profile(db, handle)
    if profile is None:
        raise HTTPException(status_code=404, detail="User not found")
    return profile


@router.get("/{handle}/decks", response_model=list[PublicDeckItem])
def public_decks(handle: str, db: Session = Depends(get_db)) -> list[PublicDeckItem]:
    """An author's public+approved decks, for their /u/{handle} page."""
    if users_service.get_public_profile(db, handle) is None:
        raise HTTPException(status_code=404, detail="User not found")
    return decks_service.list_decks_by_handle(db, handle)


@router.get("/{handle}/topics/{topic_slug}", response_model=TopicDetail)
def public_topic(
    handle: str, topic_slug: str, db: Session = Depends(get_db)
) -> TopicDetail:
    """One topic in an author's namespace, for /u/{handle}/{topic} pages."""
    topic = topics_service.get_topic_for_owner(db, handle, topic_slug)
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    return topic
