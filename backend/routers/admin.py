"""Admin router — owner-only user monitoring (mounted at /api/admin).

Deck management (list all / delete any / upload) lives on the decks router,
gated by the same get_current_admin dependency.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import User
from schemas.admin import AdminUserItem
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
