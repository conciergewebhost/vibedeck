"""Tests for the email delivery backends (resend / smtp / log) and the
config-level validation of the email settings.

Backend selection is driven by the long-lived `settings` singleton, so the
tests mutate its provider fields directly (the same save/restore pattern the
edition tests use) — `settings.email_delivery` is a property and reflects
the change immediately.

Run from the backend/ directory:
    python -m unittest tests.test_email_backends -v
"""

import os
import sys
import unittest
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

from pydantic import ValidationError  # noqa: E402

from config import Settings, settings  # noqa: E402
from services import email as email_service  # noqa: E402


class _ProviderTestCase(unittest.TestCase):
    """Save/restore the provider-selection fields on the settings singleton."""

    _FIELDS = (
        "RESEND_API_KEY",
        "SMTP_HOST",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_TLS",
        "EMAIL_FROM_ADDRESS",
    )

    def setUp(self):
        self._saved = {f: getattr(settings, f) for f in self._FIELDS}

    def tearDown(self):
        for field, value in self._saved.items():
            setattr(settings, field, value)


class TestBackendSelection(_ProviderTestCase):
    def test_resend_key_selects_resend(self):
        settings.RESEND_API_KEY = "re_x"
        settings.SMTP_HOST = ""
        self.assertEqual(settings.email_delivery, "resend")

    def test_smtp_host_selects_smtp(self):
        settings.RESEND_API_KEY = ""
        settings.SMTP_HOST = "mail.example.com"
        self.assertEqual(settings.email_delivery, "smtp")

    def test_no_provider_selects_log(self):
        settings.RESEND_API_KEY = ""
        settings.SMTP_HOST = ""
        self.assertEqual(settings.email_delivery, "log")

    def test_send_dispatches_to_selected_backend(self):
        settings.RESEND_API_KEY = ""
        settings.SMTP_HOST = "mail.example.com"
        with mock.patch.object(email_service, "_send_smtp") as smtp:
            email_service._send(to="a@e.com", subject="s", html="<p>h</p>", text="t")
        smtp.assert_called_once()


class TestLogBackend(_ProviderTestCase):
    def test_log_mode_records_the_plain_text_body(self):
        settings.RESEND_API_KEY = ""
        settings.SMTP_HOST = ""
        with self.assertLogs("services.email", level="WARNING") as captured:
            email_service.send_magic_link(
                to="solo@e.com",
                link="https://test.example/auth/verify?token=abc123",
                is_signup=False,
            )
        output = "\n".join(captured.output)
        # The link must be copy-pasteable from the server log.
        self.assertIn("https://test.example/auth/verify?token=abc123", output)
        self.assertIn("solo@e.com", output)


class _FakeSMTP:
    """Recording stand-in for smtplib.SMTP (context-manager protocol)."""

    instances: list["_FakeSMTP"] = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.calls: list[tuple] = []
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.calls.append(("starttls",))

    def login(self, username, password):
        self.calls.append(("login", username, password))

    def send_message(self, msg):
        self.calls.append(("send_message", msg))


class TestSmtpBackend(_ProviderTestCase):
    def setUp(self):
        super().setUp()
        _FakeSMTP.instances = []
        settings.RESEND_API_KEY = ""
        settings.SMTP_HOST = "mail.example.com"
        settings.EMAIL_FROM_ADDRESS = "noreply@example.com"
        self._patcher = mock.patch.object(email_service.smtplib, "SMTP", _FakeSMTP)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        super().tearDown()

    def _send(self):
        email_service.send_magic_link(
            to="a@e.com", link="https://test.example/x", is_signup=True
        )

    def test_tls_and_login_when_configured(self):
        settings.SMTP_TLS = True
        settings.SMTP_USERNAME = "mailer"
        settings.SMTP_PASSWORD = "hunter2"
        self._send()
        (server,) = _FakeSMTP.instances
        self.assertEqual(server.host, "mail.example.com")
        self.assertEqual(
            [c[0] for c in server.calls], ["starttls", "login", "send_message"]
        )
        self.assertEqual(server.calls[1], ("login", "mailer", "hunter2"))

    def test_plain_relay_skips_tls_and_login(self):
        settings.SMTP_TLS = False
        settings.SMTP_USERNAME = ""
        self._send()
        (server,) = _FakeSMTP.instances
        self.assertEqual([c[0] for c in server.calls], ["send_message"])

    def test_message_carries_both_bodies_and_the_link(self):
        self._send()
        (server,) = _FakeSMTP.instances
        msg = server.calls[-1][1]
        self.assertEqual(msg["To"], "a@e.com")
        self.assertIn("noreply@example.com", msg["From"])
        body = msg.get_body(preferencelist=("plain",)).get_content()
        self.assertIn("https://test.example/x", body)
        html = msg.get_body(preferencelist=("html",)).get_content()
        self.assertIn("https://test.example/x", html)


# Valid baseline kwargs for constructing Settings directly. `_env_file=None`
# skips the repo's .env, but pydantic-settings still reads os.environ — and
# this module pins RESEND_API_KEY/EMAIL_FROM_ADDRESS there for the app-level
# tests — so the email fields are pinned blank explicitly. Per-test overrides
# (later duplicate kwargs) would collide, so tests build dicts via `|`.
_BASE_KWARGS = dict(
    _env_file=None,
    DATABASE_URL="postgresql+psycopg://u:p@localhost/db",
    SECRET_KEY="s",
    UPLOAD_DIR="/tmp",
    UPLOAD_TOKEN="t",
    UPLOAD_OWNER_EMAIL="owner@example.com",
    NEW_USER_CODE="code",
    RESEND_API_KEY="",
    EMAIL_FROM_ADDRESS="",
)


class TestConfigValidation(unittest.TestCase):
    def test_no_email_settings_is_valid_log_mode(self):
        s = Settings(**_BASE_KWARGS)
        self.assertEqual(s.email_delivery, "log")

    def test_both_providers_rejected(self):
        with self.assertRaises(ValidationError):
            Settings(
                **_BASE_KWARGS
                | dict(
                    RESEND_API_KEY="re_x",
                    SMTP_HOST="mail.example.com",
                    EMAIL_FROM_ADDRESS="noreply@example.com",
                )
            )

    def test_provider_without_from_address_rejected(self):
        with self.assertRaises(ValidationError):
            Settings(**_BASE_KWARGS | dict(SMTP_HOST="mail.example.com"))
        with self.assertRaises(ValidationError):
            Settings(**_BASE_KWARGS | dict(RESEND_API_KEY="re_x"))

    def test_smtp_credentials_without_host_rejected(self):
        with self.assertRaises(ValidationError):
            Settings(**_BASE_KWARGS | dict(SMTP_USERNAME="mailer"))

    def test_site_password_flag(self):
        self.assertFalse(Settings(**_BASE_KWARGS).site_password_enabled)
        self.assertTrue(
            Settings(**_BASE_KWARGS | dict(SITE_PASSWORD="pw")).site_password_enabled
        )


if __name__ == "__main__":
    unittest.main()
