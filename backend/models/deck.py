"""Deck model + deck<->keyword association table.

IMPORTANT — storage model: the markdown file is the canonical source of
truth. This row is an INDEX of the frontmatter metadata for fast listing
and querying. Card *content* is NOT stored here; it is re-parsed from the
file on read. Editing a file therefore needs no DB sync for card bodies —
only a re-index if the frontmatter changed.

`card_count` is a denormalised convenience for index listings (the spec's
deck entries show a card count). It is computed once at upload/re-index
time so topic-list pages don't have to open and parse every file.
"""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

# Many-to-many: a deck has many keywords, a keyword tags many decks.
deck_keywords = Table(
    "deck_keywords",
    Base.metadata,
    Column("deck_id", ForeignKey("decks.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "keyword_id",
        ForeignKey("keywords.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Deck(Base):
    __tablename__ = "decks"

    id: Mapped[int] = mapped_column(primary_key=True)

    # URL identity: /{topic.slug}/{slug}. Slug generated from title at upload.
    # Unique per topic, not globally (enforced at the service layer in v1).
    slug: Mapped[str] = mapped_column(String(200), index=True)

    # Frontmatter-derived metadata (indexed copy of the file's truth).
    title: Mapped[str] = mapped_column(String(300))
    author: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(500), default=None)
    theme: Mapped[str] = mapped_column(String(120))

    # Visibility, from the file's frontmatter (defaults to public):
    #   public   — listed in the library + readable by anyone
    #   unlisted — readable by direct link, but kept out of all listings
    #   private  — owner-only (the public reader 404s it)
    visibility: Mapped[str] = mapped_column(
        String(12), default="public", server_default="public", index=True
    )

    # Moderation verdict from services.moderation (server edition only):
    #   approved — passed the checks (or moderation is off / admin approved)
    #   flagged  — suspicious; withheld from public view (treated like
    #              private on public read paths) until an admin approves
    # Blocked decks never get a row at all — they are rejected at submit.
    moderation_status: Mapped[str] = mapped_column(
        String(12), default="approved", server_default="approved", index=True
    )
    # Human-readable reasons from the verdict, newline-joined; shown in the
    # admin review queue. Null when approved on first sight.
    moderation_reasons: Mapped[str | None] = mapped_column(Text, default=None)
    flagged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    # Pointer to the canonical file: an OPAQUE relative path under
    # UPLOAD_DIR. New decks land in per-owner subdirs ({handle}/{topic}__
    # {title}.md); legacy flat filenames stay valid forever and migrate
    # lazily on edit (or via `manage.py tidy`). Never derived back from —
    # identity is (owner, topic.slug, slug).
    filename: Mapped[str] = mapped_column(String(512), unique=True)

    # Denormalised card count for listings (see module docstring).
    card_count: Mapped[int] = mapped_column(Integer, default=0)

    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    topic: Mapped["Topic"] = relationship(back_populates="decks")  # noqa: F821
    owner: Mapped["User"] = relationship(back_populates="decks")  # noqa: F821
    keywords: Mapped[list["Keyword"]] = relationship(  # noqa: F821
        secondary=deck_keywords, back_populates="decks"
    )
