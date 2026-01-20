from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel, field_validator, ConfigDict
from nanomoni.crypto.certificates import load_private_key_from_pem
from cryptography.hazmat.primitives.asymmetric import ec


class Settings(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    database_url: str
    database_echo: bool

    api_host: str
    api_port: int
    api_debug: bool
    api_cors_origins: list[str]

    app_name: str
    app_version: str

    issuer_private_key_pem: str

    issuer_private_key: ec.EllipticCurvePrivateKey

    @field_validator("issuer_private_key_pem")
    @classmethod
    def validate_issuer_private_key_pem(cls, v: str) -> str:
        """Validate that the issuer private key is a valid PEM-encoded private key."""
        if not v:
            raise ValueError("Issuer private key cannot be empty")
        try:
            load_private_key_from_pem(v)
        except Exception as e:
            raise ValueError(f"Invalid issuer private key PEM: {e}") from e
        return v


@lru_cache()
def get_settings() -> Settings:
    database_echo_str = os.environ.get("ISSUER_DATABASE_ECHO")
    api_debug_str = os.environ.get("ISSUER_API_DEBUG")
    api_cors_origins_str = os.environ.get("ISSUER_API_CORS_ORIGINS")
    api_port_str = os.environ.get("ISSUER_API_PORT")

    database_url = os.environ.get("ISSUER_DATABASE_URL")
    if database_url is None:
        raise ValueError("ISSUER_DATABASE_URL is required")
    api_host = os.environ.get("ISSUER_API_HOST") or "0.0.0.0"
    api_port = int(api_port_str) if api_port_str is not None else 8000
    database_echo = (database_echo_str or "false").lower() == "true"
    api_debug = (api_debug_str or "false").lower() == "true"
    api_cors_origins = api_cors_origins_str.split(",") if api_cors_origins_str else []
    app_name = os.environ.get("ISSUER_APP_NAME") or "NanoMoni"
    app_version = os.environ.get("ISSUER_APP_VERSION") or "0.1.0"

    issuer_private_key_pem = os.environ.get("ISSUER_PRIVATE_KEY_PEM")
    if issuer_private_key_pem is None:
        raise ValueError("ISSUER_PRIVATE_KEY_PEM is required")

    return Settings(
        database_url=database_url,
        database_echo=database_echo,
        api_host=api_host,
        api_port=api_port,
        api_debug=api_debug,
        api_cors_origins=api_cors_origins,
        app_name=app_name,
        app_version=app_version,
        issuer_private_key_pem=issuer_private_key_pem,
        issuer_private_key=load_private_key_from_pem(issuer_private_key_pem),
    )
