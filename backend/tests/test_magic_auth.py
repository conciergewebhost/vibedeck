"""Tests for magic-link auth and the sandbox preview endpoint.

Token helpers are tested as pure functions; the request-link/verify/preview
flows run against the FastAPI app with an in-memory SQLite DB and a mocked
email sender, so no Postgres or network is needed.

Run from the backend/ directory:
    python -m unittest tests.test_magic_auth -v
"""

import os
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

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
from config import Edition, settings  # noqa: E402
from database import Base, get_db  # noqa: E402
from models import User  # noqa: E402
from routers import auth as auth_router  # noqa: E402
from services.ratelimit import SlidingWindowLimiter  # noqa: E402
from services.auth import (  # noqa: E402
    create_access_token,
    create_magic_token,
    decode_magic_token,
    hash_password,
)


class TestMagicToken(unittest.TestCase):
    def test_roundtrip_carries_email_and_intent(self):
        token = create_magic_token("alice@example.com", is_signup=True)
        email, is_signup = decode_magic_token(token)
        self.assertEqual(email, "alice@example.com")
        self.assertTrue(is_signup)

    def test_login_token_is_not_signup(self):
        _, is_signup = decode_magic_token(
            create_magic_token("bob@example.com", is_signup=False)
        )
        self.assertFalse(is_signup)

    def test_session_token_rejected_as_magic(self):
        # A normal access token has no "magic" purpose claim.
        with self.assertRaises(jwt.InvalidTokenError):
            decode_magic_token(create_access_token(subject="alice@example.com"))

    def test_expired_token_rejected(self):
        from config import settings

        expired = jwt.encode(
            {
                "sub": "a@e.com",
                "purpose": "magic",
                "signup": True,
                "exp": __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                )
                - timedelta(minutes=1),
            },
            settings.SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        with self.assertRaises(jwt.ExpiredSignatureError):
            decode_magic_token(expired)


class _AppTestCase(unittest.TestCase):
    """Base class wiring the app to an isolated in-memory SQLite DB."""

    def setUp(self):
        # These exercise the multi-user signup/login flow, which only exists
        # in the server edition; pin it regardless of the default edition.
        self._prev_edition = settings.EDITION
        settings.EDITION = Edition.SERVER

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

        # Rate limiters are module-level; reset so tests don't leak counts.
        auth_router._link_limiter.clear()
        auth_router._bad_code_limiter.clear()

    def tearDown(self):
        settings.EDITION = self._prev_edition
        main.app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def add_user(self, email, active=True):
        db = self.Session()
        db.add(User(email=email, hashed_password=hash_password("x"), is_active=active))
        db.commit()
        db.close()


class TestRequestLink(_AppTestCase):
    @mock.patch("routers.auth.send_magic_link")
    def test_new_email_without_code_is_rejected(self, sender):
        resp = self.client.post("/api/auth/request-link", json={"email": "new@e.com"})
        self.assertEqual(resp.status_code, 403)
        sender.assert_not_called()

    @mock.patch("routers.auth.send_magic_link")
    def test_new_email_with_valid_code_sends_signup_link(self, sender):
        resp = self.client.post(
            "/api/auth/request-link",
            json={"email": "new@e.com", "code": settings.NEW_USER_CODE},
        )
        self.assertEqual(resp.status_code, 200)
        sender.assert_called_once()
        self.assertTrue(sender.call_args.kwargs["is_signup"])

    @mock.patch("routers.auth.send_magic_link")
    def test_existing_user_gets_login_link_without_code(self, sender):
        self.add_user("known@e.com")
        resp = self.client.post(
            "/api/auth/request-link", json={"email": "known@e.com"}
        )
        self.assertEqual(resp.status_code, 200)
        sender.assert_called_once()
        self.assertFalse(sender.call_args.kwargs["is_signup"])

    @mock.patch("routers.auth.send_magic_link")
    def test_email_is_normalized_lowercase(self, sender):
        self.client.post(
            "/api/auth/request-link",
            json={"email": "MixedCase@E.com", "code": settings.NEW_USER_CODE},
        )
        self.assertEqual(sender.call_args.kwargs["to"], "mixedcase@e.com")

    @mock.patch("routers.auth.send_magic_link")
    def test_standalone_edition_disables_signup_even_with_code(self, sender):
        # Standalone is single-user: no public sign-up, regardless of the code.
        settings.EDITION = Edition.STANDALONE
        resp = self.client.post(
            "/api/auth/request-link",
            json={"email": "new@e.com", "code": settings.NEW_USER_CODE},
        )
        self.assertEqual(resp.status_code, 403)
        sender.assert_not_called()


class TestSlidingWindowLimiter(unittest.TestCase):
    def test_allows_up_to_limit_then_blocks(self):
        lim = SlidingWindowLimiter()
        t = 1000.0
        for _ in range(3):
            allowed, retry = lim.hit("ip", limit=3, window_seconds=60, now=t)
            self.assertTrue(allowed)
            self.assertEqual(retry, 0)
        allowed, retry = lim.hit("ip", limit=3, window_seconds=60, now=t)
        self.assertFalse(allowed)
        self.assertGreater(retry, 0)

    def test_window_slides(self):
        lim = SlidingWindowLimiter()
        for _ in range(3):
            lim.hit("ip", limit=3, window_seconds=60, now=1000.0)
        # Blocked at t=1000, but allowed again once the window has passed.
        self.assertFalse(lim.hit("ip", 3, 60, now=1000.0)[0])
        self.assertTrue(lim.hit("ip", 3, 60, now=1061.0)[0])

    def test_keys_are_independent(self):
        lim = SlidingWindowLimiter()
        self.assertTrue(lim.hit("a", 1, 60, now=1.0)[0])
        self.assertFalse(lim.hit("a", 1, 60, now=1.0)[0])
        self.assertTrue(lim.hit("b", 1, 60, now=1.0)[0])  # different key


class TestRequestLinkRateLimit(_AppTestCase):
    @mock.patch("routers.auth.send_magic_link")
    def test_invalid_code_attempts_are_throttled(self, sender):
        limit = settings.RATE_LIMIT_BAD_CODE_PER_HOUR
        for _ in range(limit):
            r = self.client.post(
                "/api/auth/request-link",
                json={"email": "guess@e.com", "code": "wrong"},
            )
            self.assertEqual(r.status_code, 403)
        blocked = self.client.post(
            "/api/auth/request-link",
            json={"email": "guess@e.com", "code": "wrong"},
        )
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Retry-After", blocked.headers)
        sender.assert_not_called()

    @mock.patch("routers.auth.send_magic_link")
    def test_overall_per_ip_cap(self, sender):
        self.add_user("known@e.com")
        limit = settings.RATE_LIMIT_REQUESTS_PER_HOUR
        for _ in range(limit):
            r = self.client.post(
                "/api/auth/request-link", json={"email": "known@e.com"}
            )
            self.assertEqual(r.status_code, 200)
        blocked = self.client.post(
            "/api/auth/request-link", json={"email": "known@e.com"}
        )
        self.assertEqual(blocked.status_code, 429)


class TestVerify(_AppTestCase):
    def test_signup_link_creates_user_and_returns_token(self):
        token = create_magic_token("fresh@e.com", is_signup=True)
        resp = self.client.post("/api/auth/verify", json={"token": token})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access_token", resp.json())
        db = self.Session()
        self.assertIsNotNone(
            db.query(User).filter_by(email="fresh@e.com").one_or_none()
        )
        db.close()

    def test_login_link_for_unknown_user_is_rejected(self):
        token = create_magic_token("ghost@e.com", is_signup=False)
        resp = self.client.post("/api/auth/verify", json={"token": token})
        self.assertEqual(resp.status_code, 400)

    def test_garbage_token_is_rejected(self):
        resp = self.client.post("/api/auth/verify", json={"token": "not-a-jwt"})
        self.assertEqual(resp.status_code, 400)


class TestPreview(_AppTestCase):
    SAMPLE = """\
---
title: Sample
author: Tester
topic: sandbox
theme: default
keywords: [demo]
---
---
type: title
---
# Hello
---
type: concept
---
A single idea.
"""

    def test_valid_markdown_returns_deck_detail(self):
        resp = self.client.post("/api/decks/preview", json={"markdown": self.SAMPLE})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["title"], "Sample")
        self.assertEqual(len(data["cards"]), 2)
        self.assertEqual(data["cards"][0]["type"], "title")

    def test_malformed_markdown_returns_400(self):
        resp = self.client.post(
            "/api/decks/preview", json={"markdown": "no frontmatter here"}
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
