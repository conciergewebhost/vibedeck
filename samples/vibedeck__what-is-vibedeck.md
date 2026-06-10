---
title: What is Vibedeck?
author: Rob Wall
topic: vibedeck
keywords: [intro, about, getting-started]
theme: operazione-stile
description: A quick introduction to what Vibedeck is, why it exists, and how it works.
---

---
type: title
---

# Vibedeck
### Digital index cards. Chunked knowledge, beautifully delivered.

---
type: concept
---

## The Problem with Presentations

Most presentation tools are built for a stage.

Big screen. Captive audience. Clicker in hand.

But what about content people consume on their own — on a phone, at their own pace, whenever it fits into their day?

Slideshows weren't designed for that. Vibedeck was.

---
type: concept
---

## The Index Card Idea

Remember index cards?

One idea per card. Focused. Constrained. Sequenced to build understanding without overwhelming.

Students have been using them for centuries because they work — not despite the constraint, but because of it.

Vibedeck brings that model to the web.

---
type: concept
---

## What Vibedeck Is

A platform for creating and browsing card decks authored in plain markdown.

You write a markdown file. Vibedeck turns it into a beautiful, paginated card experience that works on any device — phone, tablet, desktop, or projected screen.

No special software. No complex tooling. Just markdown and a clear idea.

---
type: concept
---

## What Vibedeck Is Not

Vibedeck is not a presentation tool.

It is a **reading and learning experience** that happens to work beautifully in a presentation context.

The distinction matters. The design decisions — mobile-first, paginated, card-constrained — all follow from that.

---
type: summary
---

## So Far

- Most presentation tools aren't built for solo, mobile consumption
- The index card is a proven learning format — one idea, focused, sequenced
- Vibedeck brings that model to the web as markdown-authored card decks
- It's a reading experience first, presentation tool second

---
type: concept
---

## Card Types

Vibedeck supports five card types in v1:

**Title** — the opening card, large display treatment

**Concept** — one idea, explained cleanly. The constraint is the feature.

**Summary** — big picture consolidation, bullet points, palette cleanser between concept runs

**Graphic** — full image or chart with a caption

**Quote** — a pull quote, styled distinctively

---
type: concept
---

## Authoring a Deck

Every deck is a single markdown file with YAML frontmatter.

Cards are separated by `---`. Each card declares its type in its own frontmatter block.

That's the entire format. If you can write markdown, you can author a Vibedeck deck.

---
type: concept
---

## The Format

A deck frontmatter block at the top defines the title, author, topic, keywords, and theme.

Each card follows — separated by `---` — with its own type declaration and content.

Title card. Concept cards. Summary cards. Quote cards. Graphic cards. That's the whole vocabulary.

---
type: concept
---

## How Decks Are Organized

Decks are grouped by **topic** — a slug that becomes part of the URL.

`vibedeck.online/z13` — all astrology decks

`vibedeck.online/tok` — all Theory of Knowledge decks

Each deck also carries **keywords** for finer-grained thematic grouping within a topic.

---
type: concept
---

## The Open Source Project

Vibedeck is open source under the MIT license.

The codebase is yours to clone, deploy, and build on. Run your own instance for your own content — your deck content stays on your domain, building your authority, not ours.

`vibedeck.online` is the proof of concept. Your instance is the point.

---
type: concept
---

## Built With

- **Astro** — frontend
- **FastAPI** — backend
- **PostgreSQL** — metadata and user data
- **Caddy** — reverse proxy
- **Markdown** — because it should be simple to author

Architectural decisions and editorial judgment by a human. Execution assisted by a very carefully guided code djinni.

---
type: summary
---

## The Full Picture

- Five card types — title, concept, summary, graphic, quote
- Markdown authoring with YAML frontmatter
- Paginated navigation — swipe, buttons, keyboard
- Organized by topic and keyword
- Mobile-first, works everywhere
- Open source, MIT licensed, self-hostable
- `vibedeck.online` — the live proof of concept

---
type: quote
---

> The constraint is the feature. One idea per card, sequenced to build understanding without overwhelm.

*— The Vibedeck design philosophy*
