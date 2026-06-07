# Vibedeck Editions — architecture & roadmap

Vibedeck is built to run as **two editions** from one config-driven codebase:

1. **Standalone** — a single user running their own decks on their own server.
2. **Server** — a host running decks from many users (a shared/community instance).

They differ by **configuration, not by a code fork** (an `EDITION` setting drives a set of derived
feature flags). This doc covers the architecture and the decisions that keep both buildable from one
codebase.

> Status (2026-06): the codebase is a strong base — **standalone is ~90% there** and **server has the
> right bones with a few real gaps.**

---

## Shared foundation (already built — benefits both editions)

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
- **Edition seam**: an `EDITION` setting in `backend/config.py` with derived feature flags, exposed
  to the frontend via `GET /api/meta` so pages adapt without a rebuild.
- **Theming contract** (`--vd-*` tokens) and the **per-deployment landing** (`index.astro` is
  gitignored) — a ready-made seam for per-deployment customization.

---

## 1. Standalone (single user, own server) — ~90% there

The original v1 shape; the codebase fits it well. The only friction is that the multi-user machinery
(signup, invite codes, magic links) is overhead for one person.

**To finish:**
- A **single-user mode**, keyed on `EDITION == standalone`: disable public signup, treat the one
  account as owner, and allow no-auth public *read*. Mostly configuration, not architecture.

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

**Decision (made): per-user spaces.** This drives URLs, on-disk filenames, and the topic model, and
is painful to migrate afterward (URLs break, files move, DB changes), so it is sequenced first within
the server work — before visibility, roles, moderation, and quotas build on top of it.

---

## Cross-cutting decisions to make early (cheap now, expensive later)

1. **Namespacing / content model** — communal shared library vs per-user spaces (see Server §). The
   single most consequential call. **Decided: per-user spaces.**
2. **Edition seam** — one config-driven codebase (an `EDITION` setting / feature flags) rather than
   forks. Standalone and server differ by configuration, not by code.
3. **Extensibility** — keep limit/policy decisions behind **overridable functions / interfaces** and
   a feature-flagged seam, so the server can be extended by **private modules** without forking the
   codebase. The backend loads an optional `private` package if present (`backend/main.py`); when it
   is absent the deployment runs as plain open core.

## Readiness checklist

**Server-ready:** content moderation · per-deck visibility · roles (`is_admin`) · quotas + abuse
controls · the namespace rework.

---

_Companion docs: `SPEC.md` (product spec + roadmap), `HANDOFF.md` (current v2 operational state)._
