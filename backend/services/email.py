"""Email delivery via the Resend HTTP API.

Kept deliberately small: one synchronous POST per send. We call Resend's
REST endpoint directly with httpx rather than pulling in their SDK — the
payload is trivial and this avoids another dependency.

The sender identity comes from EMAIL_FROM_NAME/EMAIL_FROM_ADDRESS; the
from-address domain must be verified in Resend or sends are rejected.
"""

import httpx

from config import settings

_RESEND_ENDPOINT = "https://api.resend.com/emails"
_TIMEOUT_SECONDS = 10.0


def _send(to: str, subject: str, html: str) -> None:
    """POST a single transactional email to Resend; raise on failure."""
    payload = {
        "from": f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>",
        "to": [to],
        "subject": subject,
        "html": html,
    }
    headers = {"Authorization": f"Bearer {settings.RESEND_API_KEY}"}
    resp = httpx.post(
        _RESEND_ENDPOINT, json=payload, headers=headers, timeout=_TIMEOUT_SECONDS
    )
    resp.raise_for_status()


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

    _send(to=to, subject=subject, html=html)
