"""Keyword model.

Keywords are thematic tags captured from deck frontmatter. The data is
stored in v1; the filtering UI is a v2 feature. Many-to-many with decks
via the `deck_keywords` association table (defined in models/deck.py).
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stored normalised: lowercase, hyphen-separated (e.g. "natal-chart").
    value: Mapped[str] = mapped_column(String(120), unique=True, index=True)

    decks: Mapped[list["Deck"]] = relationship(  # noqa: F821
        secondary="deck_keywords", back_populates="keywords"
    )
