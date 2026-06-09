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
- **Multi-user ownership**: users own decks (`Deck.owner_id`) and per-user themes; user endpoints are
  owner-scoped (`/api/decks/mine`).
- **Form-based authoring**: a deck builder (`/account/build`, per-card-type fields) and a theme builder
  (`/account/theme`, generates a safe `:root{--vd-*}` block — no raw-CSS upload), alongside the raw
  markdown editor. Lowers the bar for non-technical authors.
- **Per-deck visibility**: `public` / `unlisted` / `private` (frontmatter + `Deck.visibility`).
  Listings show public only; private 404s the public reader and renders only for the owner.
- **Admin portal** (owner-only): manage any deck + monitor users
  (`get_current_admin` in `services/auth.py`, `routers/admin.py`).
- **Edition seam**: an `EDITION` setting in `backend/config.py` with derived feature flags, exposed
  to the frontend via `GET /api/meta` so pages adapt without a rebuild.
- **Theming contract** (`--vd-*` tokens), custom themes **inlined for every reader** at SSR
  (`GET /api/decks/{topic}/{deck}/theme.css`), and the **per-deployment landing** (`index.astro` is
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

**Gaps to close:** none — the server-edition checklist is complete. (Still optional/deferred:
the AI moderation second pass; see `HANDOFF.md`.)

**Already closed:**
- ~~Per-deck visibility~~ — `public` / `unlisted` / `private` shipped (`Deck.visibility`).
- ~~Roles~~ — **promotable admins shipped**: `users.is_admin` grants the full admin surface;
  the owner (`UPLOAD_OWNER_EMAIL`) is admin by config fallback (can't be locked out) and is the
  only one who can promote/demote (`get_current_owner`). Admins enter `/admin` with their own
  session (attributable); the shared `UPLOAD_TOKEN` unlock remains as the owner fallback.
- ~~Quotas + abuse controls~~ — **shipped**: per-user deck/theme caps (`QUOTA_MAX_DECKS`/
  `QUOTA_MAX_THEMES`, server edition, admins exempt); a reader report path (`POST /api/reports`,
  rate-limited, deduped per reporter) that auto-quarantines a deck at `REPORT_QUARANTINE_THRESHOLD`
  distinct reporters into the existing moderation review queue, plus an admin Reports tab; and
  ban/deactivate (`POST /api/admin/users/{id}/deactivate|reactivate`) — a ban hides all the user's
  public content at read time and closes the magic-link re-entry holes.
- ~~Content moderation~~ — the algorithmic layer shipped (hybrid auto-block/flag + admin review
  queue + daily digest; AI second pass still deferred — see `HANDOFF.md`).
- ~~The namespace rework~~ — **per-user spaces shipped**: users have public handles, topics are
  owner-scoped (unique per owner), new deck files live under per-owner subdirs (legacy flat files
  stay valid; `manage.py tidy` is optional housekeeping). Server-edition URLs are
  `/u/{handle}/{topic}/{deck}` + an author page `/u/{handle}`; legacy flat URLs 301 while
  unambiguous. **Standalone keeps flat URLs** — the editions share one data model and differ only
  in URL shape (`services/urls.py`, the single place it's decided).

### The content namespace — DECIDED AND BUILT: per-user spaces

Every user is a namespace owner. `users.handle` (chosen at signup, slug-validated with a reserved
blocklist in `services/handles.py`; derived from the email local-part for pre-existing accounts) is
the public URL segment. `topics` are unique per `(owner_id, slug)`; `deck_filename()` derives
`{handle}/{topic}__{title}.md` for new decks while `Deck.filename` is treated as an opaque relative
path so legacy flat files never have to move. Flat lookups resolve only unambiguous matches —
canonical in standalone, 301-redirects in the server edition. Admin deck actions are keyed by deck
row id (collision-proof). Handles are immutable for now; a rename feature later is cheap because
nothing but the `users.handle` column carries the name.

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

**Server-ready: COMPLETE.** Per-deck visibility · algorithmic content moderation · the
per-user-spaces namespace rework · roles/promotable admins · quotas + abuse controls. The one
optional follow-up is the AI moderation second pass (escalate-only Claude classifier seam in
`services/moderation.py`).

---

_Companion docs: `SPEC.md` (product spec + roadmap), `HANDOFF.md` (current v2 operational state)._
