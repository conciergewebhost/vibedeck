# Vibedeck

> Digital index cards. Chunked knowledge, beautifully delivered.

Vibedeck is an open-source platform for creating and browsing beautiful,
mobile-first card decks authored in plain markdown. The mental model is the
physical index card — one focused idea per card, sequenced to build
understanding without overwhelm.

It is not a presentation tool. It is a reading and learning experience that
happens to work beautifully in a presentation context.

**Live demo:** [vibedeck.online](https://vibedeck.online)

---

## Features

- **Markdown decks** — one file per deck: YAML frontmatter + `---`-separated cards.
- **Five card types** — `title`, `concept`, `summary`, `graphic`, `quote`.
- **Mobile-first reader** — one card at a time, swipe / arrow-key / button nav,
  progress indicator, and an index modal for jumping around.
- **CSS-variable theming** — ships with `operazione-stile` and `fascicolo`
  (plus a plain `default`), each with a **dark/light toggle** that follows the
  OS preference.
- **Auth-gated uploads** — a discreet `/admin` surface (shared-token gate) and
  a JWT API for uploading/managing decks remotely.
- **Server-side management CLI** — index, list, and delete decks from files.

---

## Tech stack

| Layer | Tech |
|-------|------|
| Frontend | [Astro](https://astro.build) (SSR, Node adapter) |
| Backend | [FastAPI](https://fastapi.tiangolo.com) (Python 3.11+) |
| Database | PostgreSQL + [Alembic](https://alembic.sqlalchemy.org) migrations |
| Auth | JWT (OAuth2 password flow) + bcrypt |
| Proxy (prod) | [Caddy](https://caddyserver.com) |

The markdown file is the **source of truth**; the database only indexes
frontmatter metadata for fast listing. Card bodies are re-parsed from the file
on every read, so editing a deck file needs no database sync.

---

## Repository layout

```
vibedeck/
├── backend/            # FastAPI app — run uvicorn from THIS directory
│   ├── main.py
│   ├── manage.py       # management CLI (create-user, reindex, delete-deck, …)
│   ├── seed.py         # dev seeder
│   ├── models/  routers/  schemas/  services/  tests/
├── frontend/           # Astro SSR project
│   └── src/{layouts,pages,components,lib,styles/themes}
├── migrations/         # Alembic migrations
├── decks/              # markdown decks (the canonical files / UPLOAD_DIR)
├── deploy/             # systemd units + Caddy site block (templates)
├── alembic.ini  requirements.txt  .env.example  Caddyfile.example
├── SPEC.md             # full product spec
└── README.md
```

---

## Local development

### Prerequisites

- Python 3.11+
- Node.js 18.20+ (or 20.3+ / 22+)
- PostgreSQL (a local instance, or Docker)

### 1. Clone

```bash
git clone https://github.com/conciergewebhost/vibedeck.git
cd vibedeck
```

### 2. Start PostgreSQL

Any PostgreSQL works. The quickest is Docker:

```bash
docker run -d --name vibedeck_db \
  -e POSTGRES_USER=vibedeck -e POSTGRES_PASSWORD=vibedeck -e POSTGRES_DB=vibedeck \
  -p 5432:5432 -v vibedeck_pgdata:/var/lib/postgresql/data postgres:16
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set:

| Variable | Notes |
|----------|-------|
| `DATABASE_URL` | e.g. `postgresql+psycopg://vibedeck:vibedeck@localhost:5432/vibedeck` |
| `SECRET_KEY` | `openssl rand -hex 32` |
| `UPLOAD_DIR` | **absolute** path to the repo's `decks/` directory |
| `UPLOAD_TOKEN` | `openssl rand -hex 32` — the `/admin` access token |
| `UPLOAD_OWNER_EMAIL` | the account that uploaded/indexed decks belong to |
| `BASE_URL` | `http://localhost:4321` for local dev |
| `ENVIRONMENT` | `development` |

### 4. Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create the schema (run from the repo root):
alembic upgrade head

# Create the owner account (prompts for a password):
cd backend
python manage.py create-user "$(grep ^UPLOAD_OWNER_EMAIL ../.env | cut -d= -f2)"

# Index the sample decks under decks/ :
python manage.py reindex

# Run the API (must be started from the backend/ directory):
uvicorn main:app --reload          # serves http://localhost:8000
```

### 5. Frontend

In a second terminal:

```bash
cd frontend
npm install
echo "API_BASE_URL=http://localhost:8000" > .env   # see frontend/.env.example
npm run dev                                          # serves http://localhost:4321
```

Open **http://localhost:4321** — you should see the sample decks.

---

## Authoring decks

A deck is a single markdown file: YAML frontmatter, then cards separated by a
line containing exactly `---`, where each card opens with its own `type:`
frontmatter block.

```markdown
---
title: My Deck
author: Jane Doe
topic: Demo
keywords: [intro, demo]
theme: operazione-stile
description: A short summary for the index listing.
---

---
type: title
---

# My Deck
### a subtitle

---
type: concept
---

## One idea

Kept deliberately small. The constraint is the feature.
```

**Frontmatter:** `title`, `author`, `topic`, `keywords`, `theme` are required;
`description` is optional. **Card types:** `title`, `concept`, `summary`,
`graphic`, `quote`. **Themes:** `operazione-stile`, `fascicolo`, `default`
(see `frontend/src/styles/themes/`). A card body cannot contain a line that is
exactly `---` (that's the card separator — use `***` for a horizontal rule).

### Adding a deck

Two ways:

- **From the server (CLI):** drop the `.md` file into `decks/` and run
  `python manage.py reindex` (from `backend/`). `reindex` also prunes decks
  whose files were removed.
- **Over the web:** visit `/admin`, enter the `UPLOAD_TOKEN`, and upload the
  file. Uploaded decks are attributed to `UPLOAD_OWNER_EMAIL`.

---

## Management CLI

Run from `backend/` with the venv active:

```bash
python manage.py create-user EMAIL [--password PW]   # provision a user
python manage.py delete-user EMAIL                   # (must own no decks)
python manage.py list-decks                          # list indexed decks
python manage.py reindex                             # index decks/*.md + prune
python manage.py delete-deck TOPIC_SLUG DECK_SLUG    # remove a deck + prune
```

## Tests

```bash
cd backend
python -m unittest discover -s tests
```

---

## Production deployment

Vibedeck runs as two localhost services behind Caddy: the FastAPI backend and
the Astro SSR server. The `deploy/` directory contains **templates** you must
adapt to your host (paths, the `node` binary location, ports, and your domain):

- `deploy/systemd/vibedeck-api.service` — uvicorn backend
- `deploy/systemd/vibedeck-web.service` — Astro SSR (`node ./dist/server/entry.mjs`)
- `deploy/caddy/vibedeck.online.caddy` — reverse-proxies `/api/*` → backend, the
  rest → frontend (also see `Caddyfile.example`)

Outline: set production values in `.env` (`ENVIRONMENT=production`, your
`BASE_URL`); build the frontend (`cd frontend && npm run build`); install and
enable the two systemd units; add the Caddy block and reload Caddy. Caddy
handles TLS automatically.

---

## Documentation

- [`SPEC.md`](SPEC.md) — the full product specification.
- [`CLAUDE.md`](CLAUDE.md) — conventions and working notes (for contributors and
  AI coding assistants).

## License

[MIT](LICENSE) © Rob Wall. Deck *content* published to any Vibedeck instance
remains the copyright of its respective authors and is not covered by this
license.

*Built by [Concierge Web Host](https://conciergewebhost.ca).*
