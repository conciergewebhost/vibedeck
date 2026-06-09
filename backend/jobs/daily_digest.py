"""Daily moderation digest — emails the admin the review-queue status.

Reports the current flagged-deck queue size plus how many decks were
blocked / newly flagged in the last 24 hours, and sends EVERY day even
when all counts are zero, so a missing email means the job (not the
moderation) is broken.

Run from backend/ as:  python -m jobs.daily_digest
Scheduled in production by a systemd timer (deploy/systemd/
vibedeck-digest.timer); server edition only — a standalone instance
exits without sending.
"""

import sys

from config import settings
from database import SessionLocal
from services import admin as admin_service
from services.email import send_moderation_digest


def main() -> int:
    if not settings.moderation_enabled:
        print("digest: moderation is off in this edition; nothing to send")
        return 0

    db = SessionLocal()
    try:
        summary = admin_service.moderation_summary(db)
    finally:
        db.close()

    to = settings.admin_digest_email
    send_moderation_digest(
        to=to,
        queue_size=summary.queue_size,
        blocked_24h=summary.blocked_24h,
        flagged_24h=summary.flagged_24h,
        open_reports=summary.open_reports,
        reports_24h=summary.reports_24h,
    )
    print(
        f"digest: sent to {to} — queue {summary.queue_size}, "
        f"blocked_24h {summary.blocked_24h}, flagged_24h {summary.flagged_24h}, "
        f"open_reports {summary.open_reports}, reports_24h {summary.reports_24h}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
