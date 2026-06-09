"""Admin router — owner-only user monitoring (mounted at /api/admin).

Deck management (list all / delete any / upload) lives on the decks router,
gated by the same get_current_admin dependency.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from database import get_db
from models import User
from schemas.admin import (
    AdminUserItem,
    ModerationSummary,
    ReportedDeckItem,
    SignupSettings,
    SignupSettingsInput,
)
from schemas.deck import AdminDeckItem
from services import admin as admin_service
from services import decks as decks_service
from services import reports as reports_service
from services import site_settings
from services.admin import RoleChangeForbidden
from services.auth import get_current_admin, get_current_owner

router = APIRouter()


@router.get("/users", response_model=list[AdminUserItem])
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> list[AdminUserItem]:
    """All users (most recent first) with deck count, created/last-login/last-deck dates."""
    return admin_service.list_users(db)


@router.get("/users/{user_id}/decks", response_model=list[AdminDeckItem])
def list_user_decks(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> list[AdminDeckItem]:
    """Decks owned by a given user — for the admin per-user view."""
    return decks_service.list_user_decks(db, user_id)


# Ban / reactivate: admins may ban regular users; only the owner may ban
# (or reactivate) admins; the owner and one's own account are untouchable.


@router.post("/users/{user_id}/deactivate", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> Response:
    """Ban a user: login refused and all their public content hidden
    (read-time filter — nothing is deleted; reactivation restores it)."""
    return _set_active(db, admin, user_id, False)


@router.post("/users/{user_id}/reactivate", status_code=status.HTTP_204_NO_CONTENT)
def reactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> Response:
    """Lift a ban — the user's content reappears immediately."""
    return _set_active(db, admin, user_id, True)


def _set_active(db: Session, actor: User, user_id: int, value: bool) -> Response:
    try:
        if not admin_service.set_active(db, actor, user_id, value):
            raise HTTPException(status_code=404, detail="User not found")
    except admin_service.BanForbidden as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Role management is OWNER-only: admins must not be able to mint or remove
# other admins. The owner account itself is admin by config (see
# services.auth.get_current_admin) and its flag can't be changed here.


@router.post("/users/{user_id}/promote", status_code=status.HTTP_204_NO_CONTENT)
def promote_user(
    user_id: int,
    db: Session = Depends(get_db),
    owner: User = Depends(get_current_owner),
) -> Response:
    """Grant a user the admin surface (idempotent)."""
    return _set_admin(db, user_id, True)


@router.post("/users/{user_id}/demote", status_code=status.HTTP_204_NO_CONTENT)
def demote_user(
    user_id: int,
    db: Session = Depends(get_db),
    owner: User = Depends(get_current_owner),
) -> Response:
    """Revoke a user's admin rights (idempotent; effective immediately)."""
    return _set_admin(db, user_id, False)


def _set_admin(db: Session, user_id: int, value: bool) -> Response:
    try:
        if not admin_service.set_admin(db, user_id, value):
            raise HTTPException(status_code=404, detail="User not found")
    except RoleChangeForbidden:
        raise HTTPException(
            status_code=400,
            detail="The owner account is always an admin; its role can't change.",
        )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/flagged", response_model=list[AdminDeckItem])
def list_flagged(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> list[AdminDeckItem]:
    """The moderation review queue: quarantined decks, oldest flag first."""
    return decks_service.list_flagged_decks(db)


# Admin deck actions key on the deck row id — collision-proof under
# per-user spaces (flat topic/deck slugs can be ambiguous across owners),
# and the admin UI already holds full deck objects from the list endpoints.


@router.post("/decks/{deck_id}/approve", status_code=status.HTTP_204_NO_CONTENT)
def approve_deck(
    deck_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> Response:
    """Approve a flagged deck — it becomes visible per its visibility setting.

    Also clears any standing reader reports: a human ruling supersedes the
    complaints (else the standing count would re-quarantine on the next
    report). Rejecting a deck is DELETE /api/admin/decks/{deck_id}.
    """
    if not decks_service.approve_deck_by_id(db, deck_id):
        raise HTTPException(status_code=404, detail="Deck not found")
    reports_service.clear_reports(db, deck_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/reports", response_model=list[ReportedDeckItem])
def list_reports(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> list[ReportedDeckItem]:
    """Reader reports grouped per deck, most recently reported first."""
    return admin_service.list_reported_decks(db)


@router.delete("/decks/{deck_id}/reports", status_code=status.HTTP_204_NO_CONTENT)
def dismiss_reports(
    deck_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> Response:
    """Dismiss all standing reports against a deck (the content stays as-is)."""
    reports_service.clear_reports(db, deck_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/decks/{deck_id}/source")
def get_deck_source(
    deck_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> Response:
    """Raw markdown of any deck — for reviewing quarantined content."""
    markdown = decks_service.get_deck_source_by_id(db, deck_id)
    if markdown is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    return Response(content=markdown, media_type="text/markdown")


@router.delete("/decks/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deck(
    deck_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> Response:
    """Delete any deck: file + DB rows + orphan prune (admin only)."""
    if not decks_service.delete_deck_by_id(db, deck_id):
        raise HTTPException(status_code=404, detail="Deck not found")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# The signup gate is owner-only, like role management: it's instance policy.


@router.get("/signup-settings", response_model=SignupSettings)
def get_signup_settings(
    db: Session = Depends(get_db),
    owner: User = Depends(get_current_owner),
) -> SignupSettings:
    """Current signup-gate state, including the effective invite code."""
    return SignupSettings(
        require_code=site_settings.invite_code_required(db),
        code=site_settings.invite_code(db),
    )


@router.put("/signup-settings", response_model=SignupSettings)
def update_signup_settings(
    body: SignupSettingsInput,
    db: Session = Depends(get_db),
    owner: User = Depends(get_current_owner),
) -> SignupSettings:
    """Toggle whether signups need an invite code and/or change the code.

    Takes effect immediately (no restart — the auth flow reads the runtime
    store per request). A blank `code` leaves the current code unchanged.
    """
    code = (body.code or "").strip()
    if code and len(code) < 4:
        raise HTTPException(
            status_code=400,
            detail="The invite code must be at least 4 characters.",
        )
    site_settings.set_setting(
        db, site_settings.REQUIRE_INVITE_CODE, "true" if body.require_code else "false"
    )
    if code:
        site_settings.set_setting(db, site_settings.INVITE_CODE, code)
    db.commit()
    return SignupSettings(
        require_code=site_settings.invite_code_required(db),
        code=site_settings.invite_code(db),
    )


@router.get("/moderation-summary", response_model=ModerationSummary)
def moderation_summary(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> ModerationSummary:
    """Queue size + last-24h block/flag counts (also used by the digest)."""
    return admin_service.moderation_summary(db)
