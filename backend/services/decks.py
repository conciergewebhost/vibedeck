"""Decks service — retrieve a deck and re-parse its cards on read.

The DB row locates the canonical file; the parser turns that file into
cards every read. This means editing a file is reflected immediately,
with no card data to sync in the DB.
"""

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import settings
from models import Deck, Keyword, Topic, deck_keywords
from schemas.deck import AdminDeckItem, Card, DeckDetail
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


def list_all_decks(db: Session) -> list[AdminDeckItem]:
    """All indexed decks, for the admin management list."""
    decks = db.scalars(
        select(Deck).join(Topic, Deck.topic_id == Topic.id).order_by(
            Topic.slug, Deck.slug
        )
    ).all()
    return [
        AdminDeckItem(
            topic=d.topic.slug,
            slug=d.slug,
            title=d.title,
            author=d.author,
            card_count=d.card_count,
            filename=d.filename,
            url=f"/{d.topic.slug}/{d.slug}",
        )
        for d in decks
    ]


def delete_deck_by_slugs(db: Session, topic_slug: str, deck_slug: str) -> bool:
    """Delete a deck by its URL slugs. Returns False if not found.

    Removes the DB row, prunes now-orphaned keywords and the topic if it is
    left empty, and unlinks the canonical file. The caller owns the commit.
    """
    deck = db.scalar(
        select(Deck)
        .join(Topic, Deck.topic_id == Topic.id)
        .where(Topic.slug == topic_slug, Deck.slug == deck_slug)
    )
    if deck is None:
        return False
    _delete_deck(db, deck)
    return True


def _delete_deck(db: Session, deck: Deck) -> None:
    """Delete a resolved Deck: row (+cascade associations), orphan keywords,
    empty topic, then the file. Idempotent on the file. Caller commits."""
    topic_id = deck.topic_id
    keyword_ids = [k.id for k in deck.keywords]  # capture before delete
    filename = deck.filename

    db.delete(deck)  # deck_keywords association rows cascade (FK ondelete)
    db.flush()  # so the count queries below see the cascade

    _prune_orphan_keywords(db, keyword_ids)
    _prune_empty_topic(db, topic_id)

    # Unlink the canonical file last; tolerate an already-missing file so a
    # half-finished prior delete (or a CLI prune) is self-healing.
    path = Path(settings.UPLOAD_DIR) / filename
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _prune_orphan_keywords(db: Session, keyword_ids: list[int]) -> None:
    for kid in keyword_ids:
        remaining = db.scalar(
            select(func.count())
            .select_from(deck_keywords)
            .where(deck_keywords.c.keyword_id == kid)
        )
        if remaining == 0:
            kw = db.get(Keyword, kid)
            if kw is not None:
                db.delete(kw)
    db.flush()


def _prune_empty_topic(db: Session, topic_id: int) -> None:
    remaining = db.scalar(
        select(func.count()).select_from(Deck).where(Deck.topic_id == topic_id)
    )
    if remaining == 0:
        topic = db.get(Topic, topic_id)
        if topic is not None:
            db.delete(topic)
        db.flush()
