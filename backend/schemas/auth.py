"""Auth schemas."""

from pydantic import BaseModel, EmailStr


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UploadTokenRequest(BaseModel):
    """Body for the shared-token web gate (POST /api/auth/upload-token)."""

    token: str


class RequestLinkInput(BaseModel):
    """Body for POST /api/auth/request-link.

    `code` is only required to create a new account (testing-phase invite
    gate); existing users may omit it.
    """

    email: EmailStr
    code: str | None = None


class VerifyInput(BaseModel):
    """Body for POST /api/auth/verify — the token from the emailed link."""

    token: str


class MessageOut(BaseModel):
    """Generic acknowledgement for fire-and-forget actions (e.g. link sent)."""

    ok: bool = True
    message: str
