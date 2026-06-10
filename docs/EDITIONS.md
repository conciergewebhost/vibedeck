# Vibedeck Editions — how one codebase runs two ways

Vibedeck runs as **two editions** from one config-driven codebase:

1. **Standalone** — a single user running their own decks on their own server.
2. **Server** — a host running decks from many users (a shared/community instance).

They differ by **configuration, not by a code fork**. This doc explains the
seam that makes that work, what actually differs between the editions, and
the content model they share.

---

## The edition seam

A single `EDITION` setting (`standalone` | `server`, default `standalone`)
in `backend/config.py` drives a set of **derived feature flags**. Nothing in
the app branches on the raw `EDITION` value — everything reads the flags:

| Flag | Standalone | Server | Gates |
|---|---|---|---|
| `allow_public_signup` | off | on | The sign-up surface (invite-gated on server) |
| `user_spaces_enabled` | off | on | URL shape: flat `/{topic}/{deck}` vs `/u/{handle}/…` |
| `moderation_enabled` | off | on | Content moderation on submitted decks |
| `visibility_enabled` | off | on | Per-deck `public` / `unlisted` / `private` |
| `quotas_enabled` | off | on | Per-user deck/theme caps (admins exempt) |
| `allow_anon_read` | on | on | Public reading without a session (both editions today) |

The flags are exposed (non-secret) to the frontend via `GET /api/meta`, so
Astro pages adapt their UI — which login methods to offer, whether to show
the sandbox or sign-up affordances — **without a rebuild**.

Switching edition is a `.env` change and a service restart. The data model
is identical in both editions; nothing has to migrate.

---

## The content namespace: per-user spaces

Every user is a namespace owner; the editions differ only in whether the
namespace appears in URLs.

- **Handles.** `users.handle` (chosen at signup; slug-validated against a
  reserved blocklist in `services/handles.py`) is the public URL segment.
  Handles are immutable for now — a rename feature later is cheap because
  nothing but the `users.handle` column carries the name.
- **Owner-scoped topics.** `topics` are unique per `(owner_id, slug)`, so
  two authors can each have a `recipes` topic without colliding.
- **Opaque file paths.** `Deck.filename` is treated as an opaque relative
  path under `UPLOAD_DIR`. New decks are written to
  `{handle}/{topic}__{title}.md`; legacy flat files stay valid forever and
  never have to move (`manage.py tidy` is optional housekeeping).
- **URL shape is decided in exactly one place** — `services/urls.py`, off
  `user_spaces_enabled`:
  - **Server:** `/u/{handle}/{topic}/{deck}` plus an author page
    `/u/{handle}`. Legacy flat URLs 301-redirect while unambiguous.
  - **Standalone:** flat `/{topic}/{deck}` — one owner, no ambiguity, so
    the namespace would be noise. This is deliberate; don't "fix" it.
- **Flat lookups resolve only unambiguous matches**, and admin deck actions
  are keyed by deck row id, so topic/slug collisions across owners are
  harmless.

---

## Shared foundation

Everything else is edition-independent:

- **Markdown is the source of truth.** Decks are `.md` files under
  `UPLOAD_DIR`; the DB only indexes frontmatter, and card bodies are
  re-parsed from the file on read (`services/parser.py`, `indexing.py`).
  Portability, no lock-in, Git-friendly.
- **Auth** — three login methods, auto-detected from config (see the
  README's "Signing in"): magic links (Resend / SMTP / server-log
  delivery), per-account passwords, and the optional shared
  `SITE_PASSWORD` (most useful in standalone). JWT sessions throughout.
- **Authoring** — the deck builder (`/account/build`), markdown editor
  (`/account/edit`), and theme builder (`/account/theme`); see
  [`THEMING.md`](THEMING.md) for the theming contract.
- **Admin surface** — `/admin` for the owner and promoted admins
  (`users.is_admin`); the owner (`UPLOAD_OWNER_EMAIL`) holds admin rights
  by config fallback and is the only one who can promote/demote.
- **Layering** — thin routers → services → SQLAlchemy/Alembic; Astro SSR
  frontend; Caddy + systemd in production.

---

## Extensibility: the open-core seam

Limit and policy decisions live behind overridable functions and the
feature-flag seam, so a deployment can be extended **without forking**:
`backend/main.py` loads an optional `private` package if one is present on
the box and calls its `register(app)` hook. When the package is absent —
every clone of this repo — the deployment simply runs as plain open core.
This is the single extension point; nothing in the codebase depends on it
existing.

The per-deployment landing page works the same way: `index.astro` is
gitignored, so each instance ships its own front door (clones get the
config fallback redirect to `/decks`).

---

_Companion docs: [`SPEC.md`](../SPEC.md) (product spec),
[`THEMING.md`](THEMING.md) (theme creation), and the README for setup and
deployment._
