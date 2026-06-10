"""Decks service — retrieve a deck and re-parse its cards on read.

The DB row locates the canonical file; the parser turns that file into
cards every read. This means editing a file is reflected immediately,
with no card data to sync in the DB.
"""

import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from config import settings
from models import Deck, Keyword, ModerationEvent, Topic, User, deck_keywords
from schemas.deck import AdminDeckItem, Card, DeckDetail, PublicDeckItem
from services.auth import is_admin_user
from services.indexing import (
    assert_topic_slug_allowed,
    deck_filename,
    index_deck_file,
    slugify,
)
from services.moderation import moderate_deck
from services.parser import ParsedDeck, parse_deck
from services.themes import get_user_theme_css
from services.urls import deck_url


class DeckConflict(Exception):
    """The save would collide with another deck (the owner's own deck under
    the new topic+title on a rename, or — as a safety net — a different
    owner's file at the derived filename)."""


class DeckUnsafe(Exception):
    """The deck markdown contains executable/code-like markup."""


class DeckTooLarge(Exception):
    """The deck markdown exceeds the size limit."""


class DeckQuotaExceeded(Exception):
    """The owner is at their deck-count quota (server edition, non-admins)."""

    def __init__(self, limit: int):
        super().__init__(
            f"You've reached the limit of {limit} decks. Delete one to make "
            "room, or contact the site admin."
        )


class DeckBlocked(Exception):
    """Moderation judged the deck an egregious violation; nothing was saved."""

    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__(
            "This deck can't be published: " + "; ".join(reasons) + ". "
            "Edit the content and try again."
        )


# Decks are small documents; cap to bound memory/disk from any single upload.
_MAX_DECK_BYTES = 256_000


def assert_deck_size(markdown: str) -> None:
    """Raise DeckTooLarge if the markdown is over the size limit."""
    if len(markdown.encode("utf-8")) > _MAX_DECK_BYTES:
        raise DeckTooLarge("This deck is too large (256 KB max).")


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


def _log_moderation_event(
    db: Session, owner_id: int, action: str, reasons: list[str], deck_title: str
) -> None:
    """Append a moderation audit row (powers the daily admin digest)."""
    owner = db.get(User, owner_id)
    db.add(
        ModerationEvent(
            action=action,
            reasons="\n".join(reasons),
            deck_title=deck_title,
            owner_id=owner_id,
            owner_email=owner.email if owner else "",
        )
    )
    db.flush()


def _run_moderation(
    db: Session, owner_id: int, parsed: ParsedDeck, prev_status: str | None
) -> tuple[str, str | None]:
    """Moderate a parsed deck; return (moderation_status, reasons_text).

    Blocks log an audit event and raise DeckBlocked before anything is
    written. Flags log an audit event (only on the transition into flagged,
    so re-saving an already-flagged deck doesn't inflate the digest counts)
    and quarantine the deck. A clean verdict returns "approved" — including
    for a previously flagged deck, since the heuristics judge the current
    text and an author who removed the trigger has fixed the problem.
    """
    if not settings.moderation_enabled:
        return "approved", None

    title = str(parsed.meta.get("title") or "")
    verdict = moderate_deck(parsed)
    if verdict.action == "block":
        _log_moderation_event(db, owner_id, "block", verdict.reasons, title)
        db.commit()  # the request will fail; persist the audit row regardless
        raise DeckBlocked(verdict.reasons)
    if verdict.action == "flag":
        if prev_status != "flagged":
            _log_moderation_event(db, owner_id, "flag", verdict.reasons, title)
        return "flagged", "\n".join(verdict.reasons)
    return "approved", None


def _apply_moderation(deck: Deck, status: str, reasons: str | None) -> None:
    """Stamp a moderation verdict onto the deck row."""
    previously_flagged = deck.moderation_status == "flagged"
    deck.moderation_status = status
    deck.moderation_reasons = reasons
    if status == "flagged":
        if not previously_flagged or deck.flagged_at is None:
            deck.flagged_at = datetime.now(timezone.utc)
    else:
        deck.flagged_at = None


def _resolve_deck(db: Session, topic_slug: str, deck_slug: str) -> Deck | None:
    """Look up a Deck by FLAT slugs — only when the match is unambiguous.

    Topics are owner-scoped, so several owners can hold the same
    (topic_slug, deck_slug) pair. A flat lookup is only meaningful when
    exactly one deck matches; on 0 or ≥2 matches it returns None (a silent
    first-match would serve an arbitrary owner's deck). Flat URLs are
    canonical in standalone (single owner → always unique) and act as
    legacy redirects in the server edition.
    """
    matches = db.scalars(
        select(Deck)
        .join(Topic, Deck.topic_id == Topic.id)
        .where(Topic.slug == topic_slug, Deck.slug == deck_slug)
        .limit(2)
    ).all()
    return matches[0] if len(matches) == 1 else None


def _resolve_deck_namespaced(
    db: Session, handle: str, topic_slug: str, deck_slug: str
) -> Deck | None:
    """Look up a Deck by its canonical /u/{handle}/{topic}/{deck} identity."""
    return db.scalar(
        select(Deck)
        .join(Topic, Deck.topic_id == Topic.id)
        .join(User, Deck.owner_id == User.id)
        .where(
            User.handle == handle,
            Topic.slug == topic_slug,
            Deck.slug == deck_slug,
        )
    )


def _resolve_owned_deck(
    db: Session, owner_id: int, topic_slug: str, deck_slug: str
) -> Deck | None:
    """Look up a deck within ONE owner's namespace, or None.

    Topics are owner-scoped, so the same (topic_slug, deck_slug) pair can
    exist under several owners; the owner-portal paths must resolve with the
    owner in the WHERE clause, never globally-then-check.
    """
    return db.scalar(
        select(Deck)
        .join(Topic, Deck.topic_id == Topic.id)
        .where(
            Deck.owner_id == owner_id,
            Topic.slug == topic_slug,
            Deck.slug == deck_slug,
        )
    )


def get_deck(
    db: Session, topic_slug: str, deck_slug: str, handle: str | None = None
) -> DeckDetail | None:
    """Return deck metadata + freshly parsed cards, or None if not found.

    With `handle`, resolves in that owner's namespace (the canonical
    /u/{handle}/… reader); without, resolves flat — unique matches only.
    """
    if handle is not None:
        deck = _resolve_deck_namespaced(db, handle, topic_slug, deck_slug)
    else:
        deck = _resolve_deck(db, topic_slug, deck_slug)
    if deck is None:
        return None

    # Private decks are owner-only; the public reader treats them as missing.
    # Flagged decks are quarantined the same way until an admin approves,
    # and a banned (deactivated) owner's decks hide while the ban stands.
    if deck.visibility == "private" or deck.moderation_status == "flagged":
        return None
    if deck.owner is not None and not deck.owner.is_active:
        return None

    path = Path(settings.UPLOAD_DIR) / deck.filename
    parsed = parse_deck(path.read_text(encoding="utf-8"))
    cards = [Card(type=c.type, meta=c.meta, body=c.body) for c in parsed.cards]

    return DeckDetail(
        id=deck.id,
        slug=deck.slug,
        title=deck.title,
        author=deck.author,
        description=deck.description,
        topic=topic_slug,
        theme=deck.theme,
        visibility=deck.visibility,
        keywords=[k.value for k in deck.keywords],
        cards=cards,
        url=deck_url(deck),
        owner_handle=deck.owner.handle if deck.owner else None,
    )


def get_deck_theme_css(
    db: Session, topic_slug: str, deck_slug: str, handle: str | None = None
) -> str | None:
    """CSS of the custom theme a deck uses, or None.

    Resolves the deck → its owner + `theme` slug → that owner's theme CSS, so a
    deck's custom theme renders for ALL of its readers (not just the signed-in
    owner). A built-in theme name (or no matching theme row) yields None. The
    CSS was safety-validated when the theme was created; only a theme actually
    attached to a deck becomes visible this way.
    """
    if handle is not None:
        deck = _resolve_deck_namespaced(db, handle, topic_slug, deck_slug)
    else:
        deck = _resolve_deck(db, topic_slug, deck_slug)
    if deck is None:
        return None
    # Not publicly viewable (private, quarantined, or banned owner) → no
    # public CSS.
    if deck.visibility == "private" or deck.moderation_status == "flagged":
        return None
    if deck.owner is not None and not deck.owner.is_active:
        return None
    return get_user_theme_css(db, deck.owner_id, deck.theme)


def list_all_decks(db: Session) -> list[AdminDeckItem]:
    """All indexed decks, for the admin management list (incl. owner email)."""
    decks = db.scalars(
        select(Deck)
        .join(Topic, Deck.topic_id == Topic.id)
        .options(joinedload(Deck.owner))
        .order_by(Topic.slug, Deck.slug)
    ).all()
    return [
        AdminDeckItem(
            id=d.id,
            topic=d.topic.slug,
            slug=d.slug,
            title=d.title,
            author=d.author,
            card_count=d.card_count,
            filename=d.filename,
            url=deck_url(d),
            owner_handle=d.owner.handle if d.owner else None,
            visibility=d.visibility,
            created_at=d.created_at,
            updated_at=d.updated_at,
            owner_email=d.owner.email if d.owner else None,
            moderation_status=d.moderation_status,
            moderation_reasons=d.moderation_reasons,
        )
        for d in decks
    ]


def _public_deck_item(d: Deck) -> PublicDeckItem:
    return PublicDeckItem(
        id=d.id,
        topic=d.topic.slug,
        topic_name=d.topic.display_name,
        slug=d.slug,
        title=d.title,
        author=d.author,
        card_count=d.card_count,
        url=deck_url(d),
        owner_handle=d.owner.handle if d.owner else None,
        keywords=[k.value for k in d.keywords],
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


def list_public_decks(db: Session) -> list[PublicDeckItem]:
    """Public decks for the library grid, with their topic display name.

    Filtered to visibility == 'public'; unlisted and private decks are kept
    out of all listings, as are flagged decks awaiting moderation review.
    Ordered with the owner first so two owners' same-named topics don't
    interleave in the grouped library view.
    """
    decks = db.scalars(
        select(Deck)
        .join(Topic, Deck.topic_id == Topic.id)
        .join(User, Deck.owner_id == User.id)
        .options(joinedload(Deck.owner), selectinload(Deck.keywords))
        .where(
            Deck.visibility == "public",
            Deck.moderation_status == "approved",
            User.is_active,  # banned owners' decks hide while banned
        )
        .order_by(User.handle, Topic.display_name, Deck.title)
    ).all()
    return [_public_deck_item(d) for d in decks]


def search_public_decks(db: Session, q: str) -> list[PublicDeckItem]:
    """Public decks matching a search query, library-ordered.

    Every whitespace-separated term must match (AND) somewhere in the deck:
    the indexed `search_text` (title/author/description/keywords/card
    bodies) OR — so decks indexed before that column existed stay findable —
    the metadata columns directly. Same visibility/moderation/active filters
    as the library listing. Plain ILIKE: fine at this scale, tsvector later.
    """
    stmt = (
        select(Deck)
        .join(Topic, Deck.topic_id == Topic.id)
        .join(User, Deck.owner_id == User.id)
        .options(joinedload(Deck.owner), selectinload(Deck.keywords))
        .where(
            Deck.visibility == "public",
            Deck.moderation_status == "approved",
            User.is_active,
        )
        .order_by(User.handle, Topic.display_name, Deck.title)
    )
    for term in q.split():
        like = f"%{term}%"
        stmt = stmt.where(
            or_(
                Deck.search_text.ilike(like),
                Deck.title.ilike(like),
                Deck.description.ilike(like),
                Deck.author.ilike(like),
            )
        )
    return [_public_deck_item(d) for d in db.scalars(stmt).all()]


def list_decks_by_handle(db: Session, handle: str) -> list[PublicDeckItem]:
    """An author's public+approved decks for their /u/{handle} page."""
    decks = db.scalars(
        select(Deck)
        .join(Topic, Deck.topic_id == Topic.id)
        .join(User, Deck.owner_id == User.id)
        .options(joinedload(Deck.owner), selectinload(Deck.keywords))
        .where(
            User.handle == handle,
            User.is_active,
            Deck.visibility == "public",
            Deck.moderation_status == "approved",
        )
        .order_by(Topic.display_name, Deck.title)
    ).all()
    return [_public_deck_item(d) for d in decks]


def list_flagged_decks(db: Session) -> list[AdminDeckItem]:
    """Decks quarantined by moderation, oldest flag first — the review queue."""
    decks = db.scalars(
        select(Deck)
        .join(Topic, Deck.topic_id == Topic.id)
        .options(joinedload(Deck.owner))
        .where(Deck.moderation_status == "flagged")
        .order_by(Deck.flagged_at, Deck.id)
    ).all()
    return [
        AdminDeckItem(
            id=d.id,
            topic=d.topic.slug,
            slug=d.slug,
            title=d.title,
            author=d.author,
            card_count=d.card_count,
            filename=d.filename,
            url=deck_url(d),
            owner_handle=d.owner.handle if d.owner else None,
            visibility=d.visibility,
            created_at=d.created_at,
            updated_at=d.updated_at,
            owner_email=d.owner.email if d.owner else None,
            moderation_status=d.moderation_status,
            moderation_reasons=d.moderation_reasons,
            flagged_at=d.flagged_at,
        )
        for d in decks
    ]


# ── Admin operations by deck id ────────────────────────────────────────────
# Admin actions key on the deck row id: it is collision-proof under per-user
# spaces (flat slugs can be ambiguous) and the admin UI already holds full
# deck objects from the list endpoints.


def get_deck_source_by_id(db: Session, deck_id: int) -> str | None:
    """Raw markdown of any deck regardless of visibility/moderation state,
    or None if it doesn't exist. For the admin review queue (the public
    reader withholds quarantined decks, so the admin reads the source)."""
    deck = db.get(Deck, deck_id)
    if deck is None:
        return None
    return (Path(settings.UPLOAD_DIR) / deck.filename).read_text(encoding="utf-8")


def approve_deck_by_id(db: Session, deck_id: int) -> bool:
    """Admin-approve a flagged deck: it becomes visible per its own
    visibility setting. Returns False if the deck doesn't exist. Idempotent
    on an already-approved deck. Caller commits."""
    deck = db.get(Deck, deck_id)
    if deck is None:
        return False
    _apply_moderation(deck, "approved", None)
    db.flush()
    return True


def delete_deck_by_id(db: Session, deck_id: int) -> bool:
    """Delete any deck by row id (admin). Returns False if not found.
    The caller owns the commit."""
    deck = db.get(Deck, deck_id)
    if deck is None:
        return False
    _delete_deck(db, deck)
    return True


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
        .options(joinedload(Deck.owner))
        .where(Deck.owner_id == owner_id)
        .order_by(Topic.slug, Deck.slug)
    ).all()
    return [
        AdminDeckItem(
            id=d.id,
            topic=d.topic.slug,
            slug=d.slug,
            title=d.title,
            author=d.author,
            card_count=d.card_count,
            filename=d.filename,
            url=deck_url(d),
            owner_handle=d.owner.handle if d.owner else None,
            visibility=d.visibility,
            created_at=d.created_at,
            updated_at=d.updated_at,
            moderation_status=d.moderation_status,
            moderation_reasons=d.moderation_reasons,
        )
        for d in decks
    ]


def get_owned_deck_source(
    db: Session, owner_id: int, topic_slug: str, deck_slug: str
) -> str | None:
    """Raw markdown of an owned deck, or None if the user has no such deck."""
    deck = _resolve_owned_deck(db, owner_id, topic_slug, deck_slug)
    if deck is None:
        return None
    return (Path(settings.UPLOAD_DIR) / deck.filename).read_text(encoding="utf-8")


def create_user_deck(
    db: Session, owner_id: int, markdown: str, *, moderated: bool = True
) -> Deck:
    """Create (or refresh) a deck owned by `owner_id` from raw markdown.

    Identity is (owner, topic slug, title slug): re-saving the same identity
    refreshes that deck in place, reusing its stored filename — which may be
    a legacy flat name, so the file never has to move. Raises DeckParseError
    on malformed markdown, DeckUnsafe on code-like markup, DeckBlocked when
    moderation rejects the content, and DeckConflict if the derived filename
    is somehow held by a different owner (unreachable with per-owner dirs;
    kept as a safety net). Caller commits. `moderated=False` skips content
    moderation — only for the trusted admin file-upload path.
    """
    assert_deck_size(markdown)  # raises DeckTooLarge
    assert_safe_markup(markdown)  # raises DeckUnsafe
    parsed = parse_deck(markdown)  # raises DeckParseError

    # Resolve identity BEFORE deriving a filename: a legacy deck keeps its
    # flat filename, so re-deriving here would miss it and duplicate the row.
    topic_slug = slugify(str(parsed.meta["topic"]))
    assert_topic_slug_allowed(topic_slug)  # raises before anything is written
    deck_slug = slugify(str(parsed.meta["title"]))
    existing = _resolve_owned_deck(db, owner_id, topic_slug, deck_slug)
    if existing is not None:
        filename = existing.filename
    else:
        owner = db.get(User, owner_id)
        # Quota applies to NEW decks only (an identity refresh above isn't
        # growth); server edition, regular users only.
        if settings.quotas_enabled and not is_admin_user(owner):
            owned = db.scalar(
                select(func.count())
                .select_from(Deck)
                .where(Deck.owner_id == owner_id)
            )
            if owned >= settings.QUOTA_MAX_DECKS:
                raise DeckQuotaExceeded(settings.QUOTA_MAX_DECKS)
        filename = deck_filename(parsed.meta, owner.handle)
        clash = db.scalar(select(Deck).where(Deck.filename == filename))
        if clash is not None and clash.owner_id != owner_id:
            raise DeckConflict()

    if moderated:
        prev = existing.moderation_status if existing is not None else None
        mod_status, mod_reasons = _run_moderation(db, owner_id, parsed, prev)
    else:
        mod_status, mod_reasons = "approved", None

    path = Path(settings.UPLOAD_DIR) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    deck = index_deck_file(db, filename=filename, owner_id=owner_id)
    _apply_moderation(deck, mod_status, mod_reasons)
    db.flush()
    return deck


def update_user_deck(
    db: Session, owner_id: int, topic_slug: str, deck_slug: str, markdown: str
) -> Deck | None:
    """Replace an owned deck's markdown. Returns None if the user has no
    such deck.

    Same identity (topic+title slugs unchanged) refreshes the stored file in
    place — legacy flat filenames stay put. A changed identity is a rename:
    the new file is written and indexed (keeping the original created_at),
    then the old file + rows are pruned. Raises DeckParseError on malformed
    markdown, DeckBlocked when moderation rejects the new content (the old
    version survives), and DeckConflict if the rename lands on another deck
    the user already has (or, safety net, another owner's filename). Caller
    commits.
    """
    deck = _resolve_owned_deck(db, owner_id, topic_slug, deck_slug)
    if deck is None:
        return None

    assert_deck_size(markdown)  # raises DeckTooLarge
    assert_safe_markup(markdown)  # raises DeckUnsafe
    old_filename = deck.filename
    old_created_at = deck.created_at
    parsed = parse_deck(markdown)  # raises DeckParseError

    new_topic_slug = slugify(str(parsed.meta["topic"]))
    assert_topic_slug_allowed(new_topic_slug)  # raises before anything is written
    new_deck_slug = slugify(str(parsed.meta["title"]))
    if (new_topic_slug, new_deck_slug) == (topic_slug, deck_slug):
        new_filename = old_filename  # same identity → refresh in place
    else:
        # Renaming onto an identity the user already holds would silently
        # merge two decks via the filename upsert — reject instead.
        target = _resolve_owned_deck(db, owner_id, new_topic_slug, new_deck_slug)
        if target is not None and target.id != deck.id:
            raise DeckConflict()
        owner = db.get(User, owner_id)
        new_filename = deck_filename(parsed.meta, owner.handle)
        clash = db.scalar(select(Deck).where(Deck.filename == new_filename))
        if clash is not None and clash.owner_id != owner_id:
            raise DeckConflict()

    # A block raises here, before any write — the previous version survives
    # untouched. A flag re-quarantines the edited deck.
    mod_status, mod_reasons = _run_moderation(
        db, owner_id, parsed, deck.moderation_status
    )

    path = Path(settings.UPLOAD_DIR) / new_filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    updated = index_deck_file(db, filename=new_filename, owner_id=owner_id)
    _apply_moderation(updated, mod_status, mod_reasons)
    db.flush()

    if new_filename != old_filename:
        # The rename created a fresh row; it's still the same deck to the
        # author, so keep the original creation date.
        updated.created_at = old_created_at
        old = db.scalar(select(Deck).where(Deck.filename == old_filename))
        if old is not None:
            _delete_deck(db, old)
        db.flush()
    return updated


def delete_user_deck(
    db: Session, owner_id: int, topic_slug: str, deck_slug: str
) -> bool:
    """Delete an owned deck. Returns False if the user has no such deck.
    Caller commits."""
    deck = _resolve_owned_deck(db, owner_id, topic_slug, deck_slug)
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
