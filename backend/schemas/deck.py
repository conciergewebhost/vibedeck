"""Deck-related API schemas.

A DeckDetail carries the deck metadata plus the cards parsed from the
canonical file on read (card bodies are never stored in the DB).
"""

from datetime import datetime

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
    url: str = ""  # canonical reader path (edition-shaped; see services/urls.py)


class DeckDetail(BaseModel):
    """A single deck for the reader: metadata + parsed cards."""

    id: int = 0  # deck row id (0 for sandbox previews); used by /api/reports
    slug: str
    title: str
    author: str
    description: str | None = None
    topic: str  # topic slug
    theme: str
    visibility: str = "public"
    keywords: list[str]
    cards: list[Card]
    # Canonical reader path + owner namespace; empty/None for the sandbox
    # preview, which never touches a deck row.
    url: str = ""
    owner_handle: str | None = None


class UploadResult(BaseModel):
    """Returned after a successful deck upload."""

    topic: str  # topic slug
    slug: str
    title: str
    card_count: int
    url: str  # reader path, e.g. /z13/the-12-houses
    # "flagged" when moderation quarantined the deck pending admin review —
    # the portal tells the author instead of linking to a 404ing reader URL.
    moderation_status: str = "approved"


class PublicDeckItem(BaseModel):
    """A deck for the public library grid (grouped by topic). No owner/path
    info; ownership-gated actions are resolved client-side."""

    id: int = 0  # deck row id; used by /api/reports
    topic: str  # topic slug
    topic_name: str  # topic display name (section header)
    slug: str
    title: str
    author: str
    card_count: int
    url: str
    owner_handle: str | None = None
    keywords: list[str] = []  # for the library's keyword filter bar
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AdminDeckItem(BaseModel):
    """A deck row for the admin management list.

    Only public-equivalent fields (title/author/topic/slug/card_count) plus
    the deterministically-derived filename — no owner or path info.
    """

    id: int = 0  # deck row id — the collision-proof key for admin actions
    topic: str  # topic slug
    slug: str
    title: str
    author: str
    card_count: int
    filename: str
    url: str
    owner_handle: str | None = None
    visibility: str = "public"
    created_at: datetime | None = None
    updated_at: datetime | None = None
    owner_email: str | None = None  # populated for the admin all-decks list
    moderation_status: str = "approved"
    moderation_reasons: str | None = None  # newline-joined verdict reasons
    flagged_at: datetime | None = None  # populated for the review queue
