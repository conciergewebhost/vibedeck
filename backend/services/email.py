"""Email delivery with three interchangeable backends.

Which backend runs is auto-detected from settings (settings.email_delivery):

- "resend" — Resend's HTTP API, called directly with httpx rather than their
  SDK (the payload is trivial and this avoids another dependency). The
  from-address domain must be verified in Resend or sends are rejected.
- "smtp"   — any SMTP server via the stdlib, for self-hosters without a
  Resend account (Mailgun, a Gmail app password, local Postfix, …).
- "log"    — no provider configured: the plain-text body (which contains the
  magic link) is written to the server log. This keeps zero-email
  deployments usable — the operator copies the link from journalctl.

All sends are synchronous, one message at a time.
"""

import logging
import smtplib
from email.message import EmailMessage

import httpx

from config import settings

logger = logging.getLogger(__name__)

_RESEND_ENDPOINT = "https://api.resend.com/emails"
_TIMEOUT_SECONDS = 10.0


def _send(to: str, subject: str, html: str, text: str) -> None:
    """Deliver one transactional email via the configured backend.

    `text` is the plain-text alternative; in log mode it's the only thing
    recorded, so it must carry everything the recipient needs (the link).
    """
    delivery = settings.email_delivery
    if delivery == "resend":
        _send_resend(to=to, subject=subject, html=html, text=text)
    elif delivery == "smtp":
        _send_smtp(to=to, subject=subject, html=html, text=text)
    else:
        _send_log(to=to, subject=subject, text=text)


def _send_resend(to: str, subject: str, html: str, text: str) -> None:
    """POST a single email to Resend; raise on failure."""
    payload = {
        "from": f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>",
        "to": [to],
        "subject": subject,
        "html": html,
        "text": text,
    }
    headers = {"Authorization": f"Bearer {settings.RESEND_API_KEY}"}
    resp = httpx.post(
        _RESEND_ENDPOINT, json=payload, headers=headers, timeout=_TIMEOUT_SECONDS
    )
    resp.raise_for_status()


def _send_smtp(to: str, subject: str, html: str, text: str) -> None:
    """Send one email through the configured SMTP server; raise on failure."""
    msg = EmailMessage()
    msg["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    # smtplib is referenced via the module so tests can monkeypatch
    # services.email.smtplib.SMTP with a recording fake.
    with smtplib.SMTP(
        settings.SMTP_HOST, settings.SMTP_PORT, timeout=_TIMEOUT_SECONDS
    ) as server:
        if settings.SMTP_TLS:
            server.starttls()
        if settings.SMTP_USERNAME:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.send_message(msg)


def _send_log(to: str, subject: str, text: str) -> None:
    """No email provider configured: record the message in the server log.

    WARNING level so the line survives conservative logging configs — for a
    zero-email deployment this IS the delivery channel, not diagnostics.
    """
    logger.warning(
        "Email delivery is in log mode (no provider configured). "
        "Message for %s — %s:\n%s",
        to,
        subject,
        text,
    )


def send_magic_link(to: str, link: str, is_signup: bool) -> None:
    """Email a one-click sign-in link.

    The copy differs slightly for first-time signups vs. returning logins,
    but both carry the same kind of short-lived magic link.
    """
    if is_signup:
        subject = "Confirm your Vibedeck account"
        intro = (
            "Welcome to Vibedeck. Click the button below to confirm your email "
            "and finish creating your account."
        )
        cta = "Confirm and sign in"
    else:
        subject = "Your Vibedeck sign-in link"
        intro = "Click the button below to sign in to Vibedeck."
        cta = "Sign in"

    expires = settings.MAGIC_LINK_EXPIRE_MINUTES
    html = f"""\
<div style="font-family:system-ui,sans-serif;max-width:32rem;margin:0 auto;line-height:1.6;color:#222">
  <h1 style="font-size:1.25rem;margin:0 0 1rem">Vibedeck</h1>
  <p style="margin:0 0 1.25rem">{intro}</p>
  <p style="margin:0 0 1.5rem">
    <a href="{link}"
       style="display:inline-block;background:#c0392b;color:#fff;text-decoration:none;
              padding:0.7rem 1.4rem;border-radius:6px;font-weight:600">{cta}</a>
  </p>
  <p style="margin:0 0 0.5rem;font-size:0.85rem;color:#666">
    This link expires in {expires} minutes. If you didn't request it, you can ignore this email.
  </p>
  <p style="margin:0;font-size:0.8rem;color:#999;word-break:break-all">{link}</p>
</div>"""

    text = (
        f"{intro}\n\n"
        f"{cta}: {link}\n\n"
        f"This link expires in {expires} minutes. "
        "If you didn't request it, you can ignore this email.\n"
    )

    _send(to=to, subject=subject, html=html, text=text)


def send_moderation_digest(
    to: str,
    queue_size: int,
    blocked_24h: int,
    flagged_24h: int,
    open_reports: int = 0,
    reports_24h: int = 0,
    signups_24h: int = 0,
) -> None:
    """Email the daily moderation digest to the admin.

    Sent every day regardless of counts — a steady heartbeat that also
    confirms the digest job itself is alive (see jobs/daily_digest.py).
    """
    quiet = (
        queue_size == 0
        and blocked_24h == 0
        and flagged_24h == 0
        and open_reports == 0
    )
    subject = (
        "Vibedeck moderation: all quiet"
        if quiet
        else f"Vibedeck moderation: {queue_size} awaiting review"
    )
    queue_url = f"{settings.BASE_URL.rstrip('/')}/admin"

    html = f"""\
<div style="font-family:system-ui,sans-serif;max-width:32rem;margin:0 auto;line-height:1.6;color:#222">
  <h1 style="font-size:1.25rem;margin:0 0 1rem">Vibedeck — daily moderation digest</h1>
  <table style="border-collapse:collapse;margin:0 0 1.25rem">
    <tr><td style="padding:0.3rem 1rem 0.3rem 0">Flagged decks awaiting review</td>
        <td style="padding:0.3rem 0;font-weight:700">{queue_size}</td></tr>
    <tr><td style="padding:0.3rem 1rem 0.3rem 0">Decks with standing reader reports</td>
        <td style="padding:0.3rem 0;font-weight:700">{open_reports}</td></tr>
    <tr><td style="padding:0.3rem 1rem 0.3rem 0">Blocked in the last 24&nbsp;h</td>
        <td style="padding:0.3rem 0;font-weight:700">{blocked_24h}</td></tr>
    <tr><td style="padding:0.3rem 1rem 0.3rem 0">Newly flagged in the last 24&nbsp;h</td>
        <td style="padding:0.3rem 0;font-weight:700">{flagged_24h}</td></tr>
    <tr><td style="padding:0.3rem 1rem 0.3rem 0">Reports filed in the last 24&nbsp;h</td>
        <td style="padding:0.3rem 0;font-weight:700">{reports_24h}</td></tr>
    <tr><td style="padding:0.3rem 1rem 0.3rem 0">New accounts in the last 24&nbsp;h</td>
        <td style="padding:0.3rem 0;font-weight:700">{signups_24h}</td></tr>
  </table>
  <p style="margin:0 0 1.5rem">
    <a href="{queue_url}"
       style="display:inline-block;background:#c0392b;color:#fff;text-decoration:none;
              padding:0.7rem 1.4rem;border-radius:6px;font-weight:600">Open the review queue</a>
  </p>
  <p style="margin:0;font-size:0.8rem;color:#999">
    Sent daily by the Vibedeck moderation digest job.
  </p>
</div>"""

    text = (
        "Vibedeck — daily moderation digest\n\n"
        f"Flagged decks awaiting review: {queue_size}\n"
        f"Decks with standing reader reports: {open_reports}\n"
        f"Blocked in the last 24 h: {blocked_24h}\n"
        f"Newly flagged in the last 24 h: {flagged_24h}\n"
        f"Reports filed in the last 24 h: {reports_24h}\n"
        f"New accounts in the last 24 h: {signups_24h}\n\n"
        f"Review queue: {queue_url}\n"
    )

    _send(to=to, subject=subject, html=html, text=text)
