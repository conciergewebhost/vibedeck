"""User model.

Auth is baked into the schema from day one even though v1 exposes no
public login UI — only the upload endpoint is auth-gated. A user owns
the decks they upload (Deck.owner_id).
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    decks: Mapped[list["Deck"]] = relationship(  # noqa: F821
        back_populates="owner"
    )
    themes: Mapped[list["Theme"]] = relationship(  # noqa: F821
        back_populates="owner"
    )
