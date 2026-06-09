"""Decks router — auth-gated upload and reader retrieval.

Upload validates the markdown by parsing it BEFORE writing anything, then
stores the canonical file under UPLOAD_DIR and indexes its metadata.
Retrieval re-parses the canonical file into cards on read.
"""

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from database import get_db
from models import User
from schemas.deck import (
    AdminDeckItem,
    Card,
    DeckDetail,
    DeckSource,
    PreviewInput,
    PublicDeckItem,
    SaveDeckInput,
    UploadResult,
)
from services import decks as decks_service
from services.auth import get_current_admin, get_current_user
from services.decks import (
    DeckBlocked,
    DeckConflict,
    DeckTooLarge,
    DeckUnsafe,
)
from services.parser import DeckParseError, parse_deck
from services.ratelimit import SlidingWindowLimiter, client_ip

router = APIRouter()

# Reject oversized sandbox input outright — decks are small documents.
_PREVIEW_MAX_BYTES = 100_000

# The public, unauthenticated /preview endpoint is rate-limited per client IP
# to bound abuse. The editor's live preview reaches it via the SSR server
# (a loopback call with no X-Forwarded-For), which is exempt — only direct
# external traffic (proxied by Caddy, so XFF is present) is throttled.
_preview_limiter = SlidingWindowLimiter()
_PREVIEW_MAX_PER_MIN = 60


@router.post("/upload", response_model=UploadResult, status_code=status.HTTP_201_CREATED)
async def upload_deck(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
) -> UploadResult:
    """Validate, store, and index an uploaded markdown deck (admin only).

    Delegates to create_user_deck so uploads get the same safety as the portal
    editor: a size cap, the no-code guard, and a cross-user conflict check (a
    user can't overwrite a deck owned by someone else).
    """
    raw = await file.read()
    if len(raw) > 256_000:  # bound memory/disk; see services.decks._MAX_DECK_BYTES
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Deck file is too large (256 KB max).",
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deck file must be UTF-8 encoded text.",
        )

    try:
        # moderated=False: this surface is admin-only and trusted; the portal
        # builder/editor paths below are the moderated ones.
        deck = decks_service.create_user_deck(
            db, current_user.id, text, moderated=False
        )
    except DeckTooLarge as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        )
    except DeckUnsafe as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except DeckParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Malformed deck: {exc}"
        )
    except DeckConflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A deck with this topic and title already exists.",
        )
    db.commit()

    return UploadResult(
        topic=deck.topic.slug,
        slug=deck.slug,
        title=deck.title,
        card_count=deck.card_count,
        url=f"/{deck.topic.slug}/{deck.slug}",
    )


@router.post("/preview", response_model=DeckDetail)
def preview_deck(body: PreviewInput, request: Request) -> DeckDetail:
    """Parse raw deck markdown and return it as a DeckDetail — no persistence.

    Powers the public /sandbox: same parser as a real upload, so authors see
    exactly what they'd get (including the parser's error messages), but
    nothing is written to the DB or disk and no auth is required.
    """
    # Throttle direct external callers (they arrive via Caddy with an XFF
    # header); the SSR editor preview is a loopback call with no XFF, exempt.
    if request.headers.get("x-forwarded-for"):
        allowed, retry_after = _preview_limiter.hit(
            client_ip(request), _PREVIEW_MAX_PER_MIN, 60.0
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many preview requests. Please slow down.",
                headers={"Retry-After": str(retry_after)},
            )

    if len(body.markdown.encode("utf-8")) > _PREVIEW_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Deck is too large to preview.",
        )

    try:
        parsed = parse_deck(body.markdown)
    except DeckParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Malformed deck: {exc}",
        )

    meta = parsed.meta
    return DeckDetail(
        slug="sandbox",
        title=str(meta["title"]),
        author=str(meta["author"]),
        description=meta.get("description"),
        topic="sandbox",
        theme=str(meta["theme"]),
        keywords=[str(k) for k in meta["keywords"]],
        cards=[Card(type=c.type, meta=c.meta, body=c.body) for c in parsed.cards],
    )


@router.get("", response_model=list[AdminDeckItem])
def list_decks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),  # admin only
) -> list[AdminDeckItem]:
    """List all indexed decks (admin only) — for the admin surface."""
    return decks_service.list_all_decks(db)


@router.get("/public", response_model=list[PublicDeckItem])
def list_public_decks(db: Session = Depends(get_db)) -> list[PublicDeckItem]:
    """All decks for the public library grid (no auth)."""
    return decks_service.list_public_decks(db)


# ── Owner-scoped portal endpoints (session-authed, own decks only) ────────
# Registered before the public /{topic}/{deck} routes; "mine" + nested paths
# don't collide with the two-segment reader path.


@router.get("/mine", response_model=list[AdminDeckItem])
def list_my_decks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AdminDeckItem]:
    """List the decks owned by the current user."""
    return decks_service.list_user_decks(db, current_user.id)


@router.post("/mine", response_model=UploadResult, status_code=status.HTTP_201_CREATED)
def create_my_deck(
    body: SaveDeckInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UploadResult:
    """Create a new deck owned by the current user from raw markdown."""
    try:
        deck = decks_service.create_user_deck(db, current_user.id, body.markdown)
    except DeckTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    except DeckUnsafe as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except DeckBlocked as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except DeckParseError as exc:
        raise HTTPException(status_code=400, detail=f"Malformed deck: {exc}")
    except DeckConflict:
        raise HTTPException(
            status_code=409,
            detail="A deck with this topic and title already exists.",
        )
    db.commit()
    return UploadResult(
        topic=deck.topic.slug,
        slug=deck.slug,
        title=deck.title,
        card_count=deck.card_count,
        url=f"/{deck.topic.slug}/{deck.slug}",
        moderation_status=deck.moderation_status,
    )


@router.get("/mine/{topic_slug}/{deck_slug}", response_model=DeckSource)
def get_my_deck_source(
    topic_slug: str,
    deck_slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DeckSource:
    """Return an owned deck's raw markdown, for the editor."""
    markdown = decks_service.get_owned_deck_source(
        db, current_user.id, topic_slug, deck_slug
    )
    if markdown is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    return DeckSource(
        topic=topic_slug, slug=deck_slug, title=deck_slug, markdown=markdown
    )


@router.put("/mine/{topic_slug}/{deck_slug}", response_model=UploadResult)
def update_my_deck(
    topic_slug: str,
    deck_slug: str,
    body: SaveDeckInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UploadResult:
    """Replace an owned deck's markdown (handles a title/topic rename)."""
    try:
        deck = decks_service.update_user_deck(
            db, current_user.id, topic_slug, deck_slug, body.markdown
        )
    except DeckTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    except DeckUnsafe as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except DeckBlocked as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except DeckParseError as exc:
        raise HTTPException(status_code=400, detail=f"Malformed deck: {exc}")
    except DeckConflict:
        raise HTTPException(
            status_code=409,
            detail="You already have a deck with this topic and title.",
        )
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    db.commit()
    return UploadResult(
        topic=deck.topic.slug,
        slug=deck.slug,
        title=deck.title,
        card_count=deck.card_count,
        url=f"/{deck.topic.slug}/{deck.slug}",
        moderation_status=deck.moderation_status,
    )


@router.delete("/mine/{topic_slug}/{deck_slug}", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_deck(
    topic_slug: str,
    deck_slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Delete an owned deck (file + index)."""
    deleted = decks_service.delete_user_deck(
        db, current_user.id, topic_slug, deck_slug
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Deck not found")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{topic_slug}/{deck_slug}/theme.css")
def get_deck_theme(
    topic_slug: str, deck_slug: str, db: Session = Depends(get_db)
) -> Response:
    """The CSS of a deck's custom theme, for any reader (no auth).

    Lets the reader inline a deck's custom theme server-side so every viewer
    sees it — not just the signed-in owner. Returns 404 for built-in themes or
    decks with no matching custom theme. (When per-deck visibility lands, this
    should honour it; today all decks are public.)
    """
    css = decks_service.get_deck_theme_css(db, topic_slug, deck_slug)
    if css is None:
        raise HTTPException(status_code=404, detail="No custom theme for this deck")
    return Response(content=css, media_type="text/css")


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
    current_user: User = Depends(get_current_admin),  # admin only (any deck)
) -> Response:
    """Delete any deck: file + DB rows + orphan prune (admin only)."""
    deleted = decks_service.delete_deck_by_slugs(db, topic_slug, deck_slug)
    if not deleted:
        raise HTTPException(status_code=404, detail="Deck not found")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
