"""Dev seed — index the sample deck so the read endpoints have data.

Run from the backend/ directory with the venv active:
    python seed.py

Creates a placeholder author user whose password hash is intentionally
INVALID ("!"), so it can never authenticate — real auth/users land with
the (pending) auth work. Then indexes every *.md file under UPLOAD_DIR.
This is a development convenience, not part of the request path.
"""

from pathlib import Path

from sqlalchemy import select

from config import settings
from database import SessionLocal
from models import User
from services.indexing import index_deck_file
from services.parser import DeckParseError

SEED_AUTHOR_EMAIL = "seed@vibedeck.local"


def main() -> None:
    db = SessionLocal()
    try:
        author = db.scalar(select(User).where(User.email == SEED_AUTHOR_EMAIL))
        if author is None:
            # "!" is not a valid hash -> login impossible for the seed user.
            author = User(email=SEED_AUTHOR_EMAIL, handle="seed", hashed_password="!")
            db.add(author)
            db.flush()

        upload_dir = Path(settings.UPLOAD_DIR)
        # rglob: decks live in per-owner subdirs (legacy flat files included).
        deck_files = sorted(
            str(p.relative_to(upload_dir)) for p in upload_dir.rglob("*.md")
        )
        if not deck_files:
            print(f"No .md decks found under {upload_dir}")
            return

        for filename in deck_files:
            try:
                deck = index_deck_file(db, filename=filename, owner_id=author.id)
                print(
                    f"indexed {filename!r} -> /{deck.topic.slug}/{deck.slug} "
                    f"({deck.card_count} cards)"
                )
            except DeckParseError as exc:
                print(f"SKIP {filename!r}: malformed — {exc}")

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
