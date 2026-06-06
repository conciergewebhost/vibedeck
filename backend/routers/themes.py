"""Themes router — per-user custom themes (private to the owner).

Themes are uploaded as CSS, validated (the safe-CSS rule), and served back
only to their owner for client-side injection into the reader. A deck opts
into a theme by putting its slug in the deck's `theme:` frontmatter.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from database import get_db
from models import User
from schemas.theme import ThemeInput, ThemeItem
from services import themes as themes_service
from services.auth import get_current_user
from services.themes import ThemeConflict, ThemeInvalid

router = APIRouter()


def _item(theme) -> ThemeItem:
    return ThemeItem(
        name=theme.name,
        slug=theme.slug,
        created_at=theme.created_at,
        updated_at=theme.updated_at,
    )


@router.post("", response_model=ThemeItem, status_code=status.HTTP_201_CREATED)
def create_theme(
    body: ThemeInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ThemeItem:
    """Validate and store a new theme owned by the current user."""
    try:
        theme = themes_service.create_user_theme(
            db, current_user.id, body.name, body.css
        )
    except ThemeInvalid as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except ThemeConflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a theme with that name.",
        )
    db.commit()
    db.refresh(theme)
    return _item(theme)


@router.get("/mine", response_model=list[ThemeItem])
def list_my_themes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ThemeItem]:
    """List the current user's themes (no CSS body)."""
    return [_item(t) for t in themes_service.list_user_themes(db, current_user.id)]


@router.get("/mine/{slug}.css", response_class=PlainTextResponse)
def get_my_theme_css(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Return an owned theme's CSS (for client-side injection)."""
    css = themes_service.get_user_theme_css(db, current_user.id, slug)
    if css is None:
        raise HTTPException(status_code=404, detail="Theme not found")
    return PlainTextResponse(css, media_type="text/css")


@router.delete("/mine/{slug}", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_theme(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Delete an owned theme."""
    deleted = themes_service.delete_user_theme(db, current_user.id, slug)
    if not deleted:
        raise HTTPException(status_code=404, detail="Theme not found")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
