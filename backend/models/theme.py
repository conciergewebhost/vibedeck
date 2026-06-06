"""Theme model — a user-uploaded custom theme (private to its owner).

Unlike the built-in themes (CSS files bundled at build time under
frontend/src/styles/themes/), a user theme is stored here as raw CSS and
served at runtime from an auth-scoped endpoint, then injected client-side
only for the owner. A deck references a theme by its slug in frontmatter.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Theme(Base):
    __tablename__ = "themes"
    __table_args__ = (
        # A user can't have two themes with the same slug; different users can.
        UniqueConstraint("owner_id", "slug", name="uq_theme_owner_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    # Display name + URL/frontmatter identity (slugified from the name).
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(120), index=True)

    # The validated CSS source (no build step; served as-is to the owner).
    css: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["User"] = relationship(back_populates="themes")  # noqa: F821
