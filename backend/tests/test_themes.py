"""Tests for per-user themes (validation + CRUD + ownership) and the deck
"no code" guard.

Pure validators are tested directly; the endpoints run against an in-memory
SQLite DB with a real session token. Run from backend/:
    python -m unittest tests.test_themes -v
"""

import os
import sys
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
from database import Base, get_db  # noqa: E402
from models import User  # noqa: E402
from services.auth import create_access_token, hash_password  # noqa: E402
from services.decks import DeckUnsafe, assert_safe_markup  # noqa: E402
from services.themes import ThemeInvalid, validate_theme_css  # noqa: E402

GOOD_CSS = ":root { --vd-bg: #fff; --vd-text: #111; --vd-accent: #c00; }"


class TestValidateThemeCss(unittest.TestCase):
    def test_accepts_a_real_theme(self):
        validate_theme_css(GOOD_CSS)  # should not raise

    def test_rejects_without_vd_tokens(self):
        with self.assertRaises(ThemeInvalid):
            validate_theme_css("body { color: red; }")

    def test_rejects_import(self):
        with self.assertRaises(ThemeInvalid):
            validate_theme_css(GOOD_CSS + " @import url('evil.css');")

    def test_rejects_expression(self):
        with self.assertRaises(ThemeInvalid):
            validate_theme_css(":root{--vd-bg:expression(alert(1));}")

    def test_rejects_html(self):
        with self.assertRaises(ThemeInvalid):
            validate_theme_css("</style><script>alert(1)</script>" + GOOD_CSS)

    def test_rejects_external_url(self):
        with self.assertRaises(ThemeInvalid):
            validate_theme_css(":root{--vd-bg:url(https://evil.example/x);}--vd-")

    def test_rejects_empty(self):
        with self.assertRaises(ThemeInvalid):
            validate_theme_css("   ")

    def test_allows_child_combinator(self):
        # `>` is a valid CSS combinator and must not be rejected as HTML.
        validate_theme_css(GOOD_CSS + " .reader > .card { color: red; }")


class TestSafeMarkup(unittest.TestCase):
    def test_rejects_script(self):
        with self.assertRaises(DeckUnsafe):
            assert_safe_markup("# Hi\n<script>alert(1)</script>")

    def test_rejects_event_handler(self):
        with self.assertRaises(DeckUnsafe):
            assert_safe_markup('<img src=x onerror="alert(1)">')

    def test_allows_download_link(self):
        # The bundled theming deck uses this — must pass.
        assert_safe_markup('<a href="/themes/default.css" download>Download</a>')

    def test_allows_plain_markdown(self):
        assert_safe_markup("# Title\n\n- a\n- b\n\n**bold** and a [link](/x).")


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

    def tearDown(self):
        main.app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def make_user(self, email):
        db = self.Session()
        db.add(User(email=email, hashed_password=hash_password("x")))
        db.commit()
        db.close()
        return {"Authorization": f"Bearer {create_access_token(subject=email)}"}


class TestThemeEndpoints(_AppTestCase):
    def test_create_list_get_delete(self):
        auth = self.make_user("a@e.com")
        # create
        r = self.client.post(
            "/api/themes", json={"name": "My Theme", "css": GOOD_CSS}, headers=auth
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["slug"], "my-theme")
        # list
        r = self.client.get("/api/themes/mine", headers=auth)
        self.assertEqual([t["slug"] for t in r.json()], ["my-theme"])
        # get css
        r = self.client.get("/api/themes/mine/my-theme.css", headers=auth)
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/css", r.headers["content-type"])
        self.assertIn("--vd-bg", r.text)
        # delete
        r = self.client.delete("/api/themes/mine/my-theme", headers=auth)
        self.assertEqual(r.status_code, 204)
        self.assertEqual(self.client.get("/api/themes/mine", headers=auth).json(), [])

    def test_invalid_css_rejected(self):
        auth = self.make_user("a@e.com")
        r = self.client.post(
            "/api/themes",
            json={"name": "Bad", "css": "@import url(x); --vd-bg:1;"},
            headers=auth,
        )
        self.assertEqual(r.status_code, 400)

    def test_duplicate_name_conflicts(self):
        auth = self.make_user("a@e.com")
        body = {"name": "Dup", "css": GOOD_CSS}
        self.assertEqual(self.client.post("/api/themes", json=body, headers=auth).status_code, 201)
        self.assertEqual(self.client.post("/api/themes", json=body, headers=auth).status_code, 409)

    def test_css_requires_auth(self):
        auth = self.make_user("a@e.com")
        self.client.post("/api/themes", json={"name": "T", "css": GOOD_CSS}, headers=auth)
        self.assertEqual(self.client.get("/api/themes/mine/t.css").status_code, 401)

    def test_themes_are_private_to_owner(self):
        a = self.make_user("a@e.com")
        b = self.make_user("b@e.com")
        self.client.post("/api/themes", json={"name": "Mine", "css": GOOD_CSS}, headers=a)
        # b can't see a's theme list or fetch its css
        self.assertEqual(self.client.get("/api/themes/mine", headers=b).json(), [])
        self.assertEqual(self.client.get("/api/themes/mine/mine.css", headers=b).status_code, 404)


class TestDeckThemeCss(_AppTestCase):
    """The public per-deck theme.css endpoint (reader-visibility SSR fix)."""

    DECK_MD = (
        "---\n"
        "title: Styled\n"
        "author: A\n"
        "topic: t\n"
        "keywords: [x]\n"
        "theme: my-theme\n"
        "---\n"
        "---\n"
        "type: title\n"
        "---\n"
        "# Hi\n"
    )

    def test_serves_a_decks_custom_theme_to_any_reader(self):
        auth = self.make_user("a@e.com")
        self.client.post(
            "/api/themes", json={"name": "My Theme", "css": GOOD_CSS}, headers=auth
        )
        r = self.client.post(
            "/api/decks/mine", json={"markdown": self.DECK_MD}, headers=auth
        )
        self.assertEqual(r.status_code, 201)
        # No auth header — a public reader still gets the theme CSS.
        r = self.client.get("/api/decks/t/styled/theme.css")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/css", r.headers["content-type"])
        self.assertIn("--vd-bg", r.text)

    def test_builtin_theme_deck_has_no_custom_css(self):
        auth = self.make_user("a@e.com")
        md = self.DECK_MD.replace("theme: my-theme", "theme: default")
        self.client.post("/api/decks/mine", json={"markdown": md}, headers=auth)
        self.assertEqual(self.client.get("/api/decks/t/styled/theme.css").status_code, 404)


class TestDeckVisibility(_AppTestCase):
    """Per-deck visibility: public (listed) / unlisted (link-only) / private."""

    def _md(self, topic, title, visibility=None):
        vis = f"visibility: {visibility}\n" if visibility else ""
        return (
            f"---\ntitle: {title}\nauthor: A\ntopic: {topic}\n"
            f"keywords: [x]\ntheme: default\n{vis}---\n"
            "---\ntype: title\n---\n# Hi\n"
        )

    def test_public_listed_unlisted_and_private_excluded(self):
        auth = self.make_user("a@e.com")
        for t, title, vis in [
            ("pub", "Pub", "public"),
            ("unl", "Unl", "unlisted"),
            ("priv", "Priv", "private"),
        ]:
            r = self.client.post("/api/decks/mine", json={"markdown": self._md(t, title, vis)}, headers=auth)
            self.assertEqual(r.status_code, 201, r.text)
        listed = {d["slug"] for d in self.client.get("/api/decks/public").json()}
        self.assertEqual(listed, {"pub"})  # only the public deck is listed

    def test_unlisted_is_readable_by_url_but_private_404s(self):
        auth = self.make_user("a@e.com")
        self.client.post("/api/decks/mine", json={"markdown": self._md("unl", "Unl", "unlisted")}, headers=auth)
        self.client.post("/api/decks/mine", json={"markdown": self._md("priv", "Priv", "private")}, headers=auth)
        self.assertEqual(self.client.get("/api/decks/unl/unl").status_code, 200)
        self.assertEqual(self.client.get("/api/decks/priv/priv").status_code, 404)

    def test_reader_reports_visibility(self):
        auth = self.make_user("a@e.com")
        self.client.post("/api/decks/mine", json={"markdown": self._md("unl", "Unl", "unlisted")}, headers=auth)
        self.assertEqual(self.client.get("/api/decks/unl/unl").json()["visibility"], "unlisted")

    def test_invalid_visibility_rejected_on_save(self):
        auth = self.make_user("a@e.com")
        r = self.client.post("/api/decks/mine", json={"markdown": self._md("x", "X", "secret")}, headers=auth)
        self.assertEqual(r.status_code, 400)

    def test_default_visibility_is_public(self):
        auth = self.make_user("a@e.com")
        self.client.post("/api/decks/mine", json={"markdown": self._md("d", "D")}, headers=auth)
        self.assertEqual(self.client.get("/api/decks/d/d").json()["visibility"], "public")


if __name__ == "__main__":
    unittest.main()
