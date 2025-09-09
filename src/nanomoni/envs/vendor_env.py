from __future__ import annotations

import os

from pydantic import BaseModel


class Settings(BaseModel):
    database_url: str
    database_echo: bool

    api_host: str
    api_port: int
    api_debug: bool
    api_cors_origins: list[str]

    app_name: str
    app_version: str

    issuer_base_url: str


def get_settings() -> Settings:
    database_echo_str = os.environ.get("VENDOR_DATABASE_ECHO")
    api_debug_str = os.environ.get("VENDOR_API_DEBUG")
    api_cors_origins_str = os.environ.get("VENDOR_API_CORS_ORIGINS")
    api_port_str = os.environ.get("VENDOR_API_PORT")

    return Settings(
        database_url=os.environ.get("VENDOR_DATABASE_URL"),
        database_echo=database_echo_str.lower() == "true"
        if database_echo_str is not None
        else None,
        api_host=os.environ.get("VENDOR_API_HOST"),
        api_port=int(api_port_str) if api_port_str is not None else None,
        api_debug=api_debug_str.lower() == "true"
        if api_debug_str is not None
        else None,
        api_cors_origins=api_cors_origins_str.split(",")
        if api_cors_origins_str is not None
        else None,
        app_name=os.environ.get("VENDOR_APP_NAME"),
        app_version=os.environ.get("VENDOR_APP_VERSION"),
        issuer_base_url=os.environ.get("ISSUER_BASE_URL"),
    )
