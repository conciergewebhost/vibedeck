"""Tests for the deck parser.

Written with stdlib unittest so they run without extra dependencies
(`python -m unittest` from the backend/ directory). pytest can also
collect them unchanged.
"""

import sys
import unittest
from pathlib import Path
from textwrap import dedent

# Make the backend package importable when run from anywhere.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from services.parser import (  # noqa: E402
    DeckParseError,
    ParsedDeck,
    parse_deck,
)

REPO_ROOT = BACKEND_DIR.parent
FIXTURE = REPO_ROOT / "decks" / "the-12-houses.md"


class TestValidDeck(unittest.TestCase):
    def test_parses_the_12_houses_fixture(self):
        deck = parse_deck(FIXTURE.read_text(encoding="utf-8"))
        self.assertIsInstance(deck, ParsedDeck)
        # Deck frontmatter
        self.assertEqual(deck.meta["title"], "The 12 Houses")
        self.assertEqual(deck.meta["author"], "Rob Wall")
        self.assertEqual(deck.meta["topic"], "z13")
        self.assertEqual(deck.meta["theme"], "z13-dark")
        self.assertIn("beginner", deck.meta["keywords"])
        # Cards: title, concept, summary, graphic, quote — in order
        self.assertEqual(
            [c.type for c in deck.cards],
            ["title", "concept", "summary", "graphic", "quote"],
        )
        # Bodies are raw markdown, stripped; `type` is not duplicated in meta
        self.assertTrue(deck.cards[0].body.startswith("# The 12 Houses"))
        self.assertNotIn("type", deck.cards[0].meta)

    def test_tight_style_without_separator_gap(self):
        """Deck fm immediately followed by the first card (no blank line)."""
        text = dedent(
            """\
            ---
            title: Tight
            author: A
            topic: t
            keywords: [x]
            theme: default
            ---
            type: title
            ---
            # Hello
            """
        )
        deck = parse_deck(text)
        self.assertEqual(len(deck.cards), 1)
        self.assertEqual(deck.cards[0].type, "title")
        self.assertEqual(deck.cards[0].body, "# Hello")


def _deck(cards_block: str, *, fm: str | None = None) -> str:
    front = fm or dedent(
        """\
        title: T
        author: A
        topic: t
        keywords: [x]
        theme: default"""
    )
    return f"---\n{front}\n---\n\n{cards_block}"


class TestMalformedDecks(unittest.TestCase):
    def test_missing_required_field(self):
        text = "---\ntitle: T\nauthor: A\ntopic: t\ntheme: default\n---\n" \
               "---\ntype: concept\n---\nbody\n"  # no keywords
        with self.assertRaises(DeckParseError) as ctx:
            parse_deck(text)
        self.assertIn("keywords", str(ctx.exception))

    def test_keywords_not_a_list(self):
        fm = "title: T\nauthor: A\ntopic: t\nkeywords: nope\ntheme: default"
        with self.assertRaises(DeckParseError):
            parse_deck(_deck("---\ntype: concept\n---\nbody\n", fm=fm))

    def test_odd_trailing_blocks(self):
        # card frontmatter with no body block following it
        text = _deck("---\ntype: concept\n---\nbody\n---\ntype: quote\n")
        with self.assertRaises(DeckParseError) as ctx:
            parse_deck(text)
        self.assertIn("odd", str(ctx.exception))

    def test_unknown_card_type(self):
        text = _deck("---\ntype: hologram\n---\nbody\n")
        with self.assertRaises(DeckParseError) as ctx:
            parse_deck(text)
        self.assertIn("unknown type", str(ctx.exception))

    def test_card_missing_type(self):
        text = _deck("---\nfoo: bar\n---\nbody\n")
        with self.assertRaises(DeckParseError) as ctx:
            parse_deck(text)
        self.assertIn("type", str(ctx.exception))

    def test_no_cards(self):
        text = "---\ntitle: T\nauthor: A\ntopic: t\nkeywords: [x]\ntheme: default\n---\n"
        with self.assertRaises(DeckParseError) as ctx:
            parse_deck(text)
        self.assertIn("no cards", str(ctx.exception))

    def test_must_begin_with_frontmatter(self):
        text = "# Just markdown\n\nno frontmatter here\n"
        with self.assertRaises(DeckParseError) as ctx:
            parse_deck(text)
        self.assertIn("frontmatter", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
