"""Topic model — a first-class grouping, not just a string column.

A topic owns its display name, slug, description, and signature theme,
per the spec ("each topic can have a signature theme"). Decks reference
a topic by FK.

Topics are OWNER-SCOPED (per-user spaces): the slug is unique per owner,
not globally — two users can each have an "astrology" topic. The URL
segment is /u/{owner.handle}/{slug}/... in the server edition and
/{slug}/... in standalone (where there is effectively one owner).
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (
        UniqueConstraint("owner_id", "slug", name="uq_topics_owner_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(500), default=None)
    # Signature theme for the topic; individual decks may still override
    # via their own `theme` frontmatter field.
    theme: Mapped[str | None] = mapped_column(String(120), default=None)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    owner: Mapped["User"] = relationship()  # noqa: F821
    decks: Mapped[list["Deck"]] = relationship(  # noqa: F821
        back_populates="topic"
    )
