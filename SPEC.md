# Vibedeck — Project Specification

> Digital index cards. Chunked knowledge, beautifully delivered.

**Domain:** vibedeck.online  
**Status:** Pre-development  
**Version:** 0.1 (Initial Spec)

---

## Concept

Vibedeck is a hosted platform for creating and browsing beautiful, mobile-first, paginated card decks authored in plain markdown. The mental model is the physical index card — a single, focused unit of knowledge, designed to be consumed without overwhelm, sequenced to build understanding progressively.

It is explicitly **not** a presentation tool. It is a reading and learning experience that happens to work beautifully in a presentation context.

### Primary Use Case
Educational and training content — explainers, topic introductions, concept breakdowns, study guides — delivered in a format that works equally well on a phone, tablet, or projected screen.

### Positioning
Vibedeck is the open source project. `vibedeck.online` is the proof-of-concept deployment. Production implementations (e.g. `learn.z13astrology.com`) run their own instances against real content libraries.

---

## Architecture

### Tech Stack
- **Frontend:** Astro
- **Backend:** FastAPI (Python)
- **Database:** PostgreSQL
- **Reverse Proxy:** Caddy
- **Hosting:** OVH VPS

### URL Structure

| URL | Description |
|-----|-------------|
| `vibedeck.online` | Master index — all topics, grouped |
| `vibedeck.online/{topic}` | All decks within a topic |
| `vibedeck.online/{topic}/{deck-slug}` | Individual deck, paginated card view |
| `vibedeck.online/{topic}?kw={keyword}` | Keyword-filtered deck list (v2) |

Topic slugs are lowercase and hyphen-separated, derived directly from the `topic` frontmatter field.

---

## Content Model

### Deck Frontmatter

Each deck is a single markdown file. Deck-level metadata is defined in YAML frontmatter:

```yaml
title: The 12 Houses
author: Rob Wall
topic: z13
keywords: [houses, natal-chart, beginner]
theme: z13-dark
description: A beginner-friendly introduction to the 12 houses in astrology.
```

| Field | Required | Description |
|-------|----------|-------------|
| `title` | Yes | Display name of the deck |
| `author` | Yes | Author name |
| `topic` | Yes | URL segment and grouping key |
| `keywords` | Yes | Array of thematic tags for filtering |
| `theme` | Yes | CSS theme identifier |
| `description` | No | Short deck summary for index listing |

### Card Separator
Cards are separated by `---` within the markdown file.

### Card Types (v1)

Each card begins with a type declaration in its own frontmatter block:

```yaml
type: concept
```

| Type | Description |
|------|-------------|
| `title` | Deck title card — opening card, large display treatment |
| `concept` | Single idea, explained cleanly. The constraint is the feature. |
| `summary` | Big picture consolidation. Bullet points. Palette cleanser between concept runs. |
| `graphic` | Full-bleed image or chart with a small caption beneath. |
| `quote` | Pull quote, styled distinctively. Attribution optional. |

Extensibility for custom card types is a post-v1 target.

### Example Deck Structure

```markdown
---
title: The 12 Houses
author: Rob Wall
topic: z13
keywords: [houses, natal-chart, beginner]
theme: z13-dark
description: A beginner-friendly introduction to the 12 houses in astrology.
---

---
type: title
---

# The 12 Houses
### An introduction to the architecture of your birth chart

---
type: concept
---

## What is a House?

The birth chart is divided into 12 houses — each one a distinct area of life experience.
Where a planet falls in your chart tells you *what* energy is present.
The house tells you *where* that energy plays out.

---
type: summary
---

## So Far

- The chart has 12 houses
- Each house governs a domain of lived experience
- Planet = energy. House = arena.
- Your rising sign determines which house is which

---
type: graphic
---

![The 12 Houses Diagram](/images/12-houses.png)

*The wheel of the birth chart, showing all 12 house divisions.*

---
type: quote
---

> "The houses are the stage. The planets are the actors."
> — Anonymous
```

---

## User Interface

### Card View

- Mobile-first, full-viewport card display
- One card visible at a time
- Paginated navigation — discrete cards, not continuous scroll
- Clean typographic hierarchy per card type
- Theme applied via CSS variables from frontmatter

### Navigation

| Element | Behaviour |
|---------|-----------|
| Swipe left/right | Next / previous card (mobile) |
| Arrow buttons | Next / previous card (all devices) |
| Keyboard arrows | Next / previous card (desktop) |
| Progress indicator | Discreet "Page n of total" at card bottom |
| Index icon | Opens index modal — full card list, tappable for direct jump |
| Back button (modal) | Returns user to deck index for current topic |

### Deck Index Page (`/{topic}`)

- List view of all decks in the topic
- Grouped and browsable by keyword (data captured v1, filtering UI v2)
- Each deck entry shows: title, description, author, keyword tags, card count

### Master Index (`/`)

- All topics listed
- Each topic shows deck count and top keywords
- Entry point for browsing the full content library

---

## Theming

- Themes defined as CSS variable sets
- Theme selected via `theme` field in deck frontmatter
- Each topic can have a signature theme
- v1 ships with a small set of built-in themes
- Custom themes via additional CSS variable files

---

## Authentication

Auth is baked into the data model from day one, even though v1 content is publicly browsable without login.

This positions the platform for:
- Private decks (auth-gated content)
- Multi-user publishing
- Per-user deck libraries

Implementation: standard JWT-based auth, user table in PostgreSQL from initial schema. Not exposed in v1 UI beyond what's needed for the upload interface.

---

## Upload Interface

- Web-based markdown file upload from day one
- Parses frontmatter on upload, validates required fields
- Generates deck slug from title
- Stores deck file and registers metadata in PostgreSQL
- Auth-protected (logged-in users only)

---

## Deployment Model

### vibedeck.online (Proof of Concept)
The canonical public deployment. Demonstrates the platform with real decks across multiple topics. Primary face of the open source project.

### Self-Hosted Instances
Anyone can clone the repo and run their own instance. Documentation covers VPS deployment with Caddy. Example: `learn.z13astrology.com` running a Z13-specific instance.

### SEO Note
Content-specific deployments (e.g. Z13 educational material) should run on their own domain instances rather than on vibedeck.online, so that content authority accrues to the relevant domain rather than to the platform domain.

---

## Roadmap

### v1 (MVP)
- [ ] Core card types: title, concept, summary, graphic, quote
- [ ] Markdown authoring with frontmatter
- [ ] Paginated card view with full navigation
- [ ] Deck index per topic
- [ ] Master index
- [ ] CSS variable theming with frontmatter selection
- [ ] Web upload interface
- [ ] Auth infrastructure (backend, not full UI)
- [ ] PostgreSQL schema: users, decks, topics, keywords

### v2
- [ ] Keyword filtering UI on deck index
- [ ] Search across decks
- [ ] User-facing auth (login, profile, my decks)
- [ ] Private/public deck toggle
- [ ] Custom theme upload

### Post-v2
- [ ] Multi-user publishing
- [ ] Custom card type extensibility
- [ ] Analytics per deck (views, completion rate)
- [ ] Embeddable single-deck widget

---

## Local Development

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL (local instance or Docker)

### Database
The repository does not include a database. It includes everything needed to create one:

- **Migrations** — Alembic migration files that define the full schema. Run these against your own PostgreSQL instance to create the required tables, relationships, and indexes.
- **`.env.example`** — A template environment file listing all required variables including the database connection string. Copy to `.env` and populate with your own values. Never commit `.env` to the repo.

### Setup Steps
```bash
# Clone the repo
git clone https://github.com/conciergewebhost/vibedeck.git
cd vibedeck

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your database connection string and other config

# Install Python dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Install frontend dependencies
npm install

# Start the development servers
# Backend (FastAPI)
uvicorn main:app --reload

# Frontend (Astro)
npm run dev
```

### Environment Variables
| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `SECRET_KEY` | JWT signing secret |
| `UPLOAD_DIR` | Path to deck file storage |
| `BASE_URL` | Public URL of the instance |

### Deployment
Production deployments use Caddy as reverse proxy. A `Caddyfile.example` is included in the repo. See the deployment documentation for full VPS setup instructions.

---

## Open Source

**Repository:** github.com/conciergewebhost/vibedeck  
**License:** MIT  
**README:** Links to vibedeck.online as live demo and learn.z13astrology.com as production example.

### Content vs Code
The Vibedeck codebase is MIT licensed. Deck content published to any Vibedeck instance remains the copyright of the respective authors and is not covered by the repository license.

---

*Spec compiled June 2026. Subject to revision as development proceeds.*
