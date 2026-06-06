"""Deck-related API schemas.

A DeckDetail carries the deck metadata plus the cards parsed from the
canonical file on read (card bodies are never stored in the DB).
"""

from pydantic import BaseModel


class Card(BaseModel):
    type: str
    meta: dict
    body: str  # raw markdown; rendered at the frontend layer


class PreviewInput(BaseModel):
    """Body for the public sandbox preview (POST /api/decks/preview).

    Raw deck markdown that is parsed and returned as a DeckDetail without
    ever touching the DB or filesystem.
    """

    markdown: str


class SaveDeckInput(BaseModel):
    """Body for creating/replacing an owned deck from the portal editor."""

    markdown: str


class DeckSource(BaseModel):
    """An owned deck's raw markdown, for loading into the portal editor."""

    topic: str
    slug: str
    title: str
    markdown: str


class DeckListItem(BaseModel):
    """A deck as it appears in a topic listing."""

    slug: str
    title: str
    author: str
    description: str | None = None
    theme: str
    keywords: list[str]
    card_count: int


class DeckDetail(BaseModel):
    """A single deck for the reader: metadata + parsed cards."""

    slug: str
    title: str
    author: str
    description: str | None = None
    topic: str  # topic slug
    theme: str
    keywords: list[str]
    cards: list[Card]


class UploadResult(BaseModel):
    """Returned after a successful deck upload."""

    topic: str  # topic slug
    slug: str
    title: str
    card_count: int
    url: str  # reader path, e.g. /z13/the-12-houses


class AdminDeckItem(BaseModel):
    """A deck row for the admin management list.

    Only public-equivalent fields (title/author/topic/slug/card_count) plus
    the deterministically-derived filename — no owner or path info.
    """

    topic: str  # topic slug
    slug: str
    title: str
    author: str
    card_count: int
    filename: str
    url: str
