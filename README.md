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
  progress indicator, an index modal, per-deck **card transitions**
  (`slide`/`fade`/`none`), and optional **progressive bullet reveal**.
- **In-browser authoring** — a form-based **deck builder**, a raw **markdown editor**
  with live preview, and `.md`/`.css` **file uploads** that are inspected on the
  way in (parse errors, unsafe markup, moderation, quotas — problems are
  reported back verbatim).
- **CSS-variable theming** — built-in themes (`operazione-stile`, `fascicolo`, `default`)
  with an OS-aware **dark/light toggle**, plus a form-based **theme builder** for per-user
  custom themes that render for **every** reader of a deck.
- **Per-user spaces** *(server edition)* — every author has a public handle, an
  author page (`/u/{handle}`), and namespaced deck URLs; legacy flat URLs 301.
- **Discovery** — full-content **search** across the library and clickable
  **keyword filtering** on every deck list.
- **Per-deck visibility** — `public`, `unlisted` (link-only), or `private` (owner-only).
- **Community safety** *(server edition)* — algorithmic **content moderation**
  (auto-block egregious, quarantine suspicious for human review), a reader
  **Report** path with auto-quarantine at a threshold, per-user **quotas**, and
  **ban/deactivate** controls — all surfaced in the admin portal, with a daily
  digest email.
- **Roles** — promotable admins (`is_admin`); the owner manages roles and the
  runtime **signup gate** (invite code on/off + the code itself) from the admin
  Settings tab.
- **Embeds** — every public deck has an `/embed/...` widget + copy-paste snippet.
- **Two editions from one codebase** — an `EDITION` setting selects **standalone**
  (single user, flat URLs) or **server** (multi-user host). See
  [`docs/EDITIONS.md`](docs/EDITIONS.md).
- **Auth** — three login methods, auto-detected from config: magic links
  (Resend, any SMTP server, or — with no email provider — links written to the
  server log), per-account passwords, and an optional shared site password for
  single-user instances. Invite-gated signup with chosen handles, and a
  session-first `/admin` surface (shared-token fallback).
- **Server-side management CLI** — provision users, promote/demote, reindex,
  tidy files, delete decks.

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
├── decks/              # LIVE deck files (UPLOAD_DIR) — gitignored user content
├── samples/            # bundled reference decks (seed.py copies them in)
├── deploy/             # systemd units (app + digest timer) + Caddy templates
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
| `EDITION` | `standalone` (single user, no public signup) or `server` (multi-user host); defaults to `standalone` |
| `NEW_USER_CODE` | invite code that gates new sign-ups (seed value; changeable at runtime from the admin Settings tab) |

Everything else is optional — see [Signing in](#signing-in) below and the
comments in `.env.example` for email delivery (`RESEND_API_KEY` or `SMTP_*`)
and the single-user `SITE_PASSWORD`. With no email settings at all, magic
sign-in links are written to the server log instead of emailed, so a fresh
clone is fully usable without any email account.

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

# Seed the bundled sample decks (copies samples/ into decks/ and indexes):
python seed.py

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

## Signing in

The `/login` page offers up to three methods; which ones appear is
auto-detected from your `.env` (no extra switch to set):

1. **Magic link** — always available. How the link reaches you depends on
   what's configured:
   - `RESEND_API_KEY` set → emailed via [Resend](https://resend.com);
   - `SMTP_HOST` set → emailed via your SMTP server (`SMTP_PORT`,
     `SMTP_USERNAME`/`SMTP_PASSWORD`, `SMTP_TLS`);
   - neither → the link is **written to the server log** (dev: the uvicorn
     console; production: `journalctl -u <api-service>`). Zero email setup,
     at the cost of the operator fishing links out of the log.

   Configure at most one provider; `EMAIL_FROM_ADDRESS` is required with
   either. Misconfigured combinations fail at startup with a clear error.
2. **Account password** — always available, for accounts that have one:
   `python manage.py create-user you@example.com --password ...` (run from
   `backend/`). There is no self-serve password signup; magic-link signup is
   the only public registration path.
3. **Site password** — only when `SITE_PASSWORD` is set. A shared password
   that signs you in as the `UPLOAD_OWNER_EMAIL` account — the simplest
   option for a single-user (standalone) instance.

OAuth/OIDC and passkeys are not implemented yet.
<!-- TODO(post-v2): OAuth/OIDC (GitHub/Google) and passkey login. -->

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

The complete format reference — every field, card type, and validation
rule, with a worked example — is
[`docs/VIBEDECK_FORMAT.md`](docs/VIBEDECK_FORMAT.md) (written to double as
AI-assistant context for generating decks). The short version:

**Frontmatter:** `title`, `author`, `topic`, `keywords`, `theme` are required;
optional: `description`, `visibility` (`public` / `unlisted` / `private`),
`transition` (`slide` / `fade` / `none` — the reader's card animation), and
`reveal: bullets` (bullet lists reveal one item per advance).
**Card types:** `title`, `concept`, `summary`, `graphic`, `quote`. **Themes:**
`operazione-stile`, `fascicolo`, `default` (see `frontend/src/styles/themes/`),
or a per-user theme built in the theme builder — see
[`docs/THEMING.md`](docs/THEMING.md). A card body cannot contain a line
that is exactly `---` (that's the card separator — use `***` for a horizontal rule).

### Adding a deck

- **In the browser:** sign in and use the `/account` portal — the **deck builder**
  (`/account/build`, guided form) or the **markdown editor** (`/account/edit`), and the
  **theme builder** (`/account/theme`) for custom styles. This is the normal path.
- **From the server (CLI):** drop the `.md` file into `decks/` and run
  `python manage.py reindex` (from `backend/`). `reindex` also prunes decks
  whose files were removed.
- **Over the web (admin):** visit `/admin`, enter the `UPLOAD_TOKEN`, and upload the
  file. Uploaded decks are attributed to `UPLOAD_OWNER_EMAIL`.

---

## Management CLI

Run from `backend/` with the venv active:

```bash
python manage.py create-user EMAIL [--password PW] [--handle NAME]  # provision a user
python manage.py delete-user EMAIL                   # (must own no decks)
python manage.py promote-user EMAIL                  # grant the admin surface
python manage.py demote-user EMAIL                   # revoke admin rights
python manage.py list-decks                          # list indexed decks
python manage.py reindex                             # index all deck files + prune
python manage.py tidy                                # move legacy flat files into owner dirs
python manage.py delete-deck TOPIC_SLUG DECK_SLUG [--handle NAME]   # remove a deck
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
- `deploy/systemd/vibedeck-digest.{service,timer}` — the daily moderation digest
  email (server edition)
- `deploy/caddy/vibedeck.online.caddy` — reverse-proxies `/api/*` → backend, the
  rest → frontend (also see `Caddyfile.example`)

Outline: set production values in `.env` (`ENVIRONMENT=production`, your
`BASE_URL`); build the frontend (`cd frontend && npm run build`); install and
enable the two systemd units; add the Caddy block and reload Caddy. Caddy
handles TLS automatically.

---

## Documentation

- [`SPEC.md`](SPEC.md) — the full product specification.
- [`docs/VIBEDECK_FORMAT.md`](docs/VIBEDECK_FORMAT.md) — the deck-file authoring reference: every field, card type, and rule, with examples. Written to double as AI-assistant context for generating decks.
- [`docs/THEMING.md`](docs/THEMING.md) — creating themes: the token contract, the in-browser builder, and CSS-file themes.
- [`docs/EDITIONS.md`](docs/EDITIONS.md) — the standalone/server edition architecture and roadmap.
- [`CLAUDE.md`](CLAUDE.md) — conventions and working notes (for contributors and
  AI coding assistants).

## License

[MIT](LICENSE) © Rob Wall. Deck *content* published to any Vibedeck instance
remains the copyright of its respective authors and is not covered by this
license.

*Built by [Concierge Web Host](https://conciergewebhost.ca).*
