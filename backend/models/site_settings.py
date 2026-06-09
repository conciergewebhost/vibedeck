"""Site settings — a tiny runtime key-value store.

For instance-level knobs an admin changes from the web UI, where `.env`
(loaded once at process start) is the wrong home. Values are strings;
interpretation lives in services/site_settings.py. Keys today:

  require_invite_code — "true"/"false"; unset means required (the safe
      default and the pre-feature behavior)
  invite_code — runtime override of NEW_USER_CODE; unset/empty falls back
      to the .env value
"""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class SiteSetting(Base):
    __tablename__ = "site_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(500))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
