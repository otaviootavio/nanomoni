from __future__ import annotations

import os

from pydantic import BaseModel


class Settings(BaseModel):
    """Typed application settings built from environment variables."""

    secret: str
    # Database settings
    database_url: str = "sqlite:///nanomoni.db"
    database_echo: bool = False

    # API settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_debug: bool = False
    api_cors_origins: list[str] = ["*"]

    # Application settings
    app_name: str = "NanoMoni"
    app_version: str = "1.0.0"


def get_settings() -> Settings:
    """Return typed settings instance sourced from env vars."""
    return Settings(
        secret=os.environ.get("SECRET", "your-secret-key-here"),
        database_url=os.environ.get("DATABASE_URL", "sqlite:///nanomoni.db"),
        database_echo=os.environ.get("DATABASE_ECHO", "false").lower() == "true",
        api_host=os.environ.get("API_HOST", "0.0.0.0"),
        api_port=int(os.environ.get("API_PORT", "8000")),
        api_debug=os.environ.get("API_DEBUG", "false").lower() == "true",
        api_cors_origins=os.environ.get("API_CORS_ORIGINS", "*").split(","),
        app_name=os.environ.get("APP_NAME", "NanoMoni"),
        app_version=os.environ.get("APP_VERSION", "1.0.0"),
    )
