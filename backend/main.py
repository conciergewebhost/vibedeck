"""Vibedeck FastAPI application entry point.

Run from this directory:
    uvicorn main:app --reload

Routers are mounted under /api so Caddy can split frontend (Astro SSR)
from backend traffic by path prefix. See Caddyfile.example.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from routers import auth, decks, themes, topics, users

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


@app.get("/api/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "environment": settings.ENVIRONMENT}
