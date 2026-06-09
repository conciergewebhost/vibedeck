"""User handles — the public namespace segment in /u/{handle}/... URLs.

A handle is chosen at signup (server edition) or derived from the email
local-part (existing users, via migration; CLI-provisioned accounts). It is
immutable for now: filenames are opaque pointers and URLs derive from the
users.handle join at read time, so a rename feature later is cheap — only
external links/embeds would break (solvable then with a handle-history
table).

The Alembic migration `add_user_handles_and_topic_owners` mirrors
`derive_handle` inline (migrations must not import app services); keep the
two in sync if the rules ever change.
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import User
from services.indexing import slugify

# 2-63 chars, lowercase alphanumerics + hyphens, no leading/trailing hyphen.
HANDLE_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_MIN_HANDLE_LEN = 2

# Handles that collide with app routes, API segments, or likely future
# pages. Checked at signup and by the migration's derivation.
RESERVED_HANDLES = frozenset(
    {
        "about",
        "account",
        "admin",
        "api",
        "assets",
        "auth",
        "decks",
        "embed",
        "favicon",
        "health",
        "help",
        "index",
        "login",
        "logout",
        "me",
        "meta",
        "mine",
        "preview",
        "privacy",
        "public",
        "robots",
        "rss",
        "sandbox",
        "search",
        "settings",
        "signup",
        "sitemap",
        "static",
        "support",
        "terms",
        "themes",
        "topics",
        "u",
        "upload",
        "users",
        "vibedeck",
        "well-known",
    }
)


class HandleInvalid(Exception):
    """The requested handle fails format/reserved/uniqueness rules."""


def normalize_handle(raw: str) -> str:
    return raw.strip().lower()


def validate_handle(db: Session, raw: str) -> str:
    """Return the normalized handle, or raise HandleInvalid with a reason."""
    handle = normalize_handle(raw)
    if len(handle) < _MIN_HANDLE_LEN or not HANDLE_RE.match(handle):
        raise HandleInvalid(
            "Handles are 2-63 characters: lowercase letters, numbers, and "
            "hyphens (no leading/trailing hyphen)."
        )
    if handle in RESERVED_HANDLES:
        raise HandleInvalid("That handle is reserved. Please pick another.")
    if db.scalar(select(User).where(User.handle == handle)) is not None:
        raise HandleInvalid("That handle is already taken. Please pick another.")
    return handle


def derive_handle(db: Session, email: str) -> str:
    """A free handle derived from the email local-part (for CLI provisioning).

    Slugified local-part, '-2'/'-3'... suffix on collision with existing or
    reserved handles. Mirrored inline by the namespace migration.
    """
    base = slugify(email.split("@", 1)[0])[:60] or "user"
    if not HANDLE_RE.match(base):
        base = "user"
    candidate = base
    n = 2
    while (
        candidate in RESERVED_HANDLES
        or db.scalar(select(User).where(User.handle == candidate)) is not None
    ):
        candidate = f"{base}-{n}"
        n += 1
    return candidate
