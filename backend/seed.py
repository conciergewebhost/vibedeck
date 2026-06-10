"""Dev seed — give a fresh instance its first decks.

Run from the backend/ directory with the venv active:
    python seed.py

If UPLOAD_DIR contains no decks yet, the bundled reference decks from the
repo's samples/ directory are copied into UPLOAD_DIR/seed/ first. Then
every *.md under UPLOAD_DIR is indexed, attributed to a placeholder seed
author whose password hash is intentionally INVALID ("!") so it can never
authenticate. This is a development/bootstrap convenience, not part of
the request path.
"""

import shutil
from pathlib import Path

from sqlalchemy import select

from config import settings
from database import SessionLocal
from models import User
from services.indexing import index_deck_file
from services.parser import DeckParseError
from services.urls import deck_url

SEED_AUTHOR_EMAIL = "seed@vibedeck.local"
SEED_HANDLE = "seed"
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"


def main() -> None:
    db = SessionLocal()
    try:
        author = db.scalar(select(User).where(User.email == SEED_AUTHOR_EMAIL))
        if author is None:
            # "!" is not a valid hash -> login impossible for the seed user.
            author = User(
                email=SEED_AUTHOR_EMAIL, handle=SEED_HANDLE, hashed_password="!"
            )
            db.add(author)
            db.flush()

        upload_dir = Path(settings.UPLOAD_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)

        # First run on an empty instance: copy the bundled samples in.
        if not any(upload_dir.rglob("*.md")) and SAMPLES_DIR.is_dir():
            dest = upload_dir / SEED_HANDLE
            dest.mkdir(parents=True, exist_ok=True)
            for sample in sorted(SAMPLES_DIR.glob("*.md")):
                shutil.copy(sample, dest / sample.name)
                print(f"copied sample {sample.name!r} -> {dest / sample.name}")

        # rglob: decks live in per-owner subdirs (legacy flat files included).
        deck_files = sorted(
            str(p.relative_to(upload_dir)) for p in upload_dir.rglob("*.md")
        )
        if not deck_files:
            print(f"No .md decks found under {upload_dir} (and no samples/).")
            return

        for filename in deck_files:
            try:
                deck = index_deck_file(db, filename=filename, owner_id=author.id)
                print(
                    f"indexed {filename!r} -> {deck_url(deck)} "
                    f"({deck.card_count} cards)"
                )
            except DeckParseError as exc:
                print(f"SKIP {filename!r}: malformed — {exc}")

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
