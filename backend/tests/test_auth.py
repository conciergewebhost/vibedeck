"""Unit tests for the auth service (no DB required).

Run from the backend/ directory:
    python -m unittest tests.test_auth -v
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

import jwt  # noqa: E402

from services.auth import (  # noqa: E402
    create_access_token,
    hash_password,
    verify_password,
)
from config import settings  # noqa: E402


class TestPasswordHashing(unittest.TestCase):
    def test_hash_and_verify_roundtrip(self):
        h = hash_password("correct horse battery staple")
        self.assertTrue(h.startswith("$2"))
        self.assertTrue(verify_password("correct horse battery staple", h))
        self.assertFalse(verify_password("wrong", h))

    def test_verify_fails_closed_on_malformed_hash(self):
        # The seed user's hash is "!" — must return False, not raise.
        self.assertFalse(verify_password("anything", "!"))

    def test_long_password_truncated_not_crashed(self):
        long_pw = "a" * 200
        h = hash_password(long_pw)
        self.assertTrue(verify_password(long_pw, h))


class TestAccessToken(unittest.TestCase):
    def test_token_roundtrip(self):
        token = create_access_token(subject="alice@example.com")
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        self.assertEqual(payload["sub"], "alice@example.com")
        self.assertIn("exp", payload)

    def test_token_signature_is_checked(self):
        token = create_access_token(subject="alice@example.com")
        with self.assertRaises(jwt.InvalidSignatureError):
            jwt.decode(token, "wrong-secret", algorithms=[settings.JWT_ALGORITHM])


if __name__ == "__main__":
    unittest.main()
