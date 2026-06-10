"""Indexing service — register a deck file's metadata into the DB index.

The markdown file is the source of truth; this writes/refreshes the DB row
that indexes its frontmatter (for fast listing) plus a denormalised
card_count. Shared by the (future, auth-gated) upload endpoint and the dev
seed. Card bodies are never stored — they are re-parsed on read.

Callers own the transaction: this function flushes but does not commit.
"""

import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from models import Deck, Keyword, Topic
from services.parser import VALID_VISIBILITIES, DeckParseError, parse_deck


def slugify(value: str) -> str:
    """Lowercase, hyphen-separated slug (matches the URL slug convention)."""
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def deck_filename(meta: dict, owner_handle: str) -> str:
    """Deterministic canonical relative path from deck frontmatter + owner.

    Per-owner subdirectory + topic/title slugs keep it unique and
    human-readable; re-saving the same deck (same owner + topic + title)
    lands on the same file, refreshing it in place. Never derived from a
    user-supplied upload filename. Only used for NEW decks — existing rows
    keep their stored filename as an opaque pointer (legacy flat names
    included), so identity lookups must never re-derive this.
    """
    return f"{owner_handle}/{slugify(str(meta['topic']))}__{slugify(str(meta['title']))}.md"


# Topic slugs that routing shadows: /u/* is the user-space prefix and
# /embed/* the widget. (Other app routes like /decks or /account are
# shadowed too, but pre-date per-user spaces; the new prefixes are the ones
# this rework must not let users squat.)
_RESERVED_TOPIC_SLUGS = frozenset({"u", "embed"})


class TopicReserved(DeckParseError):
    """The topic slug collides with an app route prefix. Subclasses
    DeckParseError so every create/update/upload path reports it as a
    normal 400 validation error without new handling."""


def assert_topic_slug_allowed(slug: str) -> None:
    """Raise TopicReserved for route-shadowed topic slugs. Callers should
    check BEFORE writing the deck file so a rejection leaves no orphan."""
    if slug in _RESERVED_TOPIC_SLUGS:
        raise TopicReserved(
            f'"{slug}" can\'t be used as a topic name — it collides with a '
            "reserved address on this site. Please rename the topic."
        )


def _get_or_create_topic(
    db: Session, *, owner_id: int, topic_field: str, theme: str
) -> Topic:
    slug = slugify(topic_field)
    assert_topic_slug_allowed(slug)  # backstop; create/update check earlier
    # Topics are owner-scoped: each user has their own namespace of slugs.
    topic = db.scalar(
        select(Topic).where(Topic.owner_id == owner_id, Topic.slug == slug)
    )
    if topic is None:
        # First deck in a topic seeds the topic's display name + signature
        # theme from that deck's frontmatter. Curating topic metadata beyond
        # this is a later concern.
        topic = Topic(
            slug=slug, display_name=topic_field, theme=theme, owner_id=owner_id
        )
        db.add(topic)
        db.flush()
    return topic


def _sync_keywords(db: Session, values: list) -> list[Keyword]:
    keywords: list[Keyword] = []
    for raw in values:
        kw_slug = slugify(str(raw))
        if not kw_slug:
            continue
        kw = db.scalar(select(Keyword).where(Keyword.value == kw_slug))
        if kw is None:
            kw = Keyword(value=kw_slug)
            db.add(kw)
            db.flush()
        keywords.append(kw)
    return keywords


def index_deck_file(db: Session, *, filename: str, owner_id: int) -> Deck:
    """Parse the file under UPLOAD_DIR and upsert its DB index row.

    Upserts by filename (the stable identity of the canonical file), so
    re-indexing an edited file refreshes its metadata in place. Raises
    DeckParseError if the file is malformed.
    """
    path = Path(settings.UPLOAD_DIR) / filename
    parsed = parse_deck(path.read_text(encoding="utf-8"))
    meta = parsed.meta

    topic = _get_or_create_topic(
        db, owner_id=owner_id, topic_field=str(meta["topic"]), theme=str(meta["theme"])
    )

    deck = db.scalar(select(Deck).where(Deck.filename == filename))
    if deck is None:
        deck = Deck(filename=filename, owner_id=owner_id)
        db.add(deck)

    deck.slug = slugify(str(meta["title"]))
    deck.title = str(meta["title"])
    deck.author = str(meta["author"])
    deck.description = meta.get("description")
    deck.theme = str(meta["theme"])
    vis = str(meta.get("visibility", "public"))
    deck.visibility = vis if vis in VALID_VISIBILITIES else "public"
    deck.card_count = len(parsed.cards)
    deck.topic = topic
    deck.keywords = _sync_keywords(db, meta.get("keywords", []))
    # Searchable copy of everything reader-visible (see Deck.search_text).
    deck.search_text = "\n".join(
        [
            str(meta["title"]),
            str(meta["author"]),
            str(meta.get("description") or ""),
            " ".join(str(k) for k in meta.get("keywords") or []),
            *(card.body for card in parsed.cards),
        ]
    ).lower()

    db.flush()
    return deck
