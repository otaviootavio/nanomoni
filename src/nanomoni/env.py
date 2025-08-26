from __future__ import annotations

import os

from pydantic import BaseModel

class Settings(BaseModel):
    """Typed application settings built from environment variables."""

    secret: str

def get_settings() -> Settings:
    """Return typed settings instance sourced from env vars."""
    return Settings(
        secret=os.environ.get("SECRET"),
    ) 