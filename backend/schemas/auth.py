"""Auth schemas."""

from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UploadTokenRequest(BaseModel):
    """Body for the shared-token web gate (POST /api/auth/upload-token)."""

    token: str
