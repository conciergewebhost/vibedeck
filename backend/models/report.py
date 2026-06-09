"""Reader reports — the takedown-request path.

One row per (deck, reporter) complaint. Reporters may be signed in
(reporter_id) or anonymous (deduped by reporter_ip); the distinct-reporter
count drives the auto-quarantine threshold (see services/reports.py).
Reports cascade away with their deck, are cleared when an admin approves
the deck (a ruling supersedes the standing complaints), and can be
dismissed wholesale from the admin Reports queue.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

# Reason categories offered by the report form.
REPORT_REASONS = frozenset({"spam", "harmful", "copyright", "other"})


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)

    deck_id: Mapped[int] = mapped_column(
        ForeignKey("decks.id", ondelete="CASCADE"), index=True
    )

    # Signed-in reporter, when there was one. SET NULL keeps the report (and
    # its IP-based dedupe identity) if the account goes away.
    reporter_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    # Client IP — the dedupe/distinct identity for anonymous reports.
    reporter_ip: Mapped[str] = mapped_column(String(64))

    reason: Mapped[str] = mapped_column(String(20))
    detail: Mapped[str | None] = mapped_column(String(500), default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    deck: Mapped["Deck"] = relationship()  # noqa: F821
