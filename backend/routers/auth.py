"""Auth router — JWT login / token issuance.

STUB: endpoints are scaffolded but not implemented. Auth logic (password
verification, token signing) will live in services/auth.py.
"""

from fastapi import APIRouter

router = APIRouter()


@router.post("/token")
def login() -> dict:
    """Exchange credentials for a JWT access token. (Not implemented.)"""
    raise NotImplementedError
