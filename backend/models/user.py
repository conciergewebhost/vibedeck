"""User model.

Auth is baked into the schema from day one even though v1 exposes no
public login UI — only the upload endpoint is auth-gated. A user owns
the decks they upload (Deck.owner_id).

`handle` is the user's public namespace segment (/u/{handle}/...), chosen
at signup or derived from the email local-part. Immutable for now: deck
filenames are opaque pointers and URLs derive from this column at read
time, so a rename feature later only has to worry about external links.

`is_admin` grants the full admin surface (review queue, deck management,
user monitoring, trusted upload). The OWNER (the UPLOAD_OWNER_EMAIL
account) is admin by config fallback in services.auth.get_current_admin —
never by this flag — so the owner can't be locked out and promote/demote
(owner-only) never needs to touch the owner row.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, false, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # Public namespace segment (see module docstring). Slug-validated via
    # services.handles; reserved words blocked there.
    handle: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Updated each time a session token is issued (see services.auth.record_login).
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    decks: Mapped[list["Deck"]] = relationship(  # noqa: F821
        back_populates="owner"
    )
    themes: Mapped[list["Theme"]] = relationship(  # noqa: F821
        back_populates="owner"
    )
