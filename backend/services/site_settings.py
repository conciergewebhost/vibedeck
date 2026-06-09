"""Runtime site settings — read/write the SiteSetting k-v store.

The signup gate lives here: whether an invite code is required at all, and
what the code is. Both default to the pre-feature `.env` behavior when
unset (required; NEW_USER_CODE), so a fresh clone or an un-migrated row
set behaves exactly as before.
"""

from sqlalchemy.orm import Session

from config import settings
from models import SiteSetting

REQUIRE_INVITE_CODE = "require_invite_code"
INVITE_CODE = "invite_code"


def get_setting(db: Session, key: str) -> str | None:
    row = db.get(SiteSetting, key)
    return row.value if row is not None else None


def set_setting(db: Session, key: str, value: str) -> None:
    """Upsert one setting. Caller commits."""
    row = db.get(SiteSetting, key)
    if row is None:
        db.add(SiteSetting(key=key, value=value))
    else:
        row.value = value
    db.flush()


def invite_code_required(db: Session) -> bool:
    """Whether new signups must present an invite code. Default: True."""
    return get_setting(db, REQUIRE_INVITE_CODE) != "false"


def invite_code(db: Session) -> str:
    """The effective invite code: runtime override, else NEW_USER_CODE."""
    return get_setting(db, INVITE_CODE) or settings.NEW_USER_CODE
