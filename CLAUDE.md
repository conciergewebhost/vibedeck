# CLAUDE.md — Vibedeck

Working instructions for Claude Code on the Vibedeck project.

---

## What This Project Is

Vibedeck is a hosted platform for creating and browsing mobile-first, paginated card decks authored in markdown. The mental model is the physical index card — one focused idea per card, sequenced to build understanding progressively.

Full specification: `SPEC.md`

---

## Infrastructure

- **Server:** concierge_noir (OVH VPS)
- **Reverse Proxy:** Caddy
- **Frontend:** Astro
- **Backend:** FastAPI (Python)
- **Database:** PostgreSQL
- **Migrations:** Alembic
- **Auth:** JWT-based

---

## Project Structure

```
vibedeck/
├── frontend/          # Astro project
│   ├── src/
│   │   ├── components/
│   │   ├── layouts/
│   │   ├── pages/
│   │   └── styles/    # CSS variables and themes
│   └── public/
├── backend/           # FastAPI project
│   ├── main.py
│   ├── routers/
│   ├── models/        # SQLAlchemy models
│   ├── schemas/       # Pydantic schemas
│   └── services/      # Business logic
├── migrations/        # Alembic migration files
├── decks/             # LIVE deck files (UPLOAD_DIR) — gitignored user content
├── samples/           # bundled reference decks (seed.py copies them in)
├── .env.example
├── Caddyfile.example
├── CLAUDE.md
├── README.md
└── SPEC.md
```

---

## Stack Conventions

### Python / FastAPI
- Python 3.11+
- Use Pydantic v2 for all schemas
- SQLAlchemy 2.0 ORM style (not legacy query API)
- One router file per resource (decks, topics, users, auth)
- Services layer handles business logic — routers stay thin
- All database access goes through SQLAlchemy sessions, never raw SQL

### Alembic
- Every schema change gets a migration — never modify tables manually
- Migration messages should be descriptive: `add_keywords_table` not `update_1`
- Always generate migrations with `alembic revision --autogenerate -m "description"`

### Astro
- Component-based — one component per card type
- CSS variables for all theming — no hardcoded colours anywhere
- Mobile-first styles — desktop is the enhancement, not the default
- No inline styles

### CSS / Theming
- All theme values defined as CSS variables in `/frontend/src/styles/themes/`
- One file per theme, e.g. `z13-dark.css`, `default.css`
- Frontmatter `theme` field maps directly to a theme filename

---

## Decision Protocol

### Stop and ask before proceeding:
- Any change to the database schema
- Any change to the auth model, JWT handling, or user permissions
- Any new table or migration
- Anything that affects how deck files are stored or parsed

### Proceed and document:
- Everything else — make the best decision, leave a comment in the code explaining the reasoning, mention it in the session summary

---

## Working Style

- **Build in small, testable increments.** Scaffold the structure first, then implement feature by feature. Don't build everything at once.
- **Tell me what you're about to do before doing it** when starting a new feature area — one sentence is enough.
- **Prefer explicit over clever.** Readable code over terse code. This project will be read by contributors who aren't familiar with the codebase.
- **No premature abstraction.** If something only happens once, don't abstract it. Abstract when the third instance appears.
- **Leave TODO comments** for anything deferred to v2 rather than silently skipping it.

---

## Environment Variables

Defined in `.env`, never committed. Use `.env.example` as the template.

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `SECRET_KEY` | JWT signing secret — generate with `openssl rand -hex 32` |
| `UPLOAD_DIR` | Absolute path to deck file storage |
| `BASE_URL` | Public URL of this instance |
| `ENVIRONMENT` | `development` or `production` |
| `EDITION` | `standalone` (single user, no public signup) or `server` (multi-user host) — defaults to `standalone` |
| `UPLOAD_TOKEN` | Shared token for the `/admin` web upload surface — `openssl rand -hex 32` |
| `UPLOAD_OWNER_EMAIL` | Account that token-gated and CLI uploads are attributed to |
| `ADMIN_DIGEST_EMAIL` | Recipient of the daily moderation digest (optional — defaults to `UPLOAD_OWNER_EMAIL`) |
| `QUOTA_MAX_DECKS` / `QUOTA_MAX_THEMES` | Per-user creation caps, server edition only (optional — default 50 / 20; admins exempt) |
| `REPORT_QUARANTINE_THRESHOLD` | Distinct reader reports that auto-quarantine a deck (optional — default 3) |
| `NEW_USER_CODE` | Seed/fallback invite code — runtime on/off + code changes live in the admin Settings tab (`site_settings` table) |
| `RESEND_API_KEY` | Resend API key for magic-link email (optional — see email delivery note below) |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_TLS` | SMTP alternative to Resend (optional; configure at most one provider) |
| `EMAIL_FROM_ADDRESS` / `EMAIL_FROM_NAME` | Sender identity — `EMAIL_FROM_ADDRESS` required iff Resend or SMTP is configured |
| `SITE_PASSWORD` | Optional shared login password (single-user instances); sessions issue as `UPLOAD_OWNER_EMAIL` |

**Email delivery is auto-detected** (`settings.email_delivery`): Resend if
`RESEND_API_KEY`, else SMTP if `SMTP_HOST`, else **log mode** — magic links are
written to the server log instead of emailed. Login methods offered on `/login`
follow the same auto-detection via `/api/meta` (`auth_methods`).

---

## v1 Scope — What We're Building Now

- [x] Project scaffold — frontend and backend structure
- [x] PostgreSQL schema and Alembic migrations: users, decks, topics, keywords
- [x] Markdown parser — reads frontmatter and card blocks from uploaded files
- [x] FastAPI backend — deck upload, deck retrieval, topic listing
- [x] Auth infrastructure — JWT, user model, protected upload endpoint
- [x] Astro frontend — master index, topic index, card deck view
- [x] Card types: title, concept, summary, graphic, quote
- [x] Paginated navigation — swipe, buttons, keyboard arrows
- [x] Progress indicator — "Page n of total"
- [x] Index modal — card list, direct jump, back to topic
- [x] CSS variable theming — default theme ships with v1
- [x] Caddyfile.example for production deployment

**Not in v1:** keyword filtering UI, user-facing auth UI, private decks, custom themes, multi-user publishing.

---

## Deployment

Production runs on concierge_noir behind Caddy. The `Caddyfile.example` in the repo root covers the basic reverse proxy config. Environment variables are set in `.env` on the server — never in the repo.

---

*Last updated: June 2026*
