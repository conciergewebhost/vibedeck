"""Decks router — upload, retrieval, and parsed card delivery.

STUB: endpoints scaffolded. Upload is auth-gated and delegates to the
upload service (validate frontmatter -> store file -> index metadata).
Retrieval re-parses the canonical file into cards on read.
"""

from fastapi import APIRouter

router = APIRouter()


@router.post("/upload")
def upload_deck() -> dict:
    """Accept a markdown deck, validate, store, and index. (Not implemented.)"""
    raise NotImplementedError


@router.get("/{topic_slug}/{deck_slug}")
def get_deck(topic_slug: str, deck_slug: str) -> dict:
    """Return deck metadata + parsed cards for the reader. (Not implemented.)"""
    raise NotImplementedError
