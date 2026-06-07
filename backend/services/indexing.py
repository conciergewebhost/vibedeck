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
from services.parser import VALID_VISIBILITIES, parse_deck


def slugify(value: str) -> str:
    """Lowercase, hyphen-separated slug (matches the URL slug convention)."""
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def deck_filename(meta: dict) -> str:
    """Deterministic canonical filename from deck frontmatter.

    topic + title slugs keep it unique and human-readable; re-saving the same
    deck (same topic + title) lands on the same file, refreshing it in place.
    Never derived from a user-supplied upload filename.
    """
    return f"{slugify(str(meta['topic']))}__{slugify(str(meta['title']))}.md"


def _get_or_create_topic(db: Session, *, topic_field: str, theme: str) -> Topic:
    slug = slugify(topic_field)
    topic = db.scalar(select(Topic).where(Topic.slug == slug))
    if topic is None:
        # First deck in a topic seeds the topic's display name + signature
        # theme from that deck's frontmatter. Curating topic metadata beyond
        # this is a later concern.
        topic = Topic(slug=slug, display_name=topic_field, theme=theme)
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
        db, topic_field=str(meta["topic"]), theme=str(meta["theme"])
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

    db.flush()
    return deck
