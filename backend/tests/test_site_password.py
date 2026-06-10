"""Tests for the shared site-password login (POST /api/auth/site-password)
and the auth_methods / email_delivery flags on /api/meta.

Runs against the FastAPI app with an in-memory SQLite DB — same wiring as
tests/test_magic_auth.py.

Run from the backend/ directory:
    python -m unittest tests.test_site_password -v
"""

import os
import sys
import unittest
from pathlib import Path

# Importable backend + minimal env so `config` loads without a real .env.
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
os.environ.setdefault("BASE_URL", "https://test.example")

import jwt  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import main  # noqa: E402
from config import settings  # noqa: E402
from database import Base, get_db  # noqa: E402
from models import User  # noqa: E402
from routers import auth as auth_router  # noqa: E402
from services.auth import hash_password  # noqa: E402


class _AppTestCase(unittest.TestCase):
    """Base class wiring the app to an isolated in-memory SQLite DB."""

    def setUp(self):
        self._prev_site_password = settings.SITE_PASSWORD

        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        TestingSession = sessionmaker(bind=self.engine, autoflush=False)

        def override_get_db():
            db = TestingSession()
            try:
                yield db
            finally:
                db.close()

        main.app.dependency_overrides[get_db] = override_get_db
        self.Session = TestingSession
        self.client = TestClient(main.app)
        auth_router._password_limiter.clear()

    def tearDown(self):
        settings.SITE_PASSWORD = self._prev_site_password
        main.app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def add_owner(self, active=True):
        db = self.Session()
        db.add(
            User(
                email=settings.UPLOAD_OWNER_EMAIL,
                handle="owner",
                hashed_password=hash_password("x"),
                is_active=active,
            )
        )
        db.commit()
        db.close()

    def attempt(self, password):
        return self.client.post(
            "/api/auth/site-password", json={"password": password}
        )


class TestSitePasswordLogin(_AppTestCase):
    def test_unset_password_means_endpoint_does_not_exist(self):
        settings.SITE_PASSWORD = ""
        self.add_owner()
        self.assertEqual(self.attempt("anything").status_code, 404)

    def test_correct_password_returns_owner_session(self):
        settings.SITE_PASSWORD = "open-sesame"
        self.add_owner()
        resp = self.attempt("open-sesame")
        self.assertEqual(resp.status_code, 200)
        claims = jwt.decode(
            resp.json()["access_token"],
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        self.assertEqual(claims["sub"], settings.UPLOAD_OWNER_EMAIL)

    def test_wrong_password_rejected(self):
        settings.SITE_PASSWORD = "open-sesame"
        self.add_owner()
        self.assertEqual(self.attempt("wrong").status_code, 401)

    def test_empty_submission_rejected(self):
        settings.SITE_PASSWORD = "open-sesame"
        self.add_owner()
        self.assertEqual(self.attempt("").status_code, 401)

    def test_unprovisioned_owner_is_a_server_error(self):
        settings.SITE_PASSWORD = "open-sesame"
        self.assertEqual(self.attempt("open-sesame").status_code, 500)

    def test_inactive_owner_is_a_server_error(self):
        settings.SITE_PASSWORD = "open-sesame"
        self.add_owner(active=False)
        self.assertEqual(self.attempt("open-sesame").status_code, 500)

    def test_attempts_are_rate_limited_per_ip(self):
        settings.SITE_PASSWORD = "open-sesame"
        self.add_owner()
        for _ in range(settings.RATE_LIMIT_REQUESTS_PER_HOUR):
            self.assertEqual(self.attempt("wrong").status_code, 401)
        blocked = self.attempt("wrong")
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Retry-After", blocked.headers)

    def test_password_login_shares_the_rate_limit(self):
        # /api/auth/token and /site-password guard the same limiter, so an
        # attacker can't double their guesses by alternating endpoints.
        settings.SITE_PASSWORD = "open-sesame"
        self.add_owner()
        for _ in range(settings.RATE_LIMIT_REQUESTS_PER_HOUR):
            self.attempt("wrong")
        resp = self.client.post(
            "/api/auth/token",
            data={"username": "owner@example.com", "password": "wrong"},
        )
        self.assertEqual(resp.status_code, 429)


class TestMetaAuthFlags(_AppTestCase):
    def test_site_password_flag_follows_setting(self):
        settings.SITE_PASSWORD = ""
        meta = self.client.get("/api/meta").json()
        self.assertEqual(
            meta["auth_methods"],
            {"magic_link": True, "password": True, "site_password": False},
        )
        settings.SITE_PASSWORD = "open-sesame"
        meta = self.client.get("/api/meta").json()
        self.assertTrue(meta["auth_methods"]["site_password"])

    def test_email_delivery_mode_is_exposed(self):
        # The test env pins RESEND_API_KEY, so resend mode is reported.
        self.assertEqual(self.client.get("/api/meta").json()["email_delivery"], "resend")


if __name__ == "__main__":
    unittest.main()
