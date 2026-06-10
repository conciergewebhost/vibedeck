---
title: Anatomy of a VibeDeck File
author: Rob Wall
topic: vibedeck
keywords: [authoring, format, markdown, reference]
theme: operazione-stile
description: A field guide to the parts of a VibeDeck markdown file — frontmatter, cards, the five card types, and the optional behavior switches.
---
---
type: title
---
# Anatomy of a VibeDeck File
### How one plain markdown file becomes a deck
---
type: concept
---
## Two layers, one file

A VibeDeck file has just two layers: the **deck frontmatter** at the very top, then a series of **cards**.

It's all plain markdown — no proprietary format, and no special editor required.
---
type: concept
---
## The fence

Blocks are separated by a line containing exactly three dashes: `---`.

The first fenced block is the **deck frontmatter**. After that, blocks come in pairs — a card's frontmatter, then that card's body.

Because the three-dash line *is* the separator, a card body can't contain one. Want a horizontal rule inside a card? Use `***` instead.
---
type: concept
---
## Deck frontmatter

The opening block is YAML that describes the whole deck. Five fields are required:

- **title** — the deck's name
- **author** — who made it
- **topic** — groups the deck in the library
- **keywords** — a list, e.g. `[markdown, reference]`
- **theme** — the visual style (you're reading `operazione-stile`)

Plus the optional **description** — a one-line summary for index listings.
---
type: concept
---
## Optional: behavior switches

Three more optional frontmatter fields tune how the deck behaves:

- **visibility** — `public` (listed), `unlisted` (link-only), or `private` (only you)
- **transition** — the card-change animation: `slide`, `fade`, or `none`
- **reveal: bullets** — bullet lists reveal one item per advance, so each point lands before the next appears
---
type: concept
---
## A card

Each card is a tiny frontmatter block followed by a markdown body. The card frontmatter only needs one field:

```
type: concept
```

Everything after it, until the next fence, is the card's body — ordinary markdown: headings, lists, **emphasis**, links, and images.
---
type: summary
---
## The five card types

- **title** — the opening card; sets the tone before the content begins
- **concept** — the workhorse: one idea, explained clearly
- **summary** — bullet points for just the big picture
- **graphic** — a full image or chart with a caption
- **quote** — a pull quote, styled to land
---
type: quote
---
> One idea per card. Focused enough to absorb, sequenced to build understanding without overwhelm.

— The VibeDeck constraint
---
type: summary
---
## Putting it together

- Open with the deck frontmatter
- Lead with a `title` card
- Build the body from `concept` and `summary` cards
- Punctuate with a `quote` or a `graphic`
- Set `visibility`, `transition`, or `reveal` if the defaults aren't right
- Save it as a `.md` file and upload — or skip the file and use the in-browser builder
