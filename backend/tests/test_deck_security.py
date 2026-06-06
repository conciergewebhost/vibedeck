"""Security regression tests for deck uploads:
  - a user can't overwrite another user's deck via /api/decks/upload
  - uploads run the no-code guard
  - oversized decks are rejected

Runs against an in-memory DB with an isolated temp UPLOAD_DIR so it never
touches real deck files. From backend/:  python -m unittest tests.test_deck_security
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("UPLOAD_DIR", "/tmp")
os.environ.setdefault("UPLOAD_TOKEN", "test-upload-token")
os.environ.setdefault("UPLOAD_OWNER_EMAIL", "owner@example.com")
os.environ.setdefault("NEW_USER_CODE", "let-me-in")
os.environ.setdefault("RESEND_API_KEY", "re_test")
os.environ.setdefault("EMAIL_FROM_ADDRESS", "noreply@example.com")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import main  # noqa: E402
from config import settings  # noqa: E402
from database import Base, get_db  # noqa: E402
from models import User  # noqa: E402
from services.auth import create_access_token, hash_password  # noqa: E402

DECK = (
    "---\n"
    "title: Shared Title\nauthor: A\ntopic: shared\nkeywords: [x]\ntheme: default\n"
    "---\n---\ntype: title\n---\n# Hi\n"
)


class TestUploadSecurity(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False)

        def override_get_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        main.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(main.app)

        # Isolate deck file writes to a throwaway dir (never the real decks/).
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_upload_dir = settings.UPLOAD_DIR
        settings.UPLOAD_DIR = Path(self._tmp.name)

    def tearDown(self):
        main.app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        settings.UPLOAD_DIR = self._orig_upload_dir
        self._tmp.cleanup()

    def _auth(self, email):
        db = self.Session()
        db.add(User(email=email, hashed_password=hash_password("x")))
        db.commit()
        db.close()
        return {"Authorization": f"Bearer {create_access_token(subject=email)}"}

    def _upload(self, content, auth):
        return self.client.post(
            "/api/decks/upload",
            files={"file": ("deck.md", content, "text/markdown")},
            headers=auth,
        )

    def test_upload_blocks_cross_user_overwrite(self):
        a = self._auth("a@e.com")
        b = self._auth("b@e.com")
        self.assertEqual(self._upload(DECK, a).status_code, 201)
        # B uploads a deck with the same topic+title → same filename → must be
        # rejected, not silently overwrite A's deck.
        r = self._upload(DECK, b)
        self.assertEqual(r.status_code, 409)

    def test_upload_rejects_code(self):
        a = self._auth("a@e.com")
        evil = DECK + "---\ntype: concept\n---\n<script>alert(1)</script>\n"
        self.assertEqual(self._upload(evil, a).status_code, 400)

    def test_upload_rejects_oversized(self):
        a = self._auth("a@e.com")
        big = DECK + "---\ntype: concept\n---\n" + ("a" * 300_000) + "\n"
        self.assertEqual(self._upload(big, a).status_code, 413)

    def test_oversized_via_mine_json(self):
        a = self._auth("a@e.com")
        big = DECK + "---\ntype: concept\n---\n" + ("a" * 300_000) + "\n"
        r = self.client.post("/api/decks/mine", json={"markdown": big}, headers=a)
        self.assertEqual(r.status_code, 413)


class TestPreviewThrottle(unittest.TestCase):
    """The public /api/decks/preview is throttled for external callers (XFF
    present) but exempt for trusted loopback SSR calls (no XFF)."""

    def setUp(self):
        from routers import decks as decks_router

        decks_router._preview_limiter.clear()
        self.client = TestClient(main.app)

    def test_external_caller_throttled_after_limit(self):
        from routers import decks as decks_router

        hdr = {"X-Forwarded-For": "9.9.9.9"}
        limit = decks_router._PREVIEW_MAX_PER_MIN
        for _ in range(limit):
            r = self.client.post("/api/decks/preview", json={"markdown": DECK}, headers=hdr)
            self.assertEqual(r.status_code, 200)
        blocked = self.client.post("/api/decks/preview", json={"markdown": DECK}, headers=hdr)
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Retry-After", blocked.headers)

    def test_loopback_not_throttled(self):
        from routers import decks as decks_router

        # No XFF → trusted loopback (the SSR editor preview path) → never throttled.
        for _ in range(decks_router._PREVIEW_MAX_PER_MIN + 5):
            r = self.client.post("/api/decks/preview", json={"markdown": DECK})
            self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
