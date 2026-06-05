"""Decks router — auth-gated upload and reader retrieval.

Upload validates the markdown by parsing it BEFORE writing anything, then
stores the canonical file under UPLOAD_DIR and indexes its metadata.
Retrieval re-parses the canonical file into cards on read.
"""

from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import User
from schemas.deck import AdminDeckItem, DeckDetail, UploadResult
from services import decks as decks_service
from services.auth import get_current_user
from services.indexing import index_deck_file, slugify
from services.parser import DeckParseError, parse_deck

router = APIRouter()


@router.post("/upload", response_model=UploadResult, status_code=status.HTTP_201_CREATED)
async def upload_deck(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UploadResult:
    """Validate, store, and index an uploaded markdown deck (auth required)."""
    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deck file must be UTF-8 encoded text.",
        )

    # Validate by parsing before we write anything to disk.
    try:
        parsed = parse_deck(text)
    except DeckParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Malformed deck: {exc}",
        )

    meta = parsed.meta
    # Generate a safe filename from frontmatter (never trust the upload's
    # own filename). topic + title slugs keep it unique and human-readable;
    # re-uploading the same deck refreshes it in place.
    filename = f"{slugify(str(meta['topic']))}__{slugify(str(meta['title']))}.md"

    path = Path(settings.UPLOAD_DIR) / filename
    path.write_text(text, encoding="utf-8")

    deck = index_deck_file(db, filename=filename, owner_id=current_user.id)
    db.commit()

    return UploadResult(
        topic=deck.topic.slug,
        slug=deck.slug,
        title=deck.title,
        card_count=deck.card_count,
        url=f"/{deck.topic.slug}/{deck.slug}",
    )


@router.get("", response_model=list[AdminDeckItem])
def list_decks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # auth gate
) -> list[AdminDeckItem]:
    """List all indexed decks (auth required) — for the admin surface."""
    return decks_service.list_all_decks(db)


@router.get("/{topic_slug}/{deck_slug}", response_model=DeckDetail)
def get_deck(
    topic_slug: str, deck_slug: str, db: Session = Depends(get_db)
) -> DeckDetail:
    """Return deck metadata + parsed cards for the reader."""
    deck = decks_service.get_deck(db, topic_slug, deck_slug)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    return deck


@router.delete("/{topic_slug}/{deck_slug}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deck(
    topic_slug: str,
    deck_slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # auth gate
) -> Response:
    """Delete a deck: file + DB rows + orphan prune (auth required)."""
    deleted = decks_service.delete_deck_by_slugs(db, topic_slug, deck_slug)
    if not deleted:
        raise HTTPException(status_code=404, detail="Deck not found")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
