"""Vibedeck FastAPI application entry point.

Run from this directory:
    uvicorn main:app --reload

Routers are mounted under /api so Caddy can split frontend (Astro SSR)
from backend traffic by path prefix. See Caddyfile.example.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from routers import admin, auth, decks, reports, themes, topics, users

app = FastAPI(
    title="Vibedeck API",
    version="0.1.0",
    description="Backend for the Vibedeck card-deck platform.",
)

# In dev, Astro runs on a separate origin; in prod they share a host via Caddy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.BASE_URL, "http://localhost:4321"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(topics.router, prefix="/api/topics", tags=["topics"])
app.include_router(decks.router, prefix="/api/decks", tags=["decks"])
app.include_router(themes.router, prefix="/api/themes", tags=["themes"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])

# Optional private add-on layer, kept out of this repo. If a `private` package
# is present on the box, give it a chance to register extra routes / overrides;
# open-core deployments simply run without it. This is the single extension
# seam — nothing here depends on it existing.
try:
    import private  # type: ignore
except ImportError:
    private = None
if private is not None and hasattr(private, "register"):
    private.register(app)


@app.get("/api/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "environment": settings.ENVIRONMENT}


@app.get("/api/meta", tags=["meta"])
def meta() -> dict[str, object]:
    """Non-secret deployment flags the frontend reads to adapt its UI.

    Lets Astro pages show/hide affordances (e.g. the sign-up surface) per
    edition without a rebuild. Safe to expose publicly — booleans only.
    """
    return {
        "edition": settings.EDITION.value,
        "allow_public_signup": settings.allow_public_signup,
        "allow_anon_read": settings.allow_anon_read,
        "moderation_enabled": settings.moderation_enabled,
        "visibility_enabled": settings.visibility_enabled,
        "quotas_enabled": settings.quotas_enabled,
        "user_spaces_enabled": settings.user_spaces_enabled,
    }
