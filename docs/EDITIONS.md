# Vibedeck Editions — architecture & roadmap

Vibedeck is planned as **three editions** from one core codebase:

1. **Standalone** — a single user running their own decks on their own server.
2. **Server** — a host running decks from many users (a shared/community instance).
3. **Commercial** — a private, hosted, paid product (a revenue stream).

This doc covers the **open-core** concerns (standalone + server) and the architectural decisions that
keep all three buildable from one codebase. Commercial/revenue specifics are kept **out of this repo**
in a private companion doc — see "Commercial" below.

> Status (2026-06): the codebase is a strong base — **standalone is ~90% there**, **server has the
> right bones with a few real gaps**, and **commercial has a solid product underneath but all the
> commercial machinery is greenfield.**

---

## Shared foundation (already built — benefits all editions)

- **Markdown is the source of truth.** Decks are `.md` files under `UPLOAD_DIR`; the DB only indexes
  frontmatter and **card bodies are re-parsed from the file on read** (`backend/services/parser.py`,
  `indexing.py`). This is a genuine differentiator — portability, no lock-in, Git-friendly. Keep it.
- Clean layering: thin routers → services → SQLAlchemy/Alembic; Astro SSR front end; Caddy + systemd
  ops. Easy to extend.
- **Auth**: JWT + passwordless magic-link login, invite-gated signup, bcrypt (`services/auth.py`).
- **Multi-user ownership**: users own decks (`Deck.owner_id`) and **private** per-user themes; user
  endpoints are owner-scoped (`/api/decks/mine`).
- **Admin portal** (owner-only): manage any deck + monitor users
  (`get_current_admin` in `services/auth.py`, `routers/admin.py`).
- **Theming contract** (`--vd-*` tokens) and the **per-deployment landing** (`index.astro` is
  gitignored) — a ready-made seam for per-edition customization.

---

## 1. Standalone (single user, own server) — ~90% there

The original v1 shape; the codebase fits it well. The only friction is that the multi-user machinery
(signup, invite codes, magic links) is overhead for one person.

**To finish:**
- A **single-user mode** (config/flag): disable public signup, treat the one account as owner, and
  optionally allow no-auth public *read*. Mostly configuration, not architecture.

---

## 2. Server (host many users' decks) — good bones, real gaps

Already present: accounts, per-user ownership, private themes, admin oversight, invite-gated signup,
rate limiting, upload size caps.

**Gaps to close:**
- **Content moderation** — required before hosting others' content. Already tracked (see `SPEC.md`
  roadmap + `HANDOFF.md`).
- **Per-deck visibility** — public / private / unlisted. Today **all decks are public**
  (`list_public_decks` returns every indexed deck; there is no visibility flag).
- **Roles** — "admin" is currently a single owner-email check (`get_current_admin`). A real host
  wants promotable admins/moderators (an `is_admin` column).
- **Quotas + abuse controls** — per-user deck/storage limits, a report/takedown path, and a user
  ban/deactivate UI (`User.is_active` exists; no admin control surfaces it yet).

### ⚠️ The key architectural decision: the content namespace

Today the content model is a **communal shared library**, not **per-user spaces**:
- Topics are a **global** namespace (one shared `Topic` table / topic index).
- Deck files are **globally unique**: `deck_filename()` produces `<topic-slug>__<title-slug>.md`, and
  `create_user_deck` raises `DeckConflict` if another user already owns that name
  (`backend/services/decks.py`, `services/indexing.py`).

So two different users **cannot** both have "Astrology / Intro," and everyone contributes to one
shared topic index. That's a perfectly valid product ("a small group curating one library"), but if
"a variety of users" means **isolated per-user spaces** (URLs like `/u/alice/{topic}/{deck}`, browse
by author), the topic model and filename scheme need to be **owner-scoped**.

**Decide communal-vs-per-user before the server edition gets real users** — it drives URLs, on-disk
filenames, and the topic model, and is painful to migrate afterward (URLs break, files move, DB
changes).

---

## 3. Commercial (private, revenue) — product yes, machinery no

The product underneath is a fine base; the commercial edition is a private, hosted, paid build on top
of the open core, and that work is **planned privately — kept out of this repo by design.**

> See **`EDITIONS-COMMERCIAL.md`** (repo root, **gitignored / local only**).

---

## Cross-cutting decisions to make early (cheap now, expensive later)

1. **Namespacing / content model** — communal shared library vs per-user spaces (see Server §). The
   single most consequential call.
2. **Edition seam** — one config-driven codebase (e.g. an `EDITION` setting / feature flags) rather
   than three forks. Standalone and server should differ by configuration, not by code fork.
3. **Open-core split** — core (standalone + server) stays open; commercial features live behind
   interfaces / a separate **private** layer that *depends on* the core package, rather than forking
   the whole codebase. Retrofitting this seam is easier before commercial work begins.

## Readiness checklists

**Server-ready:** content moderation · per-deck visibility · roles (`is_admin`) · quotas + abuse
controls · the namespace decision.

**Commercial-ready:** see the private `EDITIONS-COMMERCIAL.md`.

---

_Companion docs: `SPEC.md` (product spec + roadmap), `HANDOFF.md` (current v2 operational state),
`EDITIONS-COMMERCIAL.md` (private, local — commercial/revenue strategy)._
