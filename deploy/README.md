# Deploying Vibedeck

Vibedeck runs as **two localhost services behind Caddy**:

- `vibedeck-api` — the FastAPI backend (uvicorn)
- `vibedeck-web` — the Astro SSR server (`node ./dist/server/entry.mjs`)

Caddy terminates TLS and reverse-proxies `/api/*` → backend and everything
else → frontend.

The files in this directory are **templates** — adapt the paths, ports, user,
domain, and the `node` binary location to your host before installing.

## Prerequisites

- The repo cloned on the server, a Python venv created, and
  `pip install -r requirements.txt` done (see the root [README](../README.md)).
- PostgreSQL reachable (Docker or system), and the schema applied:
  `alembic upgrade head`.
- `.env` populated with **production** values — at minimum:
  - `ENVIRONMENT=production`
  - `BASE_URL=https://your-domain` (also used for the API's CORS allow-list)
- Caddy installed and running.

## 1. Build the frontend

```bash
cd frontend
npm install
npm run build      # produces dist/server/entry.mjs
```

## 2. Install the systemd units

Edit both unit files first:

- `vibedeck-api.service` — `WorkingDirectory`, the `ExecStart` venv path, the
  `--port`, and `User`.
- `vibedeck-web.service` — `WorkingDirectory`, `ExecStart` **absolute `node`
  path** (find it with `which node` — systemd has no shell `PATH`), the
  `PORT`, and `API_BASE_URL` (point it at the backend, e.g.
  `http://127.0.0.1:8100`).

```bash
sudo cp deploy/systemd/vibedeck-api.service deploy/systemd/vibedeck-web.service \
        /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vibedeck-api.service vibedeck-web.service
systemctl status vibedeck-api vibedeck-web --no-pager
```

The backend reads `.env` itself, so no `EnvironmentFile=` is needed. Both units
use `Restart=always`.

### Daily moderation digest (server edition only)

The `server` edition emails the admin a daily moderation digest (review-queue
size + last-24h block/flag counts; see `backend/jobs/daily_digest.py`). It is
a oneshot service fired by a systemd timer. Edit `vibedeck-digest.service`
(`WorkingDirectory`, venv path, `User`) and `vibedeck-digest.timer`
(`OnCalendar` if 08:00 server time isn't what you want), then:

```bash
sudo cp deploy/systemd/vibedeck-digest.service deploy/systemd/vibedeck-digest.timer \
        /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vibedeck-digest.timer
systemctl list-timers vibedeck-digest.timer --no-pager   # confirm next run
```

Test a send immediately with `sudo systemctl start vibedeck-digest.service`
(or run `python -m jobs.daily_digest` from `backend/`). The recipient is
`ADMIN_DIGEST_EMAIL` from `.env`, falling back to `UPLOAD_OWNER_EMAIL`.
A standalone-edition instance exits without sending, so the units are safe to
install everywhere.

## 3. Configure Caddy

Adapt `deploy/caddy/vibedeck.online.caddy` (your domain + the two ports), then
add it to your Caddyfile (paste the block or `import` it), and reload:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo systemctl reload caddy
```

## 4. Verify

```bash
curl -s https://your-domain/api/health      # {"status":"ok","environment":"production"}
curl -sI https://your-domain/               # 200, HTML
```

## Updating

```bash
git pull
cd frontend && npm install && npm run build
cd .. && alembic upgrade head               # if there are new migrations
sudo systemctl restart vibedeck-api vibedeck-web
```

### Upgrading across the per-user-spaces migration

The `add_user_handles_and_topic_owners` migration gives every existing user a
**handle** derived from their email local-part (e.g. `alice@example.com` →
`alice`; numeric suffix on collision). Note for standalone instances: the
handle appears on the (unlinked) `/u/{handle}` author page, so the email
local-part becomes technically public — pick a different handle at account
creation (`manage.py create-user --handle`) if that matters to you. Existing
deck files are NOT moved; new decks are written under per-owner
subdirectories, and `python manage.py tidy` (from `backend/`) optionally
moves legacy flat files to match. URLs only change in the `server` edition
(`/u/{handle}/…`, with 301s from the old flat URLs).

## Managing content

Decks are managed from the server (see the root README): drop a `.md` file in
`decks/` and run `python manage.py reindex` from `backend/`, or upload via the
auth-gated `/admin` surface. Other commands: `list-decks`, `delete-deck`,
`create-user`, `delete-user`.
