"""Vibedeck deck parser.

=============================================================================
PARSER SPECIFICATION  (read this before changing the implementation)
=============================================================================

A Vibedeck deck is a single UTF-8 markdown file. It encodes two things:
deck-level metadata, and an ordered sequence of typed cards. Both are
delimited by lines containing exactly `---`. Because `---` serves double
duty (YAML frontmatter fence AND card separator), parsing follows one
precise rule.

THE BLOCK MODEL
---------------
Split the file on lines that are exactly `---` (a horizontal-rule fence).
This yields an ordered list of text "blocks". The blocks are interpreted
positionally:

    Block 0           -> DECK frontmatter (YAML)
    Block 1, 2        -> Card 1: [frontmatter (YAML), body (markdown)]
    Block 3, 4        -> Card 2: [frontmatter, body]
    Block 5, 6        -> Card 3: ...
    ...               -> and so on, in [frontmatter, body] pairs

So after the first block, blocks pair up: odd-indexed blocks are card
frontmatter, even-indexed blocks are the card body that follows.

Concretely, given a file like:

    ---
    title: ...            <- Block 0  (deck frontmatter)
    ---
    type: title           <- Block 1  (card 1 frontmatter)
    ---
    # The 12 Houses       <- Block 2  (card 1 body)
    ---
    type: concept         <- Block 3  (card 2 frontmatter)
    ---
    ## What is a House?   <- Block 4  (card 2 body)

Note the leading `---` before Block 0 produces an empty Block at index 0
when splitting naively; the implementation must discard a leading empty
block so that the deck frontmatter lands at logical index 0.

VALIDATION RULES
----------------
1. Deck frontmatter (Block 0) MUST contain the required fields:
   title, author, topic, keywords, theme. `description` is optional.
2. After the deck frontmatter, the remaining blocks MUST be EVEN in count
   (they pair into cards). An ODD number of trailing blocks => the deck is
   MALFORMED and upload is rejected with a clear error naming the dangling
   block.
3. Each card frontmatter MUST declare a `type`, and that type must be one
   of the known v1 card types: title, concept, summary, graphic, quote.
   An unknown type => malformed.
4. A deck must contain at least one card.

OUTPUT SHAPE
------------
parse_deck(text) -> ParsedDeck:
    meta:  dict   (validated deck frontmatter)
    cards: list[ParsedCard], each:
        type: str             (one of the v1 card types)
        meta: dict            (the card's frontmatter, minus `type`)
        body: str             (raw markdown, rendered downstream)

The card BODY is returned as raw markdown. Markdown-to-HTML rendering is a
separate concern handled at the render layer, not here.

WHY THIS DESIGN
---------------
The file is the source of truth (see models/deck.py). The parser is called
in two places: (a) at upload, to validate and to extract metadata for the
DB index and to count cards; (b) on read, to turn the canonical file into
cards for the reader. The DB never stores card bodies — they always come
from re-parsing here.
=============================================================================
"""

from dataclasses import dataclass, field

# Card types recognised in v1 (see SPEC.md "Card Types").
V1_CARD_TYPES = frozenset({"title", "concept", "summary", "graphic", "quote"})

# Deck frontmatter fields that must be present.
REQUIRED_DECK_FIELDS = ("title", "author", "topic", "keywords", "theme")


@dataclass
class ParsedCard:
    type: str
    meta: dict
    body: str


@dataclass
class ParsedDeck:
    meta: dict
    cards: list[ParsedCard] = field(default_factory=list)


class DeckParseError(ValueError):
    """Raised when a deck file violates the parser specification above."""


def parse_deck(text: str) -> ParsedDeck:
    """Parse a deck markdown file into validated metadata + cards.

    STUB: not yet implemented. Implementation will follow the block model
    documented above. Kept as a stub in this scaffold so the spec lands
    first as the contributor-facing anchor.
    """
    raise NotImplementedError("parse_deck is scaffolded; implementation pending")
