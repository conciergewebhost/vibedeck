"""Decks service — retrieve a deck and re-parse its cards on read.

The DB row locates the canonical file; the parser turns that file into
cards every read. This means editing a file is reflected immediately,
with no card data to sync in the DB.
"""

import re
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import settings
from models import Deck, Keyword, Topic, deck_keywords
from schemas.deck import AdminDeckItem, Card, DeckDetail, PublicDeckItem
from services.indexing import deck_filename, index_deck_file
from services.parser import parse_deck


class DeckConflict(Exception):
    """A different owner already holds the deck at the derived filename."""


class DeckNotOwned(Exception):
    """The deck exists but belongs to another user."""


class DeckUnsafe(Exception):
    """The deck markdown contains executable/code-like markup."""


# Blatant code constructs rejected at create/edit/upload time. This is a
# friendly early gate; the real protection is render-time HTML sanitization
# (frontend lib/markdown.ts). Safe markup like <a href … download> still
# passes — only scripts, embedders, and inline event handlers are blocked.
_UNSAFE_MARKUP = re.compile(
    r"<\s*(script|iframe|object|embed|style|link|meta|svg|math)\b"
    r"|javascript:"
    r"|\son[a-z]+\s*=\s*[\"']",
    re.IGNORECASE,
)


def assert_safe_markup(markdown: str) -> None:
    """Raise DeckUnsafe if the markdown carries code-like markup."""
    if _UNSAFE_MARKUP.search(markdown):
        raise DeckUnsafe(
            "For safety, decks can't include scripts, embedded frames, or "
            "inline event handlers. Plain markdown (and simple links) only."
        )


def _resolve_deck(db: Session, topic_slug: str, deck_slug: str) -> Deck | None:
    """Look up a Deck by its URL slugs, or None."""
    return db.scalar(
        select(Deck)
        .join(Topic, Deck.topic_id == Topic.id)
        .where(Topic.slug == topic_slug, Deck.slug == deck_slug)
    )


def get_deck(db: Session, topic_slug: str, deck_slug: str) -> DeckDetail | None:
    """Return deck metadata + freshly parsed cards, or None if not found."""
    deck = _resolve_deck(db, topic_slug, deck_slug)
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
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d in decks
    ]


def list_public_decks(db: Session) -> list[PublicDeckItem]:
    """All decks for the public library grid, with their topic display name.

    (No public/private flag exists yet, so this is every indexed deck; it will
    filter to public ones once that toggle lands.)
    """
    decks = db.scalars(
        select(Deck)
        .join(Topic, Deck.topic_id == Topic.id)
        .order_by(Topic.display_name, Deck.title)
    ).all()
    return [
        PublicDeckItem(
            topic=d.topic.slug,
            topic_name=d.topic.display_name,
            slug=d.slug,
            title=d.title,
            author=d.author,
            card_count=d.card_count,
            url=f"/{d.topic.slug}/{d.slug}",
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d in decks
    ]


def delete_deck_by_slugs(db: Session, topic_slug: str, deck_slug: str) -> bool:
    """Delete a deck by its URL slugs. Returns False if not found.

    Removes the DB row, prunes now-orphaned keywords and the topic if it is
    left empty, and unlinks the canonical file. The caller owns the commit.
    """
    deck = _resolve_deck(db, topic_slug, deck_slug)
    if deck is None:
        return False
    _delete_deck(db, deck)
    return True


# ── Owner-scoped operations (the per-user portal) ─────────────────────────
# These enforce that a deck belongs to the acting user, so a logged-in user
# can only see and mutate their own decks. The shared-token admin surface
# keeps using the unscoped helpers above.


def list_user_decks(db: Session, owner_id: int) -> list[AdminDeckItem]:
    """Decks owned by `owner_id`, for the user's portal list."""
    decks = db.scalars(
        select(Deck)
        .join(Topic, Deck.topic_id == Topic.id)
        .where(Deck.owner_id == owner_id)
        .order_by(Topic.slug, Deck.slug)
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
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d in decks
    ]


def get_owned_deck_source(
    db: Session, owner_id: int, topic_slug: str, deck_slug: str
) -> str | None:
    """Raw markdown of an owned deck, or None if it doesn't exist.

    Raises DeckNotOwned if the deck exists but belongs to someone else.
    """
    deck = _resolve_deck(db, topic_slug, deck_slug)
    if deck is None:
        return None
    if deck.owner_id != owner_id:
        raise DeckNotOwned()
    return (Path(settings.UPLOAD_DIR) / deck.filename).read_text(encoding="utf-8")


def create_user_deck(db: Session, owner_id: int, markdown: str) -> Deck:
    """Create a new deck owned by `owner_id` from raw markdown.

    Raises DeckParseError on malformed markdown, DeckUnsafe on code-like
    markup, and DeckConflict if the derived filename is already held by a
    different owner. Caller commits.
    """
    assert_safe_markup(markdown)  # raises DeckUnsafe
    parsed = parse_deck(markdown)  # raises DeckParseError
    filename = deck_filename(parsed.meta)

    existing = db.scalar(select(Deck).where(Deck.filename == filename))
    if existing is not None and existing.owner_id != owner_id:
        raise DeckConflict()

    (Path(settings.UPLOAD_DIR) / filename).write_text(markdown, encoding="utf-8")
    return index_deck_file(db, filename=filename, owner_id=owner_id)


def update_user_deck(
    db: Session, owner_id: int, topic_slug: str, deck_slug: str, markdown: str
) -> Deck | None:
    """Replace an owned deck's markdown. Returns None if it doesn't exist.

    If the new frontmatter changes the title/topic (and thus the canonical
    filename), the deck is effectively renamed: the new file is written and
    indexed, then the old file + rows are pruned. Raises DeckNotOwned if the
    deck belongs to someone else, DeckParseError on malformed markdown, and
    DeckConflict if the new filename collides with another owner's deck.
    Caller commits.
    """
    deck = _resolve_deck(db, topic_slug, deck_slug)
    if deck is None:
        return None
    if deck.owner_id != owner_id:
        raise DeckNotOwned()

    assert_safe_markup(markdown)  # raises DeckUnsafe
    old_filename = deck.filename
    parsed = parse_deck(markdown)  # raises DeckParseError
    new_filename = deck_filename(parsed.meta)

    if new_filename != old_filename:
        clash = db.scalar(select(Deck).where(Deck.filename == new_filename))
        if clash is not None and clash.owner_id != owner_id:
            raise DeckConflict()

    (Path(settings.UPLOAD_DIR) / new_filename).write_text(markdown, encoding="utf-8")
    updated = index_deck_file(db, filename=new_filename, owner_id=owner_id)

    if new_filename != old_filename:
        old = db.scalar(select(Deck).where(Deck.filename == old_filename))
        if old is not None:
            _delete_deck(db, old)
    return updated


def delete_user_deck(
    db: Session, owner_id: int, topic_slug: str, deck_slug: str
) -> bool:
    """Delete an owned deck. Returns False if not found.

    Raises DeckNotOwned if the deck belongs to someone else. Caller commits.
    """
    deck = _resolve_deck(db, topic_slug, deck_slug)
    if deck is None:
        return False
    if deck.owner_id != owner_id:
        raise DeckNotOwned()
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
