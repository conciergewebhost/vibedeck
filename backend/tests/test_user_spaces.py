"""Per-user spaces tests:
  - handle validation/derivation rules (services/handles)
  - two owners can hold the same (topic, deck) identity in separate spaces
  - flat lookups serve unique matches only; namespaced lookups always work
  - owner-portal CRUD stays scoped to the acting user under collisions
  - legacy flat filenames: re-create updates in place, rename keeps
    created_at and moves the file into the owner's subdir
  - author endpoints expose public+approved decks only
  - deck_url shape per edition

Runs against an in-memory DB with an isolated temp UPLOAD_DIR. From
backend/:  python -m unittest tests.test_user_spaces
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
from models import Deck, User  # noqa: E402
from services.auth import create_access_token, hash_password  # noqa: E402
from services.handles import (  # noqa: E402
    HandleInvalid,
    derive_handle,
    validate_handle,
)


def _md(topic="Tarot", title="Basics", body="One idea.") -> str:
    return (
        "---\n"
        f"title: {title}\nauthor: A\ntopic: {topic}\nkeywords: [x]\ntheme: default\n"
        "---\n---\ntype: concept\n---\n"
        f"{body}\n"
    )


class _AppTestCase(unittest.TestCase):
    """App + in-memory DB + temp UPLOAD_DIR, pinned to the server edition
    (per-user spaces URLs) unless a test flips it."""

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


class TestHandleRules(_AppTestCase):
    def test_format_rules(self):
        db = self.Session()
        self.assertEqual(validate_handle(db, "  Alice-W "), "alice-w")
        for bad in ["a", "-alice", "alice-", "al ice", "al_ice", "x" * 64]:
            with self.assertRaises(HandleInvalid, msg=bad):
                validate_handle(db, bad)
        db.close()

    def test_reserved_and_taken(self):
        self._auth("alice@e.com")  # takes "alice"
        db = self.Session()
        for bad in ["admin", "u", "decks", "me", "alice"]:
            with self.assertRaises(HandleInvalid, msg=bad):
                validate_handle(db, bad)
        db.close()

    def test_derive_dedupes(self):
        self._auth("bob@e.com")  # takes "bob"
        db = self.Session()
        self.assertEqual(derive_handle(db, "bob@other.com"), "bob-2")
        # Reserved local-parts skip to a suffix too.
        self.assertEqual(derive_handle(db, "admin@e.com"), "admin-2")
        db.close()


class TestSeparateSpaces(_AppTestCase):
    def test_collision_serves_namespaced_and_flat_404s(self):
        a = self._auth("alice@e.com")
        b = self._auth("bob@e.com")
        self.assertEqual(self._mine(_md(), a).status_code, 201)

        # While unique, the flat lookup works and reports the canonical url.
        flat = self.client.get("/api/decks/tarot/basics")
        self.assertEqual(flat.status_code, 200)
        self.assertEqual(flat.json()["url"], "/u/alice/tarot/basics")

        # Second owner, same identity → separate space, no conflict.
        self.assertEqual(self._mine(_md(), b).status_code, 201)

        # Flat is now ambiguous → 404; both namespaced lookups resolve.
        self.assertEqual(self.client.get("/api/decks/tarot/basics").status_code, 404)
        for handle in ("alice", "bob"):
            res = self.client.get(f"/api/decks/u/{handle}/tarot/basics")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["owner_handle"], handle)

        # Each owner got their own topic row and their own file.
        db = self.Session()
        self.assertEqual(len(db.scalars(select(Deck)).all()), 2)
        db.close()
        root = Path(self._tmp.name)
        self.assertTrue((root / "alice" / "tarot__basics.md").exists())
        self.assertTrue((root / "bob" / "tarot__basics.md").exists())

    def test_owner_crud_stays_scoped_under_collision(self):
        a = self._auth("alice@e.com")
        b = self._auth("bob@e.com")
        self._mine(_md(body="Alice's text."), a)
        self._mine(_md(body="Bob's text."), b)

        # Each owner reads/edits/deletes THEIR deck at the same mine path.
        src_a = self.client.get("/api/decks/mine/tarot/basics", headers=a).json()
        self.assertIn("Alice's text.", src_a["markdown"])

        res = self.client.put(
            "/api/decks/mine/tarot/basics",
            json={"markdown": _md(body="Bob edited.")},
            headers=b,
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn(
            "Alice's text.",
            self.client.get("/api/decks/mine/tarot/basics", headers=a).json()["markdown"],
        )

        self.assertEqual(
            self.client.delete("/api/decks/mine/tarot/basics", headers=a).status_code,
            204,
        )
        # Bob's deck survives Alice's delete.
        self.assertEqual(
            self.client.get("/api/decks/u/bob/tarot/basics").status_code, 200
        )


class TestLegacyFlatFiles(_AppTestCase):
    def _plant_legacy_deck(self, auth_email="alice@e.com"):
        """Simulate a pre-migration deck: flat file + row pointing at it."""
        auth = self._auth(auth_email)
        res = self._mine(_md(), auth)
        assert res.status_code == 201
        # Rewire to a flat filename, as the migration leaves legacy decks.
        db = self.Session()
        deck = db.scalars(select(Deck)).one()
        root = Path(self._tmp.name)
        (root / deck.filename).rename(root / "tarot__basics.md")
        deck.filename = "tarot__basics.md"
        db.commit()
        db.close()
        return auth

    def test_recreate_same_identity_updates_in_place(self):
        auth = self._plant_legacy_deck()
        # Re-creating the same topic+title must refresh the legacy row, not
        # add a duplicate alongside it under a new subdir filename.
        res = self._mine(_md(body="Updated."), auth)
        self.assertEqual(res.status_code, 201)
        db = self.Session()
        decks = db.scalars(select(Deck)).all()
        self.assertEqual(len(decks), 1)
        self.assertEqual(decks[0].filename, "tarot__basics.md")  # file unmoved
        db.close()
        self.assertIn(
            "Updated.",
            (Path(self._tmp.name) / "tarot__basics.md").read_text(encoding="utf-8"),
        )

    def test_rename_moves_into_subdir_and_keeps_created_at(self):
        auth = self._plant_legacy_deck()
        db = self.Session()
        created_at = db.scalars(select(Deck)).one().created_at
        db.close()

        res = self.client.put(
            "/api/decks/mine/tarot/basics",
            json={"markdown": _md(title="Advanced")},
            headers=auth,
        )
        self.assertEqual(res.status_code, 200)
        db = self.Session()
        deck = db.scalars(select(Deck)).one()
        self.assertEqual(deck.filename, "alice/tarot__advanced.md")
        self.assertEqual(deck.created_at, created_at)
        db.close()
        root = Path(self._tmp.name)
        self.assertFalse((root / "tarot__basics.md").exists())
        self.assertTrue((root / "alice" / "tarot__advanced.md").exists())

    def test_rename_onto_own_other_deck_is_rejected(self):
        auth = self._auth("alice@e.com")
        self._mine(_md(title="Basics"), auth)
        self._mine(_md(title="Advanced"), auth)
        res = self.client.put(
            "/api/decks/mine/tarot/advanced",
            json={"markdown": _md(title="Basics")},
            headers=auth,
        )
        self.assertEqual(res.status_code, 409)


class TestAuthorEndpoints(_AppTestCase):
    def test_profile_and_decks_show_public_approved_only(self):
        a = self._auth("alice@e.com")
        self._mine(_md(title="Public One"), a)
        self._mine(_md(title="Hidden", body="x").replace(
            "theme: default", "theme: default\nvisibility: private"
        ), a)

        profile = self.client.get("/api/users/alice").json()
        self.assertEqual(profile["handle"], "alice")
        self.assertEqual(profile["deck_count"], 1)

        decks = self.client.get("/api/users/alice/decks").json()
        self.assertEqual([d["slug"] for d in decks], ["public-one"])
        self.assertEqual(decks[0]["url"], "/u/alice/tarot/public-one")

        topic = self.client.get("/api/users/alice/topics/tarot").json()
        self.assertEqual([d["slug"] for d in topic["decks"]], ["public-one"])

        self.assertEqual(self.client.get("/api/users/nobody").status_code, 404)


class TestEditionUrlShape(_AppTestCase):
    EDITION = Edition.STANDALONE

    def test_standalone_keeps_flat_urls(self):
        a = self._auth("alice@e.com")
        res = self._mine(_md(), a)
        self.assertEqual(res.json()["url"], "/tarot/basics")
        self.assertFalse(self.client.get("/api/meta").json()["user_spaces_enabled"])
        # Flat reader is canonical; the namespaced resolver still works too.
        self.assertEqual(self.client.get("/api/decks/tarot/basics").status_code, 200)
        self.assertEqual(
            self.client.get("/api/decks/u/alice/tarot/basics").status_code, 200
        )

    def test_server_emits_namespaced_urls(self):
        settings.EDITION = Edition.SERVER
        a = self._auth("alice@e.com")
        res = self._mine(_md(), a)
        self.assertEqual(res.json()["url"], "/u/alice/tarot/basics")
        self.assertTrue(self.client.get("/api/meta").json()["user_spaces_enabled"])


if __name__ == "__main__":
    unittest.main()
