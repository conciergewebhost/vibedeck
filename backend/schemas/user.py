"""User schemas (no password fields are ever serialised out)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    handle: str
    is_active: bool
    created_at: datetime
