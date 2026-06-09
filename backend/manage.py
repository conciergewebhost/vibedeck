"""Management CLI for Vibedeck.

Run from the backend/ directory with the venv active:

    python manage.py create-user alice@example.com [--password s3cret] [--handle alice]
    python manage.py delete-user alice@example.com
    python manage.py promote-user alice@example.com
    python manage.py demote-user alice@example.com
    python manage.py list-decks
    python manage.py reindex
    python manage.py delete-deck <topic-slug> <deck-slug> [--handle alice]
    python manage.py tidy

Since v1 has no registration UI, create-user is how upload-capable users are
provisioned. Deck commands operate on the canonical files under UPLOAD_DIR
(per-owner subdirs + legacy flat files) and keep the DB index in sync. New
decks indexed here are attributed to the configured UPLOAD_OWNER_EMAIL
account. `tidy` moves legacy flat deck files into their owner's subdir —
optional housekeeping, never required.
"""

import argparse
import getpass
import sys
from pathlib import Path

from sqlalchemy import func, select

from config import settings
from database import SessionLocal
from models import Deck, Topic, User
from services.auth import hash_password
from services.decks import (
    _delete_deck,
    _resolve_deck_namespaced,
    delete_deck_by_slugs,
    list_all_decks,
)
from services.handles import HandleInvalid, derive_handle, validate_handle
from services.indexing import index_deck_file
from services.parser import DeckParseError
from services.urls import deck_url


def _owner(db) -> User:
    """Resolve the configured upload-owner account, or exit with guidance."""
    owner = db.scalar(select(User).where(User.email == settings.UPLOAD_OWNER_EMAIL))
    if owner is None:
        raise SystemExit(
            f"Owner account {settings.UPLOAD_OWNER_EMAIL!r} not found; "
            f"run: python manage.py create-user {settings.UPLOAD_OWNER_EMAIL}"
        )
    return owner


def create_user(email: str, password: str, handle: str | None) -> int:
    db = SessionLocal()
    try:
        if db.scalar(select(User).where(User.email == email)) is not None:
            print(f"User {email!r} already exists.", file=sys.stderr)
            return 1
        try:
            resolved = (
                validate_handle(db, handle) if handle else derive_handle(db, email)
            )
        except HandleInvalid as exc:
            print(f"Invalid handle: {exc}", file=sys.stderr)
            return 1
        user = User(
            email=email, handle=resolved, hashed_password=hash_password(password)
        )
        db.add(user)
        db.commit()
        print(f"Created user {email!r} (id={user.id}, handle={resolved!r}).")
        return 0
    finally:
        db.close()


def delete_user(email: str) -> int:
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            print(f"User {email!r} not found.", file=sys.stderr)
            return 1
        # Deck.owner_id has no ON DELETE cascade; refuse rather than hit an
        # IntegrityError if this user still owns decks.
        owned = db.scalar(
            select(func.count()).select_from(Deck).where(Deck.owner_id == user.id)
        )
        if owned:
            print(
                f"Refusing: {email!r} owns {owned} deck(s). "
                f"Reassign or delete them first.",
                file=sys.stderr,
            )
            return 1
        db.delete(user)
        db.commit()
        print(f"Deleted user {email!r}.")
        return 0
    finally:
        db.close()


def set_admin_role(email: str, value: bool) -> int:
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            print(f"User {email!r} not found.", file=sys.stderr)
            return 1
        if email == settings.UPLOAD_OWNER_EMAIL:
            print(
                "The owner account is always an admin (config fallback via "
                "UPLOAD_OWNER_EMAIL); its role can't be changed.",
                file=sys.stderr,
            )
            return 1
        user.is_admin = value
        db.commit()
        print(f"{'Promoted' if value else 'Demoted'} {email!r} (is_admin={value}).")
        return 0
    finally:
        db.close()


def list_decks() -> int:
    db = SessionLocal()
    try:
        decks = list_all_decks(db)
        if not decks:
            print("(no decks indexed)")
            return 0
        for d in decks:
            print(f"{d.url}  ({d.card_count} cards)  [{d.filename}]")
        return 0
    finally:
        db.close()


def reindex() -> int:
    """Index every *.md under UPLOAD_DIR (per-owner subdirs + legacy flat
    files) and prune DB rows whose file is gone.

    Pruning is keyed strictly on file ABSENCE on disk — a present-but-malformed
    file is skipped (kept), never pruned. New files indexed here are
    attributed to the configured owner account.
    """
    db = SessionLocal()
    try:
        owner = _owner(db)
        upload_dir = Path(settings.UPLOAD_DIR)
        present = sorted(
            str(p.relative_to(upload_dir)) for p in upload_dir.rglob("*.md")
        )

        for filename in present:
            try:
                deck = index_deck_file(db, filename=filename, owner_id=owner.id)
                print(f"indexed {filename!r} -> {deck_url(deck)}")
            except DeckParseError as exc:
                print(f"SKIP {filename!r}: malformed — {exc}")

        present_set = set(present)
        for deck in db.scalars(select(Deck)).all():
            if deck.filename not in present_set:
                print(f"prune {deck.filename!r} (file gone)")
                _delete_deck(db, deck)

        db.commit()
        return 0
    finally:
        db.close()


def delete_deck(topic_slug: str, deck_slug: str, handle: str | None) -> int:
    db = SessionLocal()
    try:
        if handle:
            deck = _resolve_deck_namespaced(db, handle, topic_slug, deck_slug)
            if deck is None:
                print(
                    f"Deck /u/{handle}/{topic_slug}/{deck_slug} not found.",
                    file=sys.stderr,
                )
                return 1
            _delete_deck(db, deck)
        elif not delete_deck_by_slugs(db, topic_slug, deck_slug):
            # 0 matches, or ≥2 owners hold this identity — list candidates.
            owners = db.scalars(
                select(User.handle)
                .join(Deck, Deck.owner_id == User.id)
                .join(Topic, Deck.topic_id == Topic.id)
                .where(Topic.slug == topic_slug, Deck.slug == deck_slug)
            ).all()
            if owners:
                print(
                    f"/{topic_slug}/{deck_slug} is ambiguous; pick an owner "
                    f"with --handle: {', '.join(sorted(owners))}",
                    file=sys.stderr,
                )
            else:
                print(f"Deck /{topic_slug}/{deck_slug} not found.", file=sys.stderr)
            return 1
        db.commit()
        print(f"Deleted /{topic_slug}/{deck_slug}.")
        return 0
    finally:
        db.close()


def tidy() -> int:
    """Move legacy flat deck files into their owner's subdir.

    Optional housekeeping: flat filenames work indefinitely (the filename
    column is an opaque pointer); this just makes the on-disk layout match
    the per-user spaces model. Idempotent; commits per deck so an
    interruption leaves every moved deck consistent.
    """
    db = SessionLocal()
    try:
        upload_dir = Path(settings.UPLOAD_DIR)
        moved = 0
        for deck in db.scalars(select(Deck).order_by(Deck.id)).all():
            if "/" in deck.filename:
                continue  # already in a subdir
            owner = db.get(User, deck.owner_id)
            if owner is None:
                print(f"SKIP {deck.filename!r}: no owner row")
                continue
            new_rel = f"{owner.handle}/{deck.filename}"
            src = upload_dir / deck.filename
            dst = upload_dir / new_rel
            if not src.exists():
                print(f"SKIP {deck.filename!r}: file missing (run reindex?)")
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
            deck.filename = new_rel
            db.commit()
            print(f"moved {src.name!r} -> {new_rel!r}")
            moved += 1
        print(f"tidy: {moved} file(s) moved.")
        return 0
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Vibedeck management CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    cu = sub.add_parser("create-user", help="Create an upload-capable user")
    cu.add_argument("email")
    cu.add_argument("--password", help="If omitted, you'll be prompted")
    cu.add_argument(
        "--handle",
        help="Public namespace name (/u/{handle}); derived from the email "
        "local-part if omitted",
    )

    du = sub.add_parser("delete-user", help="Delete a user (must own no decks)")
    du.add_argument("email")

    pu = sub.add_parser("promote-user", help="Grant a user the admin surface")
    pu.add_argument("email")

    dm = sub.add_parser("demote-user", help="Revoke a user's admin rights")
    dm.add_argument("email")

    sub.add_parser("list-decks", help="List all indexed decks")
    sub.add_parser("reindex", help="Index all deck files and prune deleted ones")
    sub.add_parser("tidy", help="Move legacy flat deck files into owner subdirs")

    dd = sub.add_parser("delete-deck", help="Delete one deck (file + index)")
    dd.add_argument("topic_slug")
    dd.add_argument("deck_slug")
    dd.add_argument(
        "--handle", help="Owner handle, required if the slugs are ambiguous"
    )

    args = parser.parse_args()

    if args.command == "create-user":
        password = args.password or getpass.getpass("Password: ")
        if not password:
            print("Password must not be empty.", file=sys.stderr)
            return 2
        return create_user(args.email, password, args.handle)
    if args.command == "delete-user":
        return delete_user(args.email)
    if args.command == "promote-user":
        return set_admin_role(args.email, True)
    if args.command == "demote-user":
        return set_admin_role(args.email, False)
    if args.command == "list-decks":
        return list_decks()
    if args.command == "reindex":
        return reindex()
    if args.command == "tidy":
        return tidy()
    if args.command == "delete-deck":
        return delete_deck(args.topic_slug, args.deck_slug, args.handle)

    return 2  # unreachable: subparser is required


if __name__ == "__main__":
    sys.exit(main())
