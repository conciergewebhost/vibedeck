"""Admin monitoring queries (owner-only)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import Deck, ModerationEvent, User
from schemas.admin import AdminUserItem, ModerationSummary


def list_users(db: Session) -> list[AdminUserItem]:
    """All users, most recent account first, with deck count + last-deck date.

    Aggregates owned decks in one grouped query (outer join so users with no
    decks still appear, with deck_count 0 and last_deck_at None).
    """
    rows = db.execute(
        select(
            User.id,
            User.email,
            User.created_at,
            User.last_login_at,
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
        )
        for r in rows
    ]


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

    return ModerationSummary(
        queue_size=queue_size or 0,
        blocked_24h=_events_since("block"),
        flagged_24h=_events_since("flag"),
    )
