"""Algorithmic content moderation for user-submitted deck text.

Deterministic, no external API. Two concerns, mirroring HANDOFF.md:

1. SEO / link abuse — external links extracted from the deck description and
   card bodies, then judged on count, per-domain repetition, density, URL
   shorteners, and a domain blocklist.
2. Hurtful / harmful language — word-boundary matching against two tiered
   wordlists under `moderation_data/`.

Enforcement is hybrid and leans cautious:
  block — egregious (severe slur, blocklisted domain, blatant link farm).
          The deck is rejected at submit time and never stored.
  flag  — suspicious. The deck is stored but withheld from public view
          until an admin approves it from the review queue.
  allow — everything else.

Tuning lives in two places, neither of which needs a code change to the
engine logic: the threshold constants below (documented inline, in the
spirit of `_MAX_DECK_BYTES` in services/decks.py) and the plain-text data
files in `moderation_data/` (loaded once at import; restart to pick up
edits).

This module is the single seam for the future AI layer:
TODO(v2+): add a Claude classifier as a second pass inside moderate_deck()
(needs ANTHROPIC_API_KEY in .env; run async because of per-deck latency —
see HANDOFF.md). The heuristics here stay as the cheap first gate.
"""

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import re

from config import settings
from services.parser import ParsedDeck

# ── Tunable thresholds ─────────────────────────────────────────────────────

# Total external links in one deck. Real decks cite a handful of sources;
# dozens of links is link-farm territory.
_FLAG_TOTAL_LINKS = 8
_BLOCK_TOTAL_LINKS = 20

# Repeats of a single external domain. Linking the same site this often is
# the classic SEO pattern.
_FLAG_DOMAIN_REPEATS = 4
_BLOCK_DOMAIN_REPEATS = 10

# Links-per-word density across description + card bodies. Only applied once
# a deck has _DENSITY_MIN_LINKS links, so a short deck citing one source
# isn't flagged for being short.
_FLAG_LINK_DENSITY = 0.08  # ~1 link per 12 words
_DENSITY_MIN_LINKS = 4

# URL shorteners hide the destination from both the heuristics and readers.
# One is suspicious (flag); several is deliberate obfuscation (block).
_BLOCK_SHORTENER_LINKS = 3
_SHORTENER_DOMAINS = frozenset(
    {
        "bit.ly",
        "tinyurl.com",
        "t.co",
        "goo.gl",
        "is.gd",
        "ow.ly",
        "buff.ly",
        "cutt.ly",
        "rb.gy",
        "shorturl.at",
        "tiny.cc",
        "v.gd",
        "rebrand.ly",
        "s.id",
    }
)


# ── Wordlist / blocklist loading (once, at import) ─────────────────────────

_DATA_DIR = Path(__file__).resolve().parent / "moderation_data"


def _load_list(filename: str) -> frozenset[str]:
    """Lowercased entries from a data file; blank lines and # comments skipped."""
    entries: set[str] = set()
    for line in (_DATA_DIR / filename).read_text(encoding="utf-8").splitlines():
        line = line.strip().lower()
        if line and not line.startswith("#"):
            entries.add(line)
    return frozenset(entries)


def _word_pattern(words: frozenset[str]) -> re.Pattern | None:
    """One regex matching any listed word/phrase at word boundaries."""
    if not words:
        return None
    alternatives = "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
    return re.compile(rf"\b(?:{alternatives})\b", re.IGNORECASE)

_BLOCK_WORDS_RE = _word_pattern(_load_list("words_block.txt"))
_FLAG_WORDS_RE = _word_pattern(_load_list("words_flag.txt"))
_DOMAIN_BLOCKLIST = _load_list("domain_blocklist.txt")


# ── Verdict ────────────────────────────────────────────────────────────────

# Ordered by severity; moderate_deck reports the worst finding's action.
_SEVERITY = {"allow": 0, "flag": 1, "block": 2}


@dataclass
class ModerationVerdict:
    action: str  # "allow" | "flag" | "block"
    reasons: list[str] = field(default_factory=list)


# ── Link extraction ────────────────────────────────────────────────────────

# Any absolute http(s) URL — catches markdown links, <a href>, and bare URLs
# alike, which is all that matters for counting.
_URL = re.compile(r"https?://[^\s)\"'<>\]]+", re.IGNORECASE)


def _base_host() -> str:
    """This instance's own host; links to ourselves are not 'external'."""
    host = (urlparse(settings.BASE_URL).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _external_domains(text: str) -> list[str]:
    """Registrable-ish hostnames of every external link, one per occurrence."""
    own = _base_host()
    domains: list[str] = []
    for url in _URL.findall(text):
        host = (urlparse(url).hostname or "").lower()
        host = host[4:] if host.startswith("www.") else host
        if host and host != own:
            domains.append(host)
    return domains


def _is_blocklisted(host: str) -> bool:
    """True if host or any parent domain of it is on the blocklist."""
    parts = host.split(".")
    return any(".".join(parts[i:]) in _DOMAIN_BLOCKLIST for i in range(len(parts) - 1))


# ── The verdict ────────────────────────────────────────────────────────────


def moderate_deck(parsed: ParsedDeck) -> ModerationVerdict:
    """Judge a parsed deck's text. Pure and deterministic.

    Word checks scan everything reader-visible (frontmatter strings + card
    bodies); link checks scan where links can actually render (description +
    card bodies).
    """
    meta = parsed.meta
    bodies = "\n\n".join(card.body for card in parsed.cards)
    description = str(meta.get("description") or "")
    link_text = f"{description}\n{bodies}"
    keywords = " ".join(str(k) for k in meta.get("keywords") or [])
    word_text = " ".join(
        [
            str(meta.get("title") or ""),
            str(meta.get("author") or ""),
            description,
            keywords,
            bodies,
        ]
    )

    findings: list[tuple[str, str]] = []  # (action, reason)

    # Hurtful / harmful language
    if _BLOCK_WORDS_RE and (m := _BLOCK_WORDS_RE.search(word_text)):
        findings.append(("block", f'contains disallowed language ("{m.group(0)}")'))
    if _FLAG_WORDS_RE and (m := _FLAG_WORDS_RE.search(word_text)):
        findings.append(("flag", f'contains language needing review ("{m.group(0)}")'))

    # SEO / link abuse
    domains = _external_domains(link_text)
    if domains:
        for host in dict.fromkeys(domains):  # unique, original order
            if _is_blocklisted(host):
                findings.append(("block", f"links to a blocklisted domain ({host})"))

        total = len(domains)
        if total >= _BLOCK_TOTAL_LINKS:
            findings.append(("block", f"{total} external links (limit {_BLOCK_TOTAL_LINKS})"))
        elif total >= _FLAG_TOTAL_LINKS:
            findings.append(("flag", f"{total} external links (review at {_FLAG_TOTAL_LINKS})"))

        repeats = max(domains.count(h) for h in set(domains))
        worst = max(set(domains), key=domains.count)
        if repeats >= _BLOCK_DOMAIN_REPEATS:
            findings.append(("block", f"one domain linked {repeats} times ({worst})"))
        elif repeats >= _FLAG_DOMAIN_REPEATS:
            findings.append(("flag", f"one domain linked {repeats} times ({worst})"))

        shorteners = sum(1 for h in domains if h in _SHORTENER_DOMAINS)
        if shorteners >= _BLOCK_SHORTENER_LINKS:
            findings.append(("block", f"{shorteners} links via URL shorteners"))
        elif shorteners:
            findings.append(("flag", f"{shorteners} link(s) via URL shorteners"))

        words = len(re.findall(r"\w+", link_text))
        if total >= _DENSITY_MIN_LINKS and total / max(words, 1) >= _FLAG_LINK_DENSITY:
            findings.append(("flag", f"high link density ({total} links in {words} words)"))

    # TODO(v2+): AI second pass goes here — a Claude classifier on word_text,
    # ANDed into the verdict (it can escalate allow→flag/block, never relax).

    if not findings:
        return ModerationVerdict(action="allow")
    action = max((f[0] for f in findings), key=_SEVERITY.__getitem__)
    return ModerationVerdict(action=action, reasons=[f[1] for f in findings])
