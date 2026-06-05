"""Auth router — JWT token issuance (OAuth2 password flow).

The form field `username` carries the user's email.
"""

import hmac

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import User
from schemas.auth import Token, UploadTokenRequest
from services.auth import authenticate_user, create_access_token

router = APIRouter()


@router.post("/token", response_model=Token)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    """Exchange email (as `username`) + password for a JWT access token."""
    user = authenticate_user(db, form.username, form.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=create_access_token(subject=user.email))


@router.post("/upload-token", response_model=Token)
def upload_token(body: UploadTokenRequest, db: Session = Depends(get_db)) -> Token:
    """Exchange the shared UPLOAD_TOKEN for a JWT bound to the owner account.

    A third way to obtain the same JWT as the password flow (and, later, a
    magic link), so everything downstream is unchanged. Constant-time token
    comparison avoids a timing side-channel.
    """
    submitted = body.token.encode("utf-8")
    expected = settings.UPLOAD_TOKEN.encode("utf-8")
    if not hmac.compare_digest(submitted, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid upload token"
        )

    owner = db.scalar(
        select(User).where(User.email == settings.UPLOAD_OWNER_EMAIL)
    )
    if owner is None or not owner.is_active:
        # Misconfiguration: the configured owner account must exist & be active.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Owner account not provisioned",
        )
    return Token(access_token=create_access_token(subject=owner.email))
