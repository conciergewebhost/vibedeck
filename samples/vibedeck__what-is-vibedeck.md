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

Vibedeck supports five card types:

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

## Or Author in the Browser

You don't have to touch a file at all.

Sign in and the **deck builder** walks you through it card by card, with the right fields for each card type. Prefer raw markdown? The in-browser **editor** has a live preview.

Not signed up yet? The **sandbox** lets anyone paste markdown and preview a deck instantly — nothing is saved, nothing is published.

---
type: concept
---

## The Reading Experience

Readers move through a deck with swipes, arrow keys, or buttons — with a progress indicator and an index for jumping straight to a card.

Authors can tune the feel from frontmatter: a **slide** or **fade** transition between cards, and **progressive bullet reveal**, where each advance surfaces the next point before moving on.

---
type: concept
---

## How Decks Are Organized

Every author has a public handle and an author page:

`vibedeck.online/u/robwall` — everything by one author

Within that, decks are grouped by **topic**:

`vibedeck.online/u/robwall/vibedeck` — this deck's topic

Each deck also carries **keywords** for finer-grained thematic grouping within a topic.

---
type: concept
---

## Sharing — On Your Terms

Each deck has a visibility setting:

**Public** — listed in the library, visible to everyone

**Unlisted** — anyone with the link can read it; it just isn't listed

**Private** — only you, signed in

And every public deck has an **embed widget**: a copy-paste snippet that drops the deck into any page that accepts HTML.

---
type: concept
---

## The Open Source Project

Vibedeck is open source under the MIT license.

One codebase, two ways to run it: **standalone** — just you, on your own server — or **server** — a multi-user host with sign-ups, like `vibedeck.online`.

Your deck content stays on your domain, building your authority, not ours. `vibedeck.online` is the proof of concept. Your instance is the point.

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
- Author in markdown, or in the browser — builder, editor, and sandbox
- Paginated navigation — swipe, buttons, keyboard — plus transitions and bullet reveal
- Author pages, topics, and keywords for organization
- Public, unlisted, or private — with an embed widget for sharing
- Custom themes, built in the browser
- Open source, MIT licensed, self-hostable — standalone or multi-user

---
type: quote
---

> The constraint is the feature. One idea per card, sequenced to build understanding without overwhelm.

*— The Vibedeck design philosophy*
