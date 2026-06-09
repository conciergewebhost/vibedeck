"""Reader-report API schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class ReportInput(BaseModel):
    """Body for POST /api/reports — a reader flagging a deck."""

    deck_id: int
    reason: Literal["spam", "harmful", "copyright", "other"]
    detail: str | None = Field(default=None, max_length=500)


class ReportAck(BaseModel):
    """Acknowledgement — deliberately reveals nothing about thresholds."""

    ok: bool = True
    message: str = "Thanks — our moderators will take a look."
