from __future__ import annotations

import os

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


def get_settings() -> Settings:
    database_echo_str = os.environ.get("ISSUER_DATABASE_ECHO")
    api_debug_str = os.environ.get("ISSUER_API_DEBUG")
    api_cors_origins_str = os.environ.get("ISSUER_API_CORS_ORIGINS")
    api_port_str = os.environ.get("ISSUER_API_PORT")

    return Settings(
        database_url=os.environ.get("ISSUER_DATABASE_URL"),
        database_echo=database_echo_str.lower() == "true"
        if database_echo_str is not None
        else None,
        api_host=os.environ.get("ISSUER_API_HOST"),
        api_port=int(api_port_str) if api_port_str is not None else None,
        api_debug=api_debug_str.lower() == "true"
        if api_debug_str is not None
        else None,
        api_cors_origins=api_cors_origins_str.split(",")
        if api_cors_origins_str is not None
        else None,
        app_name=os.environ.get("ISSUER_APP_NAME"),
        app_version=os.environ.get("ISSUER_APP_VERSION"),
        issuer_private_key_pem=os.environ.get("ISSUER_PRIVATE_KEY_PEM"),
        issuer_private_key=load_private_key_from_pem(
            os.environ.get("ISSUER_PRIVATE_KEY_PEM")
        ),
    )
