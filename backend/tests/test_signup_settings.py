"""Signup-gate settings tests:
  - defaults match the pre-feature behavior (code required, value from
    NEW_USER_CODE) when the site_settings table is empty
  - GET/PUT /api/admin/signup-settings is owner-only (admins 403)
  - disabling the requirement lets a new email get a signup link without
    a code; re-enabling enforces it again — all without a restart
  - changing the code: old code refused, new code accepted; short code 400
  - /api/meta reflects the runtime flag

From backend/:  python -m unittest tests.test_signup_settings
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
from config import Edition, settings  # noqa: E402
from database import Base, get_db  # noqa: E402
from models import User  # noqa: E402
from routers import auth as auth_router  # noqa: E402
from services.auth import create_access_token, hash_password  # noqa: E402

OWNER = "owner@example.com"


class _AppTestCase(unittest.TestCase):
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
        settings.EDITION = Edition.SERVER  # signup flows are server-only
        auth_router._link_limiter.clear()
        auth_router._bad_code_limiter.clear()

    def tearDown(self):
        main.app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        settings.UPLOAD_DIR = self._orig_upload_dir
        settings.EDITION = self._orig_edition
        self._tmp.cleanup()

    def _make_user(self, email, is_admin=False):
        db = self.Session()
        db.add(
            User(
                email=email,
                handle=email.split("@", 1)[0],
                hashed_password=hash_password("x"),
                is_admin=is_admin,
            )
        )
        db.commit()
        db.close()
        return {"Authorization": f"Bearer {create_access_token(subject=email)}"}

    def _request_link(self, email, code=None, handle="newbie"):
        return self.client.post(
            "/api/auth/request-link",
            json={"email": email, "code": code, "handle": handle},
        )

    def _put(self, auth, require_code, code=None):
        return self.client.put(
            "/api/admin/signup-settings",
            json={"require_code": require_code, "code": code},
            headers=auth,
        )


class TestSignupSettings(_AppTestCase):
    def test_defaults_match_env(self):
        owner = self._make_user(OWNER)
        s = self.client.get("/api/admin/signup-settings", headers=owner).json()
        self.assertEqual(s, {"require_code": True, "code": "let-me-in"})
        self.assertTrue(self.client.get("/api/meta").json()["signup_code_required"])

    def test_owner_only(self):
        admin = self._make_user("mod@e.com", is_admin=True)
        self.assertEqual(
            self.client.get("/api/admin/signup-settings", headers=admin).status_code,
            403,
        )
        self.assertEqual(self._put(admin, False).status_code, 403)

    @mock.patch("routers.auth.send_magic_link")
    def test_disable_opens_signup_without_code(self, sender):
        owner = self._make_user(OWNER)

        # Gate on (default): no code → 403, nothing sent.
        self.assertEqual(self._request_link("new@e.com").status_code, 403)
        sender.assert_not_called()

        # Owner opens the gate — takes effect immediately, no restart.
        res = self._put(owner, False)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["require_code"])
        self.assertFalse(self.client.get("/api/meta").json()["signup_code_required"])

        self.assertEqual(self._request_link("new@e.com").status_code, 200)
        sender.assert_called_once()
        self.assertTrue(sender.call_args.kwargs["is_signup"])

        # Handle is still required even with the gate open.
        self.assertEqual(
            self._request_link("other@e.com", handle=None).status_code, 400
        )

        # Re-enable: enforced again.
        self._put(owner, True)
        self.assertEqual(self._request_link("late@e.com").status_code, 403)

    @mock.patch("routers.auth.send_magic_link")
    def test_change_code(self, sender):
        owner = self._make_user(OWNER)
        res = self._put(owner, True, code="fresh-code-42")
        self.assertEqual(res.json()["code"], "fresh-code-42")

        # Old env code refused; new code accepted.
        self.assertEqual(
            self._request_link("a@e.com", code="let-me-in").status_code, 403
        )
        self.assertEqual(
            self._request_link("a@e.com", code="fresh-code-42").status_code, 200
        )

        # Blank code on PUT leaves the stored code unchanged.
        self._put(owner, True, code=None)
        s = self.client.get("/api/admin/signup-settings", headers=owner).json()
        self.assertEqual(s["code"], "fresh-code-42")

    def test_short_code_rejected(self):
        owner = self._make_user(OWNER)
        res = self._put(owner, True, code="abc")
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
