"""Auth router — JWT token issuance (OAuth2 password flow).

The form field `username` carries the user's email.
"""

import hmac

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import User
from schemas.auth import (
    MessageOut,
    RequestLinkInput,
    Token,
    UploadTokenRequest,
    VerifyInput,
)
from services.auth import (
    AccountDisabled,
    authenticate_user,
    create_access_token,
    create_magic_token,
    decode_magic_token,
    get_or_create_passwordless_user,
    record_login,
)
from services.handles import HandleInvalid, validate_handle
from services.email import send_magic_link
from services.ratelimit import SlidingWindowLimiter, client_ip

router = APIRouter()

_WINDOW_SECONDS = 3600.0
# Per-IP limiters for the magic-link request endpoint. Module-level so they
# persist across requests within the (single) worker process.
_link_limiter = SlidingWindowLimiter()  # all request-link calls
_bad_code_limiter = SlidingWindowLimiter()  # only invalid-code signup attempts


def _too_many(retry_after: int, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
        headers={"Retry-After": str(retry_after)},
    )


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
    record_login(db, user)
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
    record_login(db, owner)
    return Token(access_token=create_access_token(subject=owner.email))


@router.post("/request-link", response_model=MessageOut)
def request_link(
    body: RequestLinkInput,
    request: Request,
    db: Session = Depends(get_db),
) -> MessageOut:
    """Email a magic sign-in link (passwordless).

    Returning users get a login link. Creating a *new* account requires the
    shared NEW_USER_CODE invite gate (testing phase); the user is only
    created later, when they click the link (see /verify).

    Rate limited per client IP to blunt invite-code brute-forcing and
    email-spam abuse (this endpoint sends an email on success).
    """
    ip = client_ip(request)

    # Overall per-IP cap on the endpoint (covers email-spam + hammering).
    allowed, retry_after = _link_limiter.hit(
        ip, settings.RATE_LIMIT_REQUESTS_PER_HOUR, _WINDOW_SECONDS
    )
    if not allowed:
        raise _too_many(retry_after, "Too many requests. Please try again later.")

    email = body.email.lower()
    user = db.scalar(select(User).where(User.email == email))

    # A deactivated (banned) account must not fall through to the signup
    # branch — that would mint a fresh magic link for a banned email.
    if user is not None and not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is disabled.",
        )

    handle: str | None = None  # only signups carry one
    if user is not None and user.is_active:
        is_signup = False
    else:
        # Unknown (or inactive) email → treat as signup, gated by the code.
        # Standalone is single-user: there is no public sign-up at all.
        if not settings.allow_public_signup:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="New account sign-up is disabled on this instance.",
            )
        expected = settings.NEW_USER_CODE.encode("utf-8")
        submitted = (body.code or "").encode("utf-8")
        if not hmac.compare_digest(submitted, expected):
            # Tighter, dedicated cap on invite-code guessing per IP.
            ok, code_retry = _bad_code_limiter.hit(
                ip, settings.RATE_LIMIT_BAD_CODE_PER_HOUR, _WINDOW_SECONDS
            )
            if not ok:
                raise _too_many(
                    code_retry,
                    "Too many invalid invite-code attempts. Please try again later.",
                )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="A valid invite code is required to create an account.",
            )
        # Signups choose their public handle up front; validate before
        # sending the email so the user gets immediate feedback. It is
        # re-validated at /verify (uniqueness can change in between).
        if not body.handle:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please choose a handle for your account.",
            )
        try:
            handle = validate_handle(db, body.handle)
        except HandleInvalid as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            )
        is_signup = True

    token = create_magic_token(email, is_signup=is_signup, handle=handle)
    link = f"{settings.BASE_URL}/auth/verify?token={token}"
    try:
        send_magic_link(to=email, link=link, is_signup=is_signup)
    except Exception:
        # Don't leak whether delivery failed for a specific address; the
        # email provider logs the detail. Surface a generic 502.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not send the sign-in email. Please try again shortly.",
        )

    return MessageOut(message="Check your email for your sign-in link.")


@router.post("/verify", response_model=Token)
def verify(body: VerifyInput, db: Session = Depends(get_db)) -> Token:
    """Exchange a magic-link token for a session JWT.

    Signup links create the account on first use; login links require an
    existing, active account.
    """
    try:
        email, is_signup, handle = decode_magic_token(body.token)
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This link is invalid or has expired.",
        )

    if is_signup:
        try:
            user = get_or_create_passwordless_user(db, email, handle or "")
        except AccountDisabled:
            # A banned email replaying an old signup link. Same generic
            # message as any dead link — no oracle for banned status here.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This link is invalid or has expired.",
            )
        except HandleInvalid as exc:
            # The handle was taken between requesting the link and clicking
            # it (or a stale/replayed link carries a bad one).
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{exc} Please sign up again.",
            )
    else:
        user = db.scalar(select(User).where(User.email == email))
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This link is invalid or has expired.",
            )

    record_login(db, user)
    return Token(access_token=create_access_token(subject=user.email))
