"""Theme API schemas."""

from datetime import datetime

from pydantic import BaseModel


class ThemeInput(BaseModel):
    """Body for creating a theme (POST /api/themes)."""

    name: str
    css: str


class ThemeItem(BaseModel):
    """A theme as listed in the portal (no CSS body)."""

    name: str
    slug: str
    created_at: datetime
    updated_at: datetime
