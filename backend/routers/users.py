"""Users router.

v1 exposes only the authenticated user's own profile, used to confirm a
token is valid. No public user listing or registration UI.
"""

from fastapi import APIRouter, Depends

from models import User
from schemas.user import UserOut
from services.auth import get_current_user

router = APIRouter()


@router.get("/me", response_model=UserOut)
def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    """Return the authenticated user's profile."""
    return current_user
