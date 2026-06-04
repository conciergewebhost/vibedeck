"""Users router.

STUB: scaffolded for the auth-gated upload flow. No public user UI in v1.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/me")
def read_current_user() -> dict:
    """Return the authenticated user's profile. (Not implemented.)"""
    raise NotImplementedError
