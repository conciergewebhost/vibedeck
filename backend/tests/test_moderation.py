"""Content-moderation tests:
  - the heuristics engine's allow / flag / block verdicts
  - flagged decks are quarantined (created but withheld from public reads)
  - blocked decks are rejected at submit and leave only an audit event
  - the admin review queue lists and approves flagged decks
  - moderation is skipped entirely in the standalone edition

Runs against an in-memory DB with an isolated temp UPLOAD_DIR so it never
touches real deck files. From backend/:  python -m unittest tests.test_moderation
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
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import main  # noqa: E402
from config import Edition, settings  # noqa: E402
from database import Base, get_db  # noqa: E402
from models import Deck, ModerationEvent, User  # noqa: E402
from services.auth import create_access_token, hash_password  # noqa: E402
from services.moderation import moderate_deck  # noqa: E402
from services.parser import ParsedCard, ParsedDeck  # noqa: E402


def _parsed(body: str, **meta_overrides) -> ParsedDeck:
    meta = {
        "title": "Test Deck",
        "author": "Author",
        "topic": "testing",
        "keywords": ["k"],
        "theme": "default",
    }
    meta.update(meta_overrides)
    return ParsedDeck(meta=meta, cards=[ParsedCard(type="concept", meta={}, body=body)])


def _markdown(body: str, title: str = "Test Deck") -> str:
    return (
        "---\n"
        f"title: {title}\nauthor: A\ntopic: testing\nkeywords: [x]\ntheme: default\n"
        "---\n---\ntype: concept\n---\n"
        f"{body}\n"
    )


class TestModerationEngine(unittest.TestCase):
    """Pure verdicts from services.moderation — no DB, no app."""

    def test_clean_deck_is_allowed(self):
        v = moderate_deck(_parsed("A normal card citing [one source](https://example.com)."))
        self.assertEqual(v.action, "allow")
        self.assertEqual(v.reasons, [])

    def test_severe_word_blocks(self):
        v = moderate_deck(_parsed("some text with kys in it"))
        self.assertEqual(v.action, "block")
        self.assertTrue(v.reasons)

    def test_borderline_word_flags(self):
        v = moderate_deck(_parsed("limited offer, buy now"))
        self.assertEqual(v.action, "flag")

    def test_word_boundaries_avoid_scunthorpe(self):
        # Substring hits inside innocent words must not match.
        v = moderate_deck(_parsed("Scunthorpe's Maine coon cat assessment class"))
        self.assertEqual(v.action, "allow")

    def test_flag_word_in_frontmatter_is_scanned(self):
        v = moderate_deck(_parsed("clean body", title="Casino secrets"))
        self.assertEqual(v.action, "flag")

    def test_link_farm_blocks(self):
        body = " ".join(f"[l](https://spam{i}.example)" for i in range(25))
        v = moderate_deck(_parsed(body))
        self.assertEqual(v.action, "block")

    def test_repeated_domain_flags(self):
        links = " ".join(f"[l{i}](https://same.example/p{i})" for i in range(5))
        v = moderate_deck(_parsed(links + " " + "word " * 200))
        self.assertEqual(v.action, "flag")

    def test_url_shorteners_flag_then_block(self):
        self.assertEqual(
            moderate_deck(_parsed("see https://bit.ly/x for more")).action, "flag"
        )
        v = moderate_deck(
            _parsed("https://bit.ly/x https://tinyurl.com/y https://t.co/z")
        )
        self.assertEqual(v.action, "block")

    def test_links_to_own_instance_dont_count(self):
        own = settings.BASE_URL.rstrip("/")
        body = " ".join(f"[d{i}]({own}/topic/deck{i})" for i in range(30))
        self.assertEqual(moderate_deck(_parsed(body)).action, "allow")


class ModeratedAppTestCase(unittest.TestCase):
    """Shared app/DB scaffolding with EDITION=server (moderation on)."""

    EDITION = Edition.SERVER

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

        self._tmp = tempfile.TemporaryDirectory()
        self._orig_upload_dir = settings.UPLOAD_DIR
        settings.UPLOAD_DIR = Path(self._tmp.name)
        self._orig_edition = settings.EDITION
        settings.EDITION = self.EDITION

    def tearDown(self):
        main.app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        settings.UPLOAD_DIR = self._orig_upload_dir
        settings.EDITION = self._orig_edition
        self._tmp.cleanup()

    def _auth(self, email):
        db = self.Session()
        db.add(
            User(
                email=email,
                handle=email.split("@", 1)[0],
                hashed_password=hash_password("x"),
            )
        )
        db.commit()
        db.close()
        return {"Authorization": f"Bearer {create_access_token(subject=email)}"}

    def _mine(self, content, auth):
        return self.client.post(
            "/api/decks/mine", json={"markdown": content}, headers=auth
        )


class TestModerationEnforcement(ModeratedAppTestCase):
    def test_clean_deck_publishes_normally(self):
        a = self._auth("a@e.com")
        res = self._mine(_markdown("Just a normal card."), a)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["moderation_status"], "approved")
        self.assertEqual(self.client.get("/api/decks/testing/test-deck").status_code, 200)

    def test_flagged_deck_is_quarantined(self):
        a = self._auth("a@e.com")
        res = self._mine(_markdown("limited offer, buy now"), a)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["moderation_status"], "flagged")

        # Withheld from the public reader, library, and topic listings…
        self.assertEqual(self.client.get("/api/decks/testing/test-deck").status_code, 404)
        self.assertEqual(self.client.get("/api/decks/public").json(), [])
        self.assertEqual(self.client.get("/api/topics").json(), [])

        # …but the owner still sees it, with its state.
        mine = self.client.get("/api/decks/mine", headers=a).json()
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["moderation_status"], "flagged")

    def test_blocked_deck_is_rejected_and_logged(self):
        a = self._auth("a@e.com")
        res = self._mine(_markdown("some text with kys in it"), a)
        self.assertEqual(res.status_code, 422)

        db = self.Session()
        self.assertEqual(len(db.scalars(select(Deck)).all()), 0)
        events = db.scalars(select(ModerationEvent)).all()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].action, "block")
        self.assertEqual(events[0].owner_email, "a@e.com")
        db.close()
        # Nothing written to disk either.
        self.assertEqual(list(Path(self._tmp.name).iterdir()), [])

    def test_blocking_edit_keeps_previous_version(self):
        a = self._auth("a@e.com")
        self.assertEqual(self._mine(_markdown("Original clean body."), a).status_code, 201)
        res = self.client.put(
            "/api/decks/mine/testing/test-deck",
            json={"markdown": _markdown("now with kys added")},
            headers=a,
        )
        self.assertEqual(res.status_code, 422)
        body = self.client.get("/api/decks/testing/test-deck").json()
        self.assertIn("Original clean body.", body["cards"][0]["body"])

    def test_clean_edit_clears_flag(self):
        a = self._auth("a@e.com")
        self.assertEqual(
            self._mine(_markdown("limited offer, buy now"), a).json()["moderation_status"],
            "flagged",
        )
        res = self.client.put(
            "/api/decks/mine/testing/test-deck",
            json={"markdown": _markdown("All cleaned up.")},
            headers=a,
        )
        self.assertEqual(res.json()["moderation_status"], "approved")
        self.assertEqual(self.client.get("/api/decks/testing/test-deck").status_code, 200)


class TestAdminReviewQueue(ModeratedAppTestCase):
    def test_queue_lists_and_approve_publishes(self):
        owner = self._auth("owner@example.com")  # == UPLOAD_OWNER_EMAIL
        a = self._auth("a@e.com")
        self._mine(_markdown("limited offer, buy now"), a)

        queue = self.client.get("/api/admin/flagged", headers=owner).json()
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["owner_email"], "a@e.com")
        self.assertIn("review", queue[0]["moderation_reasons"])

        # Admin can read the quarantined source even though the reader 404s.
        src = self.client.get("/api/admin/decks/testing/test-deck/source", headers=owner)
        self.assertEqual(src.status_code, 200)
        self.assertIn("buy now", src.text)

        res = self.client.post(
            "/api/admin/decks/testing/test-deck/approve", headers=owner
        )
        self.assertEqual(res.status_code, 204)
        self.assertEqual(self.client.get("/api/decks/testing/test-deck").status_code, 200)
        self.assertEqual(self.client.get("/api/admin/flagged", headers=owner).json(), [])

    def test_queue_requires_admin(self):
        a = self._auth("a@e.com")
        self.assertEqual(self.client.get("/api/admin/flagged", headers=a).status_code, 403)

    def test_moderation_summary_counts_queue(self):
        owner = self._auth("owner@example.com")
        a = self._auth("a@e.com")
        self._mine(_markdown("limited offer, buy now"), a)
        summary = self.client.get("/api/admin/moderation-summary", headers=owner).json()
        self.assertEqual(summary["queue_size"], 1)


class TestStandaloneSkipsModeration(ModeratedAppTestCase):
    EDITION = Edition.STANDALONE

    def test_flag_words_publish_unmoderated(self):
        a = self._auth("a@e.com")
        res = self._mine(_markdown("limited offer, buy now"), a)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["moderation_status"], "approved")
        self.assertEqual(self.client.get("/api/decks/testing/test-deck").status_code, 200)

    def test_even_block_words_publish_unmoderated(self):
        # Standalone is single-user: the author moderates themselves.
        a = self._auth("a@e.com")
        res = self._mine(_markdown("some text with kys in it"), a)
        self.assertEqual(res.status_code, 201)
        db = self.Session()
        self.assertEqual(len(db.scalars(select(ModerationEvent)).all()), 0)
        db.close()
