"""Reports router — the public reader-report (takedown request) endpoint.

No auth required: any reader can report a deck. A signed-in reporter is
identified by their account (best-effort token decode), anonymous reporters
by client IP. Rate-limited per IP like the sandbox preview endpoint.
"""

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import User
from schemas.report import ReportAck, ReportInput
from services import reports as reports_service
from services.ratelimit import SlidingWindowLimiter, client_ip

router = APIRouter()

_WINDOW_SECONDS = 3600.0
_report_limiter = SlidingWindowLimiter()


def _optional_user(request: Request, db: Session) -> User | None:
    """Best-effort resolve of a signed-in reporter; anonymous is fine.

    Mirrors get_current_user's decode but never rejects — a bad/expired
    token just means the report files anonymously.
    """
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    try:
        payload = pyjwt.decode(
            header[7:], settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except pyjwt.PyJWTError:
        return None
    email = payload.get("sub")
    if not isinstance(email, str):
        return None
    user = db.scalar(select(User).where(User.email == email))
    return user if user is not None and user.is_active else None


@router.post("", response_model=ReportAck)
def report_deck(
    body: ReportInput,
    request: Request,
    db: Session = Depends(get_db),
) -> ReportAck:
    """File a report against a deck.

    Duplicates from the same reporter are silently accepted (no added
    weight), so the response never reveals report counts or thresholds.
    """
    ip = client_ip(request)
    allowed, retry_after = _report_limiter.hit(
        ip, settings.RATE_LIMIT_REPORTS_PER_HOUR, _WINDOW_SECONDS
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many reports. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    reporter = _optional_user(request, db)
    found = reports_service.file_report(
        db,
        deck_id=body.deck_id,
        reason=body.reason,
        detail=body.detail,
        reporter_id=reporter.id if reporter else None,
        reporter_ip=ip,
    )
    if not found:
        raise HTTPException(status_code=404, detail="Deck not found")
    db.commit()
    return ReportAck()
