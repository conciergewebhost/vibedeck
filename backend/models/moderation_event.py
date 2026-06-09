"""Moderation audit log.

One row per enforcement action. Blocked decks never reach the decks table
(they are rejected at submit time), so this log is the only durable record
that a block happened — the daily admin digest counts from here. Flag
events are logged too so the digest can report flagged-in-the-last-24h
even after an admin has already cleared the queue.

`owner_email` is snapshotted (not just the FK) so the audit trail survives
account deletion; the FK itself nulls out via ondelete.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class ModerationEvent(Base):
    __tablename__ = "moderation_events"

    id: Mapped[int] = mapped_column(primary_key=True)

    # "block" (deck rejected at submit) or "flag" (deck quarantined).
    action: Mapped[str] = mapped_column(String(12), index=True)

    # Newline-joined human-readable reasons from the verdict.
    reasons: Mapped[str] = mapped_column(Text)

    # Deck title from the submitted frontmatter — for blocks there is no
    # deck row to point at, so this is the identifying breadcrumb.
    deck_title: Mapped[str] = mapped_column(String(300))

    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    owner_email: Mapped[str] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
