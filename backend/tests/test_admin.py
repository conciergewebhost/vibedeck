"""Admin portal tests:
  - admin endpoints are owner-only (non-owner → 403)
  - list_users returns the right shape/order/counts
  - record_login stamps last_login_at on magic-link verify

In-memory DB + isolated temp UPLOAD_DIR (never touches real deck files).
From backend/:  python -m unittest tests.test_admin
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
from config import settings  # noqa: E402
from database import Base, get_db  # noqa: E402
from models import User  # noqa: E402
from services import decks as decks_service  # noqa: E402
from services.auth import (  # noqa: E402
    create_access_token,
    create_magic_token,
    hash_password,
)

OWNER = "owner@example.com"  # == UPLOAD_OWNER_EMAIL in the test env


def _deck(topic, title):
    return (
        f"---\ntitle: {title}\nauthor: A\ntopic: {topic}\nkeywords: [x]\n"
        "theme: default\n---\n---\ntype: title\n---\n# Hi\n"
    )


class _Base(unittest.TestCase):
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

    def tearDown(self):
        main.app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        settings.UPLOAD_DIR = self._orig_upload_dir
        self._tmp.cleanup()

    def _make_user(self, email):
        db = self.Session()
        u = User(
            email=email,
            handle=email.split("@", 1)[0],
            hashed_password=hash_password("x"),
        )
        db.add(u)
        db.commit()
        uid = u.id
        db.close()
        return uid

    def _auth(self, email):
        return {"Authorization": f"Bearer {create_access_token(subject=email)}"}


class TestAdminAuthz(_Base):
    def test_non_owner_forbidden(self):
        self._make_user(OWNER)
        self._make_user("user@e.com")
        u = self._auth("user@e.com")
        self.assertEqual(self.client.get("/api/admin/users", headers=u).status_code, 403)
        self.assertEqual(
            self.client.get("/api/admin/users/1/decks", headers=u).status_code, 403
        )
        self.assertEqual(self.client.get("/api/decks", headers=u).status_code, 403)
        self.assertEqual(
            self.client.delete("/api/admin/decks/1", headers=u).status_code, 403
        )
        self.assertEqual(
            self.client.post(
                "/api/decks/upload",
                files={"file": ("d.md", _deck("t", "T"), "text/markdown")},
                headers=u,
            ).status_code,
            403,
        )

    def test_owner_allowed(self):
        self._make_user(OWNER)
        o = self._auth(OWNER)
        self.assertEqual(self.client.get("/api/admin/users", headers=o).status_code, 200)
        self.assertEqual(self.client.get("/api/decks", headers=o).status_code, 200)

    def test_unauthenticated_rejected(self):
        # No token at all → 401 (not 403).
        self.assertEqual(self.client.get("/api/admin/users").status_code, 401)


class TestListUsers(_Base):
    def test_shape_order_counts(self):
        self._make_user(OWNER)  # oldest
        uid1 = self._make_user("u1@e.com")  # owns 2 decks
        self._make_user("u2@e.com")  # newest, no decks

        db = self.Session()
        decks_service.create_user_deck(db, uid1, _deck("alpha", "One"))
        db.commit()
        decks_service.create_user_deck(db, uid1, _deck("alpha", "Two"))
        db.commit()
        db.close()

        rows = self.client.get("/api/admin/users", headers=self._auth(OWNER)).json()
        by_email = {r["email"]: r for r in rows}

        # Newest account first (id desc tiebreak): u2, u1, owner.
        self.assertEqual([r["email"] for r in rows], ["u2@e.com", "u1@e.com", OWNER])
        self.assertEqual(by_email["u1@e.com"]["deck_count"], 2)
        self.assertIsNotNone(by_email["u1@e.com"]["last_deck_at"])
        self.assertEqual(by_email["u2@e.com"]["deck_count"], 0)
        self.assertIsNone(by_email["u2@e.com"]["last_deck_at"])
        # Shape includes the monitoring fields + role flags.
        self.assertEqual(
            set(rows[0]),
            {
                "id",
                "email",
                "created_at",
                "last_login_at",
                "deck_count",
                "last_deck_at",
                "is_admin",
                "is_owner",
                "is_active",
            },
        )
        # The owner row reports admin/owner via config, not the flag.
        self.assertTrue(by_email[OWNER]["is_admin"])
        self.assertTrue(by_email[OWNER]["is_owner"])
        self.assertFalse(by_email["u1@e.com"]["is_admin"])


class TestRecordLogin(_Base):
    def test_verify_sets_last_login(self):
        self._make_user("ml@e.com")
        token = create_magic_token("ml@e.com", is_signup=False)
        r = self.client.post("/api/auth/verify", json={"token": token})
        self.assertEqual(r.status_code, 200)

        db = self.Session()
        u = db.scalar(select(User).where(User.email == "ml@e.com"))
        self.assertIsNotNone(u.last_login_at)
        db.close()


if __name__ == "__main__":
    unittest.main()


class TestRoles(_Base):
    """Promotable admins: is_admin grants the admin surface; role management
    is owner-only; the owner is admin by config, not by flag."""

    def _promote(self, user_id, auth):
        return self.client.post(f"/api/admin/users/{user_id}/promote", headers=auth)

    def test_owner_promotes_and_demotes(self):
        self._make_user(OWNER)
        uid = self._make_user("mod@e.com")
        owner, mod = self._auth(OWNER), self._auth("mod@e.com")

        # Before: no admin surface.
        self.assertEqual(self.client.get("/api/admin/users", headers=mod).status_code, 403)

        self.assertEqual(self._promote(uid, owner).status_code, 204)
        # Effective immediately, across the whole admin surface.
        self.assertEqual(self.client.get("/api/admin/users", headers=mod).status_code, 200)
        self.assertEqual(self.client.get("/api/admin/flagged", headers=mod).status_code, 200)
        self.assertEqual(self.client.get("/api/decks", headers=mod).status_code, 200)

        self.assertEqual(
            self.client.post(f"/api/admin/users/{uid}/demote", headers=owner).status_code,
            204,
        )
        self.assertEqual(self.client.get("/api/admin/users", headers=mod).status_code, 403)

    def test_admins_cannot_manage_roles(self):
        self._make_user(OWNER)
        mod_id = self._make_user("mod@e.com")
        other_id = self._make_user("other@e.com")
        owner, mod = self._auth(OWNER), self._auth("mod@e.com")
        self._promote(mod_id, owner)

        # A promoted admin can use the surface but not mint/remove admins.
        self.assertEqual(self._promote(other_id, mod).status_code, 403)
        self.assertEqual(
            self.client.post(f"/api/admin/users/{mod_id}/demote", headers=mod).status_code,
            403,
        )

    def test_owner_role_is_immutable(self):
        owner_id = self._make_user(OWNER)
        owner = self._auth(OWNER)
        self.assertEqual(self._promote(owner_id, owner).status_code, 400)
        self.assertEqual(
            self.client.post(
                f"/api/admin/users/{owner_id}/demote", headers=owner
            ).status_code,
            400,
        )

    def test_unknown_user_404(self):
        self._make_user(OWNER)
        self.assertEqual(self._promote(999, self._auth(OWNER)).status_code, 404)

    def test_me_carries_role_flags(self):
        self._make_user(OWNER)
        uid = self._make_user("mod@e.com")
        owner, mod = self._auth(OWNER), self._auth("mod@e.com")

        me = self.client.get("/api/users/me", headers=owner).json()
        self.assertTrue(me["is_admin"])
        self.assertTrue(me["is_owner"])

        me = self.client.get("/api/users/me", headers=mod).json()
        self.assertFalse(me["is_admin"])
        self.assertFalse(me["is_owner"])

        self._promote(uid, owner)
        me = self.client.get("/api/users/me", headers=mod).json()
        self.assertTrue(me["is_admin"])
        self.assertFalse(me["is_owner"])
