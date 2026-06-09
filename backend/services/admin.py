"""Admin monitoring queries + role management."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import settings
from models import Deck, ModerationEvent, Report, User
from schemas.admin import AdminUserItem, ModerationSummary, ReportedDeckItem
from services import reports as reports_service
from services.urls import deck_url


class RoleChangeForbidden(Exception):
    """The owner account's role can't be changed (it is admin by config)."""


class BanForbidden(Exception):
    """The ban/reactivate request violates the authz matrix; the message is
    user-facing. Carried as `status`: 400 for impossible targets (owner,
    self), 403 for insufficient rank (admin banning an admin)."""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


def list_users(db: Session) -> list[AdminUserItem]:
    """All users, most recent account first, with deck count + last-deck date.

    Aggregates owned decks in one grouped query (outer join so users with no
    decks still appear, with deck_count 0 and last_deck_at None). The owner
    row reports is_admin=True regardless of its flag (their adminship is
    config-derived) so the UI renders one consistent role badge.
    """
    rows = db.execute(
        select(
            User.id,
            User.email,
            User.created_at,
            User.last_login_at,
            User.is_admin,
            User.is_active,
            func.count(Deck.id).label("deck_count"),
            func.max(Deck.created_at).label("last_deck_at"),
        )
        .outerjoin(Deck, Deck.owner_id == User.id)
        .group_by(User.id)
        .order_by(User.created_at.desc(), User.id.desc())
    ).all()
    return [
        AdminUserItem(
            id=r.id,
            email=r.email,
            created_at=r.created_at,
            last_login_at=r.last_login_at,
            deck_count=r.deck_count,
            last_deck_at=r.last_deck_at,
            is_admin=r.is_admin or r.email == settings.UPLOAD_OWNER_EMAIL,
            is_owner=r.email == settings.UPLOAD_OWNER_EMAIL,
            is_active=r.is_active,
        )
        for r in rows
    ]


def set_admin(db: Session, user_id: int, value: bool) -> bool:
    """Set a user's is_admin flag. Returns False if the user doesn't exist.

    Raises RoleChangeForbidden for the owner account — its adminship comes
    from config (UPLOAD_OWNER_EMAIL), not the flag, so flipping the flag
    there would either be a no-op or sow confusion. Idempotent otherwise.
    Caller commits.
    """
    user = db.get(User, user_id)
    if user is None:
        return False
    if user.email == settings.UPLOAD_OWNER_EMAIL:
        raise RoleChangeForbidden()
    user.is_admin = value
    db.flush()
    return True


def moderation_summary(db: Session) -> ModerationSummary:
    """Counts for the admin surface + daily digest: current review-queue size
    and how many decks were blocked / newly flagged in the last 24 hours
    (from the moderation_events audit log, so the numbers hold even after
    the queue has been cleared)."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    queue_size = db.scalar(
        select(func.count())
        .select_from(Deck)
        .where(Deck.moderation_status == "flagged")
    )

    def _events_since(action: str) -> int:
        return db.scalar(
            select(func.count())
            .select_from(ModerationEvent)
            .where(
                ModerationEvent.action == action,
                ModerationEvent.created_at >= since,
            )
        )

    open_reports = db.scalar(
        select(func.count(func.distinct(Report.deck_id)))
    )
    reports_24h = db.scalar(
        select(func.count())
        .select_from(Report)
        .where(Report.created_at >= since)
    )
    signups_24h = db.scalar(
        select(func.count())
        .select_from(User)
        .where(User.created_at >= since)
    )

    return ModerationSummary(
        queue_size=queue_size or 0,
        blocked_24h=_events_since("block"),
        flagged_24h=_events_since("flag"),
        open_reports=open_reports or 0,
        reports_24h=reports_24h or 0,
        signups_24h=signups_24h or 0,
    )


def list_reported_decks(db: Session) -> list[ReportedDeckItem]:
    """Decks with standing reader reports, most-recently-reported first.

    Reports are grouped per deck with a distinct-reporter count and a
    reason breakdown; the row links to the deck via its id (the admin
    source/delete endpoints are id-based already).
    """
    deck_ids = db.scalars(select(Report.deck_id).distinct()).all()
    items: list[ReportedDeckItem] = []
    for deck_id in deck_ids:
        deck = db.get(Deck, deck_id)
        if deck is None:  # cascade should prevent this; belt-and-braces
            continue
        reports = db.scalars(
            select(Report)
            .where(Report.deck_id == deck_id)
            .order_by(Report.created_at.desc())
        ).all()
        reasons: dict[str, int] = {}
        for r in reports:
            reasons[r.reason] = reasons.get(r.reason, 0) + 1
        items.append(
            ReportedDeckItem(
                deck_id=deck.id,
                title=deck.title,
                url=deck_url(deck),
                owner_email=deck.owner.email if deck.owner else None,
                moderation_status=deck.moderation_status,
                report_count=reports_service.distinct_reporters(db, deck_id),
                reasons=reasons,
                details=[r.detail for r in reports if r.detail][:5],
                latest_at=reports[0].created_at,
            )
        )
    items.sort(key=lambda i: i.latest_at, reverse=True)
    return items


def set_active(db: Session, actor: User, user_id: int, value: bool) -> bool:
    """Deactivate (ban) or reactivate a user. Returns False if no such user.

    Matrix: the owner can't be touched (400 — their account is the
    instance), nobody bans themselves (400), and only the owner may ban or
    reactivate an admin (403 for mere admins). Content visibility follows
    is_active at read time, so a ban hides everything immediately and a
    reactivation restores it. Caller commits.
    """
    user = db.get(User, user_id)
    if user is None:
        return False
    if user.email == settings.UPLOAD_OWNER_EMAIL:
        raise BanForbidden("The owner account can't be deactivated.", 400)
    if user.id == actor.id:
        raise BanForbidden("You can't deactivate your own account.", 400)
    if user.is_admin and actor.email != settings.UPLOAD_OWNER_EMAIL:
        raise BanForbidden(
            "Only the owner can deactivate or reactivate an admin.", 403
        )
    user.is_active = value
    db.flush()
    return True
