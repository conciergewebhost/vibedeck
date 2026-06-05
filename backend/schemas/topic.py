"""Topic-related API schemas."""

from pydantic import BaseModel

from schemas.deck import DeckListItem


class TopicSummary(BaseModel):
    """A topic as it appears on the master index."""

    slug: str
    display_name: str
    description: str | None = None
    theme: str | None = None
    deck_count: int
    top_keywords: list[str]


class TopicDetail(BaseModel):
    """A topic and the decks within it."""

    slug: str
    display_name: str
    description: str | None = None
    theme: str | None = None
    decks: list[DeckListItem]
