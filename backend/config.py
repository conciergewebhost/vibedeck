"""Application settings, loaded from environment / .env.

Uses pydantic-settings so every value is typed and validated at startup.
Run the backend from the backend/ directory so the import paths below
(`from config import settings`) resolve as flat modules.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # .env lives at the repo root, one level above backend/.
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str
    SECRET_KEY: str
    UPLOAD_DIR: Path
    BASE_URL: str = "http://localhost:4321"
    ENVIRONMENT: str = "development"

    # JWT defaults — not in .env yet; promote to env vars if they need tuning.
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


# Single import-time instance; FastAPI dependencies read from this.
settings = Settings()  # type: ignore[call-arg]
