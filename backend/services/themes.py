"""Theme service — validate and store user-uploaded custom themes.

User themes are private to their owner. The CSS is validated on the way in
(the "no code"/safe-CSS rule) so that what we later serve and inject for the
owner can't carry scripts, HTML, external fetches, or legacy IE/Mozilla
code-execution vectors. This is allow/deny-list validation, not a full CSS
parser, but it blocks the dangerous constructs and the blast radius is bound
to the owner's own view (themes are never served to anyone else).
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Theme
from services.indexing import slugify

# Hard ceiling so a theme can't be used to bloat the DB / a page.
_MAX_CSS_BYTES = 64_000

# Constructs that can execute code, fetch external resources, or break out of
# the <style> context. Matched case-insensitively against the raw CSS.
_FORBIDDEN = [
    # Block `<` (no valid CSS uses it) to keep HTML/`</style>` out, but allow
    # `>` — it's the CSS child combinator (`.a > .b`) and can't form a tag.
    (r"<", "HTML tags are not allowed in a theme"),
    (r"@import", "@import is not allowed"),
    (r"javascript:", "javascript: URLs are not allowed"),
    (r"expression\s*\(", "expression() is not allowed"),
    (r"behavior\s*:", "behavior is not allowed"),
    (r"-moz-binding", "-moz-binding is not allowed"),
    # url(...) may only reference local/relative or data:image resources —
    # block javascript:, external http(s), and non-image data: URLs.
    (r"url\(\s*['\"]?\s*javascript:", "javascript: URLs are not allowed"),
    (r"url\(\s*['\"]?\s*https?:", "external url() is not allowed"),
    (r"url\(\s*['\"]?\s*data:(?!image/)", "non-image data: URLs are not allowed"),
]


class ThemeInvalid(Exception):
    """The uploaded CSS failed validation (unsafe or not a theme)."""


class ThemeConflict(Exception):
    """The user already has a theme with this slug."""


class ThemeNotFound(Exception):
    """No such theme for this owner."""


def validate_theme_css(css: str) -> None:
    """Raise ThemeInvalid unless `css` is safe theme CSS.

    A theme must define at least one `--vd-*` custom property (otherwise it's
    not a theme), stay under the size cap, and contain none of the forbidden
    code-execution / external-fetch constructs.
    """
    if not css or not css.strip():
        raise ThemeInvalid("The theme file is empty.")
    if len(css.encode("utf-8")) > _MAX_CSS_BYTES:
        raise ThemeInvalid("The theme file is too large.")

    lowered = css.lower()
    for pattern, message in _FORBIDDEN:
        if re.search(pattern, lowered):
            raise ThemeInvalid(message)

    if "--vd-" not in lowered:
        raise ThemeInvalid(
            "This doesn't look like a VibeDeck theme — it must define at least "
            "one --vd-* custom property."
        )


def create_user_theme(db: Session, owner_id: int, name: str, css: str) -> Theme:
    """Validate and store a new theme for `owner_id`. Caller commits.

    Raises ThemeInvalid on bad CSS and ThemeConflict if the slug is taken.
    """
    name = name.strip()
    if not name:
        raise ThemeInvalid("A theme name is required.")
    slug = slugify(name)
    if not slug:
        raise ThemeInvalid("The theme name must contain letters or numbers.")

    validate_theme_css(css)

    existing = db.scalar(
        select(Theme).where(Theme.owner_id == owner_id, Theme.slug == slug)
    )
    if existing is not None:
        raise ThemeConflict()

    theme = Theme(owner_id=owner_id, name=name, slug=slug, css=css)
    db.add(theme)
    db.flush()
    return theme


def list_user_themes(db: Session, owner_id: int) -> list[Theme]:
    """Themes owned by `owner_id`, newest first."""
    return list(
        db.scalars(
            select(Theme)
            .where(Theme.owner_id == owner_id)
            .order_by(Theme.name)
        ).all()
    )


def get_user_theme_css(db: Session, owner_id: int, slug: str) -> str | None:
    """Raw CSS of an owned theme, or None if the owner has no such theme."""
    theme = db.scalar(
        select(Theme).where(Theme.owner_id == owner_id, Theme.slug == slug)
    )
    return theme.css if theme is not None else None


def delete_user_theme(db: Session, owner_id: int, slug: str) -> bool:
    """Delete an owned theme. Returns False if not found. Caller commits."""
    theme = db.scalar(
        select(Theme).where(Theme.owner_id == owner_id, Theme.slug == slug)
    )
    if theme is None:
        return False
    db.delete(theme)
    return True
