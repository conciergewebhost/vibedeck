"""Management CLI for Vibedeck.

Run from the backend/ directory with the venv active:

    python manage.py create-user alice@example.com [--password s3cret]
    python manage.py delete-user alice@example.com
    python manage.py list-decks
    python manage.py reindex
    python manage.py delete-deck <topic-slug> <deck-slug>

Since v1 has no registration UI, create-user is how upload-capable users are
provisioned. Deck commands operate on the canonical files under UPLOAD_DIR and
keep the DB index in sync. New decks indexed here are attributed to the
configured UPLOAD_OWNER_EMAIL account.
"""

import argparse
import getpass
import sys
from pathlib import Path

from sqlalchemy import func, select

from config import settings
from database import SessionLocal
from models import Deck, User
from services.auth import hash_password
from services.decks import _delete_deck, delete_deck_by_slugs, list_all_decks
from services.indexing import index_deck_file
from services.parser import DeckParseError


def _owner(db) -> User:
    """Resolve the configured upload-owner account, or exit with guidance."""
    owner = db.scalar(select(User).where(User.email == settings.UPLOAD_OWNER_EMAIL))
    if owner is None:
        raise SystemExit(
            f"Owner account {settings.UPLOAD_OWNER_EMAIL!r} not found; "
            f"run: python manage.py create-user {settings.UPLOAD_OWNER_EMAIL}"
        )
    return owner


def create_user(email: str, password: str) -> int:
    db = SessionLocal()
    try:
        if db.scalar(select(User).where(User.email == email)) is not None:
            print(f"User {email!r} already exists.", file=sys.stderr)
            return 1
        user = User(email=email, hashed_password=hash_password(password))
        db.add(user)
        db.commit()
        print(f"Created user {email!r} (id={user.id}).")
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


def list_decks() -> int:
    db = SessionLocal()
    try:
        decks = list_all_decks(db)
        if not decks:
            print("(no decks indexed)")
            return 0
        for d in decks:
            print(f"/{d.topic}/{d.slug}  ({d.card_count} cards)  [{d.filename}]")
        return 0
    finally:
        db.close()


def reindex() -> int:
    """Index every decks/*.md and prune DB rows whose file is gone.

    Pruning is keyed strictly on file ABSENCE on disk — a present-but-malformed
    file is skipped (kept), never pruned.
    """
    db = SessionLocal()
    try:
        owner = _owner(db)
        upload_dir = Path(settings.UPLOAD_DIR)
        present = sorted(p.name for p in upload_dir.glob("*.md"))

        for filename in present:
            try:
                deck = index_deck_file(db, filename=filename, owner_id=owner.id)
                print(f"indexed {filename!r} -> /{deck.topic.slug}/{deck.slug}")
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


def delete_deck(topic_slug: str, deck_slug: str) -> int:
    db = SessionLocal()
    try:
        if not delete_deck_by_slugs(db, topic_slug, deck_slug):
            print(f"Deck /{topic_slug}/{deck_slug} not found.", file=sys.stderr)
            return 1
        db.commit()
        print(f"Deleted /{topic_slug}/{deck_slug}.")
        return 0
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Vibedeck management CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    cu = sub.add_parser("create-user", help="Create an upload-capable user")
    cu.add_argument("email")
    cu.add_argument("--password", help="If omitted, you'll be prompted")

    du = sub.add_parser("delete-user", help="Delete a user (must own no decks)")
    du.add_argument("email")

    sub.add_parser("list-decks", help="List all indexed decks")
    sub.add_parser("reindex", help="Index all decks/*.md and prune deleted files")

    dd = sub.add_parser("delete-deck", help="Delete one deck (file + index)")
    dd.add_argument("topic_slug")
    dd.add_argument("deck_slug")

    args = parser.parse_args()

    if args.command == "create-user":
        password = args.password or getpass.getpass("Password: ")
        if not password:
            print("Password must not be empty.", file=sys.stderr)
            return 2
        return create_user(args.email, password)
    if args.command == "delete-user":
        return delete_user(args.email)
    if args.command == "list-decks":
        return list_decks()
    if args.command == "reindex":
        return reindex()
    if args.command == "delete-deck":
        return delete_deck(args.topic_slug, args.deck_slug)

    return 2  # unreachable: subparser is required


if __name__ == "__main__":
    sys.exit(main())
