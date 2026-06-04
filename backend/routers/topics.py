"""Topics router — master index and per-topic deck listings.

STUB: endpoints scaffolded; queries delegate to a topics service.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("")
def list_topics() -> list[dict]:
    """Master index: all topics with deck counts. (Not implemented.)"""
    raise NotImplementedError


@router.get("/{topic_slug}")
def get_topic(topic_slug: str) -> dict:
    """A topic and the decks within it. (Not implemented.)"""
    raise NotImplementedError
