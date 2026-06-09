"""Reader reports — file complaints, auto-quarantine at the threshold.

A deck reported by REPORT_QUARANTINE_THRESHOLD distinct reporters (signed-in
users count by account, anonymous reporters by client IP) is quarantined via
the existing moderation pipeline: `moderation_status='flagged'` hides it from
all public reads and puts it in the admin Flagged review queue, where
Approve (which also clears the reports — a human ruling supersedes the
standing complaints) or Delete resolves it. Duplicate reports from the same
reporter are silent no-ops, and the endpoint is rate-limited per IP, so
quarantine takes genuinely distinct complainants.
"""

from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

from config import settings
from models import Deck, Report
from models.report import REPORT_REASONS
from services.decks import _apply_moderation, _log_moderation_event


def file_report(
    db: Session,
    *,
    deck_id: int,
    reason: str,
    detail: str | None,
    reporter_id: int | None,
    reporter_ip: str,
) -> bool:
    """Record a report; quarantine the deck at the distinct-reporter threshold.

    Returns False if the deck doesn't exist (router 404s). A duplicate from
    the same reporter (account, or IP for anonymous) is accepted silently
    without adding weight. Caller commits.
    """
    deck = db.get(Deck, deck_id)
    if deck is None:
        return False
    if reason not in REPORT_REASONS:  # schema validates too; belt-and-braces
        reason = "other"

    # Dedupe per reporter identity: an account reports once per deck, an
    # anonymous IP reports once per deck.
    if reporter_id is not None:
        dupe = db.scalar(
            select(Report).where(
                Report.deck_id == deck_id, Report.reporter_id == reporter_id
            )
        )
    else:
        dupe = db.scalar(
            select(Report).where(
                Report.deck_id == deck_id,
                Report.reporter_id.is_(None),
                Report.reporter_ip == reporter_ip,
            )
        )
    if dupe is not None:
        return True

    db.add(
        Report(
            deck_id=deck_id,
            reporter_id=reporter_id,
            reporter_ip=reporter_ip,
            reason=reason,
            detail=detail,
        )
    )
    db.flush()

    distinct = distinct_reporters(db, deck_id)
    if (
        distinct >= settings.REPORT_QUARANTINE_THRESHOLD
        and deck.moderation_status == "approved"
    ):
        reason_text = f"reported by {distinct} readers"
        _apply_moderation(deck, "flagged", reason_text)
        _log_moderation_event(db, deck.owner_id, "flag", [reason_text], deck.title)
        db.flush()
    return True


def distinct_reporters(db: Session, deck_id: int) -> int:
    """How many distinct reporters (accounts or anonymous IPs) a deck has."""
    return (
        db.scalar(
            select(
                func.count(
                    func.distinct(
                        func.coalesce(
                            cast(Report.reporter_id, String), Report.reporter_ip
                        )
                    )
                )
            ).where(Report.deck_id == deck_id)
        )
        or 0
    )


def clear_reports(db: Session, deck_id: int) -> int:
    """Delete all reports for a deck (admin dismiss / approve). Returns the
    number removed. Caller commits."""
    reports = db.scalars(select(Report).where(Report.deck_id == deck_id)).all()
    for r in reports:
        db.delete(r)
    db.flush()
    return len(reports)
