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

SEPARATORS & WHITESPACE
-----------------------
The spec example places a blank line (and thus an extra `---`) between the
deck frontmatter and the first card. Naive fence-splitting therefore yields
whitespace-only segments at the very start of the card stream. The parser
discards LEADING whitespace-only card-stream segments so both styles work:

    ---            ---
    deck fm        deck fm
    ---            ---
    type: title    type: title     <- "tight" style, no gap, also valid
    ---            ---
    ...

Interior whitespace segments are NOT discarded — they hold their position so
the [frontmatter, body] pairing stays aligned even for an empty card body.

LIMITATION
----------
A card body cannot contain a line that is exactly `---`, because that is the
card separator. Authors who want a markdown horizontal rule inside a card
should use `***` or `___` instead. A trailing bare `---` at end of file is a
dangling separator and makes the deck malformed.

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

import yaml

# Card types recognised in v1 (see SPEC.md "Card Types").
V1_CARD_TYPES = frozenset({"title", "concept", "summary", "graphic", "quote"})

# Deck frontmatter fields that must be present.
REQUIRED_DECK_FIELDS = ("title", "author", "topic", "keywords", "theme")

# Optional `visibility` frontmatter field; absent means public.
VALID_VISIBILITIES = frozenset({"public", "unlisted", "private"})

# Optional `transition` frontmatter field (card-change animation in the
# reader); absent or unknown means "slide". `reveal: bullets` is the other
# optional reader field — bullet lists reveal one item per advance.
VALID_TRANSITIONS = frozenset({"slide", "fade", "none"})


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


def _split_on_fences(text: str) -> list[str]:
    """Split text into segments on lines that are exactly `---`.

    A file beginning with `---` yields an empty leading segment (the text
    before the first fence). Returns raw, unstripped segment text.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    segments: list[str] = []
    current: list[str] = []
    for line in text.split("\n"):
        if line.strip() == "---":
            segments.append("\n".join(current))
            current = []
        else:
            current.append(line)
    segments.append("\n".join(current))
    return segments


def _load_yaml_block(raw: str, *, what: str) -> dict:
    """Parse a YAML frontmatter block, requiring a mapping."""
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise DeckParseError(f"invalid YAML in {what}: {exc}") from exc
    if data is None:
        raise DeckParseError(f"empty {what}")
    if not isinstance(data, dict):
        raise DeckParseError(f"{what} must be a mapping, got {type(data).__name__}")
    return data


def parse_deck(text: str) -> ParsedDeck:
    """Parse a deck markdown file into validated metadata + cards.

    Follows the block model documented at the top of this module. Raises
    DeckParseError with a descriptive message on any violation, so the
    upload endpoint can reject malformed decks with a clear reason.
    """
    segments = _split_on_fences(text)

    # The file must open with frontmatter, i.e. the first fence is at the
    # very top and the leading segment is whitespace-only.
    if not segments or segments[0].strip() != "":
        raise DeckParseError(
            "deck must begin with YAML frontmatter delimited by '---'"
        )
    segments = segments[1:]
    if not segments:
        raise DeckParseError("deck has no frontmatter block")

    # Block 0: deck-level frontmatter.
    meta = _load_yaml_block(segments[0], what="deck frontmatter")
    _validate_deck_meta(meta)

    # Remaining blocks are the card stream. Discard LEADING whitespace-only
    # segments (the gap/separator after the deck frontmatter); keep interior
    # ones so [frontmatter, body] pairs stay aligned.
    card_segments = segments[1:]
    while card_segments and card_segments[0].strip() == "":
        card_segments = card_segments[1:]

    if not card_segments:
        raise DeckParseError("deck contains no cards")
    if len(card_segments) % 2 != 0:
        raise DeckParseError(
            "malformed deck: card blocks must form [frontmatter, body] pairs, "
            f"but found an odd number ({len(card_segments)}) of trailing blocks "
            "— check for a missing body or a stray '---'"
        )

    cards: list[ParsedCard] = []
    for i in range(0, len(card_segments), 2):
        position = i // 2 + 1
        card_meta = _load_yaml_block(
            card_segments[i], what=f"card {position} frontmatter"
        )
        card_type = card_meta.get("type")
        if card_type is None:
            raise DeckParseError(f"card {position} is missing a 'type' field")
        if card_type not in V1_CARD_TYPES:
            raise DeckParseError(
                f"card {position} has unknown type {card_type!r}; "
                f"valid types: {', '.join(sorted(V1_CARD_TYPES))}"
            )
        body = card_segments[i + 1].strip()
        extra_meta = {k: v for k, v in card_meta.items() if k != "type"}
        cards.append(ParsedCard(type=card_type, meta=extra_meta, body=body))

    return ParsedDeck(meta=meta, cards=cards)


def _validate_deck_meta(meta: dict) -> None:
    """Ensure required deck frontmatter fields are present and well-typed."""
    missing = [f for f in REQUIRED_DECK_FIELDS if f not in meta]
    if missing:
        raise DeckParseError(
            f"deck frontmatter missing required field(s): {', '.join(missing)}"
        )
    if not isinstance(meta["keywords"], list):
        raise DeckParseError("deck frontmatter 'keywords' must be a list")
    if "visibility" in meta and str(meta["visibility"]) not in VALID_VISIBILITIES:
        raise DeckParseError(
            f"deck frontmatter 'visibility' must be one of: "
            f"{', '.join(sorted(VALID_VISIBILITIES))}"
        )
