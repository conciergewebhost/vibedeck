"""Quotas + abuse-control tests:
  - per-user deck/theme creation caps (server edition; admins exempt;
    re-saving an existing deck doesn't count against the cap)
  - reader reports: filing, per-reporter dedupe, the distinct-reporter
    auto-quarantine threshold, approve-clears-reports, rate limiting
  - ban/deactivate: content hides everywhere, login paths refuse, the
    authz matrix, reactivation restores

Runs against an in-memory DB with an isolated temp UPLOAD_DIR. From
backend/:  python -m unittest tests.test_abuse_controls
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
from models import ModerationEvent, Report, User  # noqa: E402
from routers import reports as reports_router  # noqa: E402
from services.auth import create_access_token, create_magic_token, hash_password  # noqa: E402

OWNER = "owner@example.com"


def _md(topic="Tarot", title="Basics", body="One idea.") -> str:
    return (
        "---\n"
        f"title: {title}\nauthor: A\ntopic: {topic}\nkeywords: [x]\ntheme: default\n"
        "---\n---\ntype: concept\n---\n"
        f"{body}\n"
    )


THEME_CSS = ":root { --vd-bg: #111; }"


class _AppTestCase(unittest.TestCase):
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
        reports_router._report_limiter.clear()

    def tearDown(self):
        main.app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        settings.UPLOAD_DIR = self._orig_upload_dir
        settings.EDITION = self._orig_edition
        self._tmp.cleanup()

    def _make_user(self, email, is_admin=False, active=True):
        db = self.Session()
        u = User(
            email=email,
            handle=email.split("@", 1)[0],
            hashed_password=hash_password("x"),
            is_admin=is_admin,
            is_active=active,
        )
        db.add(u)
        db.commit()
        uid = u.id
        db.close()
        return uid

    def _auth(self, email):
        return {"Authorization": f"Bearer {create_access_token(subject=email)}"}

    def _mine(self, content, auth):
        return self.client.post(
            "/api/decks/mine", json={"markdown": content}, headers=auth
        )

    def _report(self, deck_id, ip, reason="spam", auth=None):
        headers = {"X-Forwarded-For": ip, **(auth or {})}
        return self.client.post(
            "/api/reports",
            json={"deck_id": deck_id, "reason": reason},
            headers=headers,
        )

    def _deck_id(self, auth):
        return self.client.get("/api/decks/mine", headers=auth).json()[0]["id"]


class TestQuotas(_AppTestCase):
    def test_deck_cap_blocks_new_but_not_resave(self):
        self._make_user("a@e.com")
        a = self._auth("a@e.com")
        orig = settings.QUOTA_MAX_DECKS
        settings.QUOTA_MAX_DECKS = 1
        try:
            self.assertEqual(self._mine(_md(title="One"), a).status_code, 201)
            res = self._mine(_md(title="Two"), a)
            self.assertEqual(res.status_code, 403)
            self.assertIn("limit", res.json()["detail"])
            # Re-saving the existing deck is a refresh, not growth.
            self.assertEqual(
                self._mine(_md(title="One", body="Edited."), a).status_code, 201
            )
        finally:
            settings.QUOTA_MAX_DECKS = orig

    def test_admins_and_owner_are_exempt(self):
        self._make_user("mod@e.com", is_admin=True)
        self._make_user(OWNER)
        orig = settings.QUOTA_MAX_DECKS
        settings.QUOTA_MAX_DECKS = 1
        try:
            mod = self._auth("mod@e.com")
            self.assertEqual(self._mine(_md(title="One"), mod).status_code, 201)
            self.assertEqual(self._mine(_md(title="Two"), mod).status_code, 201)
            owner = self._auth(OWNER)
            self.assertEqual(self._mine(_md(title="Three"), owner).status_code, 201)
        finally:
            settings.QUOTA_MAX_DECKS = orig

    def test_theme_cap(self):
        self._make_user("a@e.com")
        a = self._auth("a@e.com")
        orig = settings.QUOTA_MAX_THEMES
        settings.QUOTA_MAX_THEMES = 1
        try:
            r1 = self.client.post(
                "/api/themes", json={"name": "First", "css": THEME_CSS}, headers=a
            )
            self.assertEqual(r1.status_code, 201)
            r2 = self.client.post(
                "/api/themes", json={"name": "Second", "css": THEME_CSS}, headers=a
            )
            self.assertEqual(r2.status_code, 403)
        finally:
            settings.QUOTA_MAX_THEMES = orig


class TestQuotasStandalone(_AppTestCase):
    EDITION = Edition.STANDALONE

    def test_caps_inert_in_standalone(self):
        self._make_user("a@e.com")
        a = self._auth("a@e.com")
        orig = settings.QUOTA_MAX_DECKS
        settings.QUOTA_MAX_DECKS = 1
        try:
            self.assertEqual(self._mine(_md(title="One"), a).status_code, 201)
            self.assertEqual(self._mine(_md(title="Two"), a).status_code, 201)
        finally:
            settings.QUOTA_MAX_DECKS = orig


class TestReports(_AppTestCase):
    def setUp(self):
        super().setUp()
        self._make_user("author@e.com")
        self.author = self._auth("author@e.com")
        self._mine(_md(), self.author)
        self.deck_id = self._deck_id(self.author)

    def test_report_files_and_dedupes_per_reporter(self):
        self.assertEqual(self._report(self.deck_id, "1.1.1.1").status_code, 200)
        # Same IP again: silent no-op, no extra weight.
        self.assertEqual(self._report(self.deck_id, "1.1.1.1").status_code, 200)
        db = self.Session()
        self.assertEqual(len(db.scalars(select(Report)).all()), 1)
        db.close()
        # Deck still public — below the threshold.
        self.assertEqual(self.client.get("/api/decks/tarot/basics").status_code, 200)

    def test_third_distinct_reporter_quarantines(self):
        self._report(self.deck_id, "1.1.1.1")
        self._report(self.deck_id, "2.2.2.2", reason="harmful")
        self.assertEqual(self.client.get("/api/decks/tarot/basics").status_code, 200)
        self._report(self.deck_id, "3.3.3.3")

        # Hidden from the public reader, into the flagged queue, event logged.
        self.assertEqual(self.client.get("/api/decks/tarot/basics").status_code, 404)
        owner = self._auth_owner()
        queue = self.client.get("/api/admin/flagged", headers=owner).json()
        self.assertEqual([d["id"] for d in queue], [self.deck_id])
        self.assertIn("reported by 3 readers", queue[0]["moderation_reasons"])
        db = self.Session()
        events = db.scalars(select(ModerationEvent)).all()
        self.assertEqual([e.action for e in events], ["flag"])
        db.close()

        # The Reports queue shows the grouped item.
        reports = self.client.get("/api/admin/reports", headers=owner).json()
        self.assertEqual(reports[0]["report_count"], 3)
        self.assertEqual(reports[0]["reasons"], {"spam": 2, "harmful": 1})

    def test_approve_clears_reports_and_restores(self):
        for ip in ("1.1.1.1", "2.2.2.2", "3.3.3.3"):
            self._report(self.deck_id, ip)
        owner = self._auth_owner()
        res = self.client.post(
            f"/api/admin/decks/{self.deck_id}/approve", headers=owner
        )
        self.assertEqual(res.status_code, 204)
        self.assertEqual(self.client.get("/api/decks/tarot/basics").status_code, 200)
        self.assertEqual(self.client.get("/api/admin/reports", headers=owner).json(), [])
        # One fresh report doesn't instantly re-quarantine (counts reset).
        self._report(self.deck_id, "4.4.4.4")
        self.assertEqual(self.client.get("/api/decks/tarot/basics").status_code, 200)

    def test_signed_in_reporters_count_by_account(self):
        self._make_user("r1@e.com")
        # The same account from two IPs is ONE distinct reporter.
        r1 = self._auth("r1@e.com")
        self._report(self.deck_id, "5.5.5.5", auth=r1)
        self._report(self.deck_id, "6.6.6.6", auth=r1)
        owner = self._auth_owner()
        reports = self.client.get("/api/admin/reports", headers=owner).json()
        self.assertEqual(reports[0]["report_count"], 1)

    def test_rate_limit(self):
        limit = settings.RATE_LIMIT_REPORTS_PER_HOUR
        # Distinct decks so dedupe doesn't absorb the calls; same IP.
        ids = []
        for n in range(limit):
            self._mine(_md(title=f"Deck {n}"), self.author)
        for d in self.client.get("/api/decks/mine", headers=self.author).json():
            ids.append(d["id"])
        for n in range(limit):
            self.assertEqual(self._report(ids[n], "9.9.9.9").status_code, 200)
        blocked = self._report(ids[0], "9.9.9.9")
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Retry-After", blocked.headers)

    def test_unknown_deck_404(self):
        self.assertEqual(self._report(99999, "1.1.1.1").status_code, 404)

    def _auth_owner(self):
        self._make_user(OWNER)
        return self._auth(OWNER)


class TestBan(_AppTestCase):
    def setUp(self):
        super().setUp()
        self._make_user(OWNER)
        self.owner = self._auth(OWNER)
        self.uid = self._make_user("a@e.com")
        self.a = self._auth("a@e.com")
        self._mine(_md(), self.a)

    def _deactivate(self, uid, auth):
        return self.client.post(f"/api/admin/users/{uid}/deactivate", headers=auth)

    def test_ban_hides_everything_and_reactivate_restores(self):
        # Visible before.
        self.assertEqual(self.client.get("/api/decks/tarot/basics").status_code, 200)
        self.assertEqual(self.client.get("/api/users/a").status_code, 200)

        self.assertEqual(self._deactivate(self.uid, self.owner).status_code, 204)

        self.assertEqual(self.client.get("/api/decks/tarot/basics").status_code, 404)
        self.assertEqual(
            self.client.get("/api/decks/u/a/tarot/basics").status_code, 404
        )
        self.assertEqual(self.client.get("/api/decks/public").json(), [])
        self.assertEqual(self.client.get("/api/topics").json(), [])
        self.assertEqual(self.client.get("/api/users/a").status_code, 404)
        self.assertEqual(
            self.client.get("/api/users/a/topics/tarot").status_code, 404
        )
        # Their session token no longer works.
        self.assertEqual(
            self.client.get("/api/decks/mine", headers=self.a).status_code, 401
        )

        res = self.client.post(
            f"/api/admin/users/{self.uid}/reactivate", headers=self.owner
        )
        self.assertEqual(res.status_code, 204)
        self.assertEqual(self.client.get("/api/decks/tarot/basics").status_code, 200)
        self.assertEqual(self.client.get("/api/users/a").status_code, 200)

    def test_banned_email_cannot_reenter(self):
        self._deactivate(self.uid, self.owner)
        # Magic-link request refuses outright (no signup-branch fallthrough).
        res = self.client.post(
            "/api/auth/request-link",
            json={"email": "a@e.com", "code": settings.NEW_USER_CODE, "handle": "a2"},
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("disabled", res.json()["detail"])
        # Replaying an old signup link fails with the generic message.
        token = create_magic_token("a@e.com", is_signup=True, handle="a")
        res = self.client.post("/api/auth/verify", json={"token": token})
        self.assertEqual(res.status_code, 400)

    def test_authz_matrix(self):
        mod_id = self._make_user("mod@e.com", is_admin=True)
        mod2_id = self._make_user("mod2@e.com", is_admin=True)
        mod = self._auth("mod@e.com")

        # Admin bans a regular user: allowed.
        self.assertEqual(self._deactivate(self.uid, mod).status_code, 204)
        # Admin bans an admin: owner-only.
        self.assertEqual(self._deactivate(mod2_id, mod).status_code, 403)
        # Owner bans an admin: allowed.
        self.assertEqual(self._deactivate(mod2_id, self.owner).status_code, 204)
        # Nobody bans the owner.
        owner_id = self.client.get("/api/users/me", headers=self.owner).json()["id"]
        self.assertEqual(self._deactivate(owner_id, self.owner).status_code, 400)
        # Nobody bans themselves.
        self.assertEqual(self._deactivate(mod_id, mod).status_code, 400)
        # Unknown user.
        self.assertEqual(self._deactivate(99999, self.owner).status_code, 404)


if __name__ == "__main__":
    unittest.main()
