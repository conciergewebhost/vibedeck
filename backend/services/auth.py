"""Authentication service — password hashing, JWT issuance, and the
`get_current_user` FastAPI dependency.

v1 exposes only what the auth-gated upload flow needs: an OAuth2 password
flow that mints a JWT bearer token, and a dependency that resolves the
current user from that token. There is no public registration UI — users
are provisioned out of band (see manage.py `create-user`).
"""

import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import User

# Distinguishes a short-lived magic link from a normal session token so the
# two can't be swapped: a magic link can't act as a session bearer token and
# a session token can't be replayed against /verify.
_MAGIC_PURPOSE = "magic"

# tokenUrl is relative to the server root; the auth router is at /api/auth.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/token")

# bcrypt hashes at most the first 72 bytes of the password.
_BCRYPT_MAX_BYTES = 72

_credentials_exc = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def _pw_bytes(plain: str) -> bytes:
    return plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_pw_bytes(plain), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a password, failing closed on any malformed stored hash."""
    try:
        return bcrypt.checkpw(_pw_bytes(plain), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_magic_token(email: str, is_signup: bool) -> str:
    """Mint a short-lived magic-link JWT (email + signup intent).

    Stateless by design: there is no token table. The link is valid until it
    expires (MAGIC_LINK_EXPIRE_MINUTES) rather than being strictly one-time.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.MAGIC_LINK_EXPIRE_MINUTES
    )
    payload = {
        "sub": email,
        "purpose": _MAGIC_PURPOSE,
        "signup": is_signup,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_magic_token(token: str) -> tuple[str, bool]:
    """Validate a magic-link token; return (email, is_signup) or raise.

    Verifies signature, expiry, and that this is actually a magic token
    (not a session token). Raises jwt.InvalidTokenError on any problem so
    callers can map it to a single 'invalid or expired' response.
    """
    payload = jwt.decode(
        token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )
    if payload.get("purpose") != _MAGIC_PURPOSE:
        raise jwt.InvalidTokenError("not a magic-link token")
    email = payload.get("sub")
    if not isinstance(email, str) or not email:
        raise jwt.InvalidTokenError("missing subject")
    return email, bool(payload.get("signup", False))


def get_or_create_passwordless_user(db: Session, email: str) -> User:
    """Return the user for `email`, creating a passwordless one if needed.

    Magic-link accounts have no usable password, but the schema requires a
    non-null hash, so we store the hash of a random secret no one knows —
    making password login impossible without a separate column.
    """
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            hashed_password=hash_password(secrets.token_urlsafe(32)),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """Return the user if the email/password are valid and active, else None."""
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    """Resolve the authenticated user from a bearer token, or raise 401."""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.PyJWTError:
        raise _credentials_exc

    email = payload.get("sub")
    if not isinstance(email, str):
        raise _credentials_exc

    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active:
        raise _credentials_exc
    return user
