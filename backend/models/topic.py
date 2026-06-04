"""Topic model — a first-class grouping, not just a string column.

A topic owns its display name, slug, description, and signature theme,
per the spec ("each topic can have a signature theme"). Decks reference
a topic by FK. The slug is the URL segment: /{topic}/...
"""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(500), default=None)
    # Signature theme for the topic; individual decks may still override
    # via their own `theme` frontmatter field.
    theme: Mapped[str | None] = mapped_column(String(120), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    decks: Mapped[list["Deck"]] = relationship(  # noqa: F821
        back_populates="topic"
    )
