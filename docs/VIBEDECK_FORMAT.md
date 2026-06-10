# The Vibedeck File Format — Authoring Reference

A complete reference for writing Vibedeck deck files. It is written to be
self-contained: paste it into an AI assistant's context as the
specification for generating decks, or read it yourself.

A deck is **one UTF-8 markdown file** (max **256 KB**) containing
deck-level metadata followed by an ordered sequence of typed cards. The
mental model is the index card: **one focused idea per card**, sequenced
to build understanding progressively.

---

## 1. File structure — the block model

The file is split on lines containing **exactly `---`** (three dashes,
nothing else on the line). The resulting blocks are interpreted
positionally:

```
---
<deck frontmatter>      Block 0 — YAML describing the whole deck
---
<card 1 frontmatter>    Block 1 — YAML, at minimum `type: ...`
---
<card 1 body>           Block 2 — markdown
---
<card 2 frontmatter>    Block 3
---
<card 2 body>           Block 4
---
...and so on, always in [frontmatter, body] pairs
```

Skeleton of a minimal valid deck:

```markdown
---
title: My Deck
author: Jane Doe
topic: demo
keywords: [example]
theme: default
---

---
type: title
---

# My Deck
### A one-line subtitle

---
type: concept
---

## One idea

Explained cleanly, in a few short paragraphs.
```

**Structural rules (violations reject the file with an error):**

- The file must **begin** with `---` followed by the deck frontmatter.
- After the deck frontmatter, blocks must pair up evenly as
  `[card frontmatter, card body]`. An odd number of blocks (e.g. a missing
  body, or a stray trailing `---` at end of file) is malformed.
- A deck must contain **at least one card**.
- A blank line between the deck frontmatter and the first card is allowed
  but not required.

**The `---` limitation:** because a bare `---` line *is* the separator, a
card body can never contain one. For a horizontal rule inside a card, use
`***` or `___` instead.

---

## 2. Deck frontmatter

YAML mapping in Block 0.

### Required fields

| Field | Type | Meaning |
|---|---|---|
| `title` | string | The deck's display name |
| `author` | string | Who made it |
| `topic` | string | Groups the deck in the library; becomes a URL slug |
| `keywords` | **list** of strings | Finer-grained tags within a topic, e.g. `[intro, reference]` |
| `theme` | string | Visual style: a built-in (`default`, `operazione-stile`, `fascicolo`), or the author's custom theme name; unknown names fall back to `default` |

`keywords` must be a YAML list (`[a, b]` or dash form) — a plain string is
rejected.

### Optional fields

| Field | Values | Default | Meaning |
|---|---|---|---|
| `description` | string | — | One-line summary shown in index listings |
| `visibility` | `public` \| `unlisted` \| `private` | `public` | `public` is listed in the library; `unlisted` is readable by anyone with the link; `private` renders only for the signed-in owner |
| `transition` | `slide` \| `fade` \| `none` | `slide` | Card-change animation in the reader |
| `reveal` | `bullets` | off | Bullet-list items reveal **one per advance**: each press of "next" surfaces the next bullet on the current card before moving to the next card |

Any other value for `visibility` is rejected; unknown `transition` values
fall back to `slide`.

---

## 3. Card frontmatter

Each card's frontmatter block needs exactly one field:

```yaml
type: concept
```

`type` must be one of: **`title`, `concept`, `summary`, `graphic`,
`quote`**. A missing or unknown type rejects the deck.

---

## 4. The five card types

How each type renders, and the markdown conventions it expects.

### `title` — the opening card

Large, centred display treatment. The `# h1` gets a gradient display face;
an `### h3` directly after it is styled as the subtitle. Use exactly once,
as the first card.

```markdown
---
type: title
---

# The 12 Houses
### A map of the sky, a map of a life
```

### `concept` — the workhorse

One idea, explained cleanly. Open with an `## h2` stating the idea, then
2–5 short paragraphs (or a short list) developing it. If the card needs a
scrollbar on a phone, it's two cards.

```markdown
---
type: concept
---

## The constraint is the feature

An index card can't hold a lecture. That's the point.

Limiting each card to one idea forces sequencing — and sequencing is
what turns information into understanding.
```

### `summary` — the consolidation card

Big-picture bullets, generously line-spaced. Use after a run of 3–6
concept cards to consolidate before moving on, and usually again at the
end. Keep bullets parallel in structure and under ~12 words.

```markdown
---
type: summary
---

## So far

- One idea per card — focused, constrained
- Cards sequence into an argument, not a pile of facts
- Summaries consolidate before the next run begins
```

### `graphic` — image with caption

A full-width image, centred, with rounded corners. The *italic paragraph*
after the image renders as the caption (muted, smaller, beneath it).

```markdown
---
type: graphic
---

![A hand-drawn zodiac wheel](/images/zodiac-wheel.png)

*The wheel: twelve houses, counted anticlockwise from the eastern horizon.*
```

Image URLs may be site-relative (`/images/...`), external `https:`, or
inline `data:image/...`. Alt text is kept — write it.

### `quote` — the pull quote

A `> blockquote` styled large and italic with an accent rule. The line
after the blockquote is the attribution. Use sparingly — one lands, five
don't.

```markdown
---
type: quote
---

> We are all in the gutter, but some of us are looking at the stars.

— Oscar Wilde, *Lady Windermere's Fan*
```

---

## 5. Markdown support in card bodies

GitHub-flavored markdown, rendered then sanitised. What survives:

- **Kept:** headings, paragraphs, bold/italic/strikethrough, `inline code`
  and fenced code blocks, blockquotes, ordered/unordered lists, tables,
  links, images, `***` horizontal rules.
- **Stripped (silently):** raw HTML beyond the basics, scripts, iframes,
  event handlers, inline `style` attributes.
- **Links** may use `https:`, `mailto:`, `tel:`, site-relative `/...`, or
  `#` anchors; `javascript:` is stripped. Links open in the same tab.
- Single newlines do **not** become `<br>`; leave a blank line between
  paragraphs.

---

## 6. Hard rules — checklist for generating a valid deck

1. File starts with `---` and a YAML deck frontmatter block.
2. Frontmatter has `title`, `author`, `topic`, `keywords` (a list), `theme`.
3. Every card is a `---`-fenced YAML block with a valid `type`, followed by
   a `---`-fenced markdown body — always in pairs.
4. No card body contains a line that is exactly `---` (use `***`).
5. No trailing `---` after the last card body.
6. At least one card; whole file under 256 KB.
7. If present: `visibility` ∈ public/unlisted/private; `transition` ∈
   slide/fade/none; `reveal: bullets`.

---

## 7. Writing a *good* deck

Validity is the floor. These conventions are what make decks worth reading:

- **One idea per card.** If a concept card explains two things, split it.
  A reader should absorb a card in 15–30 seconds.
- **Sequence deliberately.** Cards are read in order, one at a time —
  build each card on the previous one. The deck is an argument, not a
  list.
- **Shape:** open with one `title` card; develop in runs of 3–6 `concept`
  cards; consolidate each run with a `summary`; punctuate with a `quote`
  or `graphic` where it earns its place; close with a final `summary` (and
  optionally a `quote` as the button on the ending).
- **Length:** 8–20 cards is the sweet spot. Under 6 rarely needs a deck;
  over 25 usually wants to be two decks.
- **Write for a phone.** Short paragraphs, no walls of text, headings that
  work at a glance. Desktop is the enhancement, not the target.
- **With `reveal: bullets`,** order list items so each one lands alone —
  the reader sees them one advance at a time.
- **Keywords:** 2–5 lowercase tags that group related decks within the
  topic.

---

## 8. A complete worked example

```markdown
---
title: Reading a Coffee Cupping Sheet
author: Sam Rivera
topic: coffee
keywords: [cupping, tasting, reference]
theme: default
description: What the numbers on a cupping form actually measure.
transition: fade
reveal: bullets
---

---
type: title
---

# Reading a Cupping Sheet
### Ten scores, one verdict

---
type: concept
---

## Why cupping exists

Every coffee gets graded the same way: same grind, same water, same
steep. The cupping sheet is how tasters make a subjective thing
comparable.

Ten categories, each scored 6–10. Above 80 total is "specialty".

---
type: concept
---

## The first impression scores

**Fragrance/Aroma** is the smell — dry grounds first, then wet.

**Flavor** is the headline number: the combined impression once you
actually slurp.

**Aftertaste** measures what stays. A score that drops here usually
means a finish that turns bitter or just vanishes.

---
type: summary
---

## The sheet, in thirds

- First impressions — fragrance, flavor, aftertaste
- Structure — acidity, body, balance
- Judgment calls — sweetness, uniformity, clean cup, overall

---
type: quote
---

> You're not scoring what you like. You're scoring what's in the cup.

— Every cupping instructor, eventually

---
type: graphic
---

![A scored cupping sheet with pencil annotations](/images/cupping-sheet.png)

*A real sheet: note the flavor and balance scores carrying the total.*

---
type: summary
---

## Take it with you

- Ten categories, 6–10 points each; 80+ is specialty grade
- Flavor and balance move totals most — read them first
- Aftertaste separates good coffees from memorable ones
```
