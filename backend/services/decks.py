"""Decks service — retrieve a deck and re-parse its cards on read.

The DB row locates the canonical file; the parser turns that file into
cards every read. This means editing a file is reflected immediately,
with no card data to sync in the DB.
"""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from models import Deck, Topic
from schemas.deck import Card, DeckDetail
from services.parser import parse_deck


def get_deck(db: Session, topic_slug: str, deck_slug: str) -> DeckDetail | None:
    """Return deck metadata + freshly parsed cards, or None if not found."""
    deck = db.scalar(
        select(Deck)
        .join(Topic, Deck.topic_id == Topic.id)
        .where(Topic.slug == topic_slug, Deck.slug == deck_slug)
    )
    if deck is None:
        return None

    path = Path(settings.UPLOAD_DIR) / deck.filename
    parsed = parse_deck(path.read_text(encoding="utf-8"))
    cards = [Card(type=c.type, meta=c.meta, body=c.body) for c in parsed.cards]

    return DeckDetail(
        slug=deck.slug,
        title=deck.title,
        author=deck.author,
        description=deck.description,
        topic=topic_slug,
        theme=deck.theme,
        keywords=[k.value for k in deck.keywords],
        cards=cards,
    )
