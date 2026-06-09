"""add_user_handles_and_topic_owners

Per-user spaces: every user gets a public handle (the /u/{handle} URL
segment) and topics become owner-scoped (unique per owner, not globally).

Data backfill, in order:
  1. users.handle — derived from the email local-part, '-2'/'-3'… suffix on
     collision with existing or reserved handles (oldest account wins the
     bare name). Mirrors services/handles.derive_handle — keep in sync.
  2. topics.owner_id — each topic is assigned to the owner of its earliest
     deck; if decks from OTHER owners share the topic, the topic row is
     duplicated per extra owner and those decks repointed (the split).
     Topics with no decks are deleted (they are unreachable; matches
     _prune_empty_topic semantics).
  3. Constraint swap: global unique topics.slug → non-unique index +
     UNIQUE (owner_id, slug).

Deck files are NOT moved — decks.filename is an opaque relative path under
UPLOAD_DIR; legacy flat names stay valid and migrate lazily on edit (or via
`manage.py tidy`). The column is widened for the new `{handle}/…` paths.

Revision ID: 3fc43e0c2d38
Revises: 1d6992afeaad
Create Date: 2026-06-09 14:26:21.650719
"""
import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3fc43e0c2d38'
down_revision: Union[str, None] = '1d6992afeaad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Inline copies of services/handles rules — migrations must not import app
# code (it changes underneath old revisions). Keep in sync with
# services/handles.py.
_RESERVED_HANDLES = frozenset(
    {
        "about", "account", "admin", "api", "assets", "auth", "decks",
        "embed", "favicon", "health", "help", "index", "login", "logout",
        "me", "meta", "mine", "preview", "privacy", "public", "robots",
        "rss", "sandbox", "search", "settings", "signup", "sitemap",
        "static", "support", "terms", "themes", "topics", "u", "upload",
        "users", "vibedeck", "well-known",
    }
)
_HANDLE_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1. users.handle ────────────────────────────────────────────────
    op.add_column('users', sa.Column('handle', sa.String(length=64), nullable=True))

    users = bind.execute(
        sa.text("SELECT id, email FROM users ORDER BY id")
    ).all()
    taken: set[str] = set(_RESERVED_HANDLES)
    for user_id, email in users:
        base = _slugify(email.split("@", 1)[0])[:60] or "user"
        if not _HANDLE_RE.match(base):
            base = "user"
        candidate, n = base, 2
        while candidate in taken:
            candidate = f"{base}-{n}"
            n += 1
        taken.add(candidate)
        bind.execute(
            sa.text("UPDATE users SET handle = :h WHERE id = :id"),
            {"h": candidate, "id": user_id},
        )

    op.alter_column('users', 'handle', nullable=False)
    op.create_index(op.f('ix_users_handle'), 'users', ['handle'], unique=True)

    # ── 2. topics.owner_id + the per-owner split ───────────────────────
    op.add_column('topics', sa.Column('owner_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_topics_owner_id_users', 'topics', 'users', ['owner_id'], ['id']
    )

    topics = bind.execute(sa.text("SELECT id FROM topics ORDER BY id")).all()
    for (topic_id,) in topics:
        owners = bind.execute(
            sa.text(
                "SELECT owner_id, MIN(created_at) AS first_deck "
                "FROM decks WHERE topic_id = :t "
                "GROUP BY owner_id ORDER BY first_deck, owner_id"
            ),
            {"t": topic_id},
        ).all()

        if not owners:  # empty topic: unreachable, mirror _prune_empty_topic
            bind.execute(
                sa.text("DELETE FROM topics WHERE id = :t"), {"t": topic_id}
            )
            continue

        # Earliest-deck owner keeps the original row (stable topic ids for
        # the common single-owner case).
        bind.execute(
            sa.text("UPDATE topics SET owner_id = :o WHERE id = :t"),
            {"o": owners[0][0], "t": topic_id},
        )

        # Every other owner gets a duplicated topic row; their decks move.
        for owner_id, _ in owners[1:]:
            new_id = bind.execute(
                sa.text(
                    "INSERT INTO topics "
                    "(slug, display_name, description, theme, created_at, owner_id) "
                    "SELECT slug, display_name, description, theme, created_at, :o "
                    "FROM topics WHERE id = :t RETURNING id"
                ),
                {"o": owner_id, "t": topic_id},
            ).scalar_one()
            bind.execute(
                sa.text(
                    "UPDATE decks SET topic_id = :new WHERE topic_id = :t "
                    "AND owner_id = :o"
                ),
                {"new": new_id, "t": topic_id, "o": owner_id},
            )

    op.alter_column('topics', 'owner_id', nullable=False)

    # ── 3. constraint swap: global slug unique → per-owner unique ──────
    op.drop_index(op.f('ix_topics_slug'), table_name='topics')
    op.create_index(op.f('ix_topics_slug'), 'topics', ['slug'], unique=False)
    op.create_unique_constraint(
        'uq_topics_owner_slug', 'topics', ['owner_id', 'slug']
    )

    # ── 4. room for {handle}/… relative paths ──────────────────────────
    op.alter_column(
        'decks', 'filename',
        existing_type=sa.String(length=300),
        type_=sa.String(length=512),
    )


def downgrade() -> None:
    """Best-effort. Restoring the global topics.slug unique index FAILS if
    split topics exist (two owners sharing a slug) — resolve duplicates by
    hand first. Handles are simply dropped."""
    op.alter_column(
        'decks', 'filename',
        existing_type=sa.String(length=512),
        type_=sa.String(length=300),
    )
    op.drop_constraint('uq_topics_owner_slug', 'topics', type_='unique')
    op.drop_index(op.f('ix_topics_slug'), table_name='topics')
    op.create_index(op.f('ix_topics_slug'), 'topics', ['slug'], unique=True)
    op.drop_constraint('fk_topics_owner_id_users', 'topics', type_='foreignkey')
    op.drop_column('topics', 'owner_id')
    op.drop_index(op.f('ix_users_handle'), table_name='users')
    op.drop_column('users', 'handle')
