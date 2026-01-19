from __future__ import annotations

import os
import base64

from pydantic import BaseModel, field_validator
from cryptography.hazmat.primitives import serialization

from nanomoni.application.issuer.dtos import RegistrationRequestDTO
from nanomoni.infrastructure.http.http_client import HttpRequestError, HttpResponseError
from nanomoni.infrastructure.issuer.issuer_client import AsyncIssuerClient


class Settings(BaseModel):
    database_url: str
    database_echo: bool

    api_host: str
    api_port: int
    api_debug: bool
    api_workers: int
    api_cors_origins: list[str]

    app_name: str
    app_version: str

    issuer_base_url: str
    vendor_private_key_pem: str
    vendor_public_key_pem: str
    vendor_public_key_der_b64: str

    @field_validator("vendor_private_key_pem")
    @classmethod
    def validate_vendor_private_key_pem(cls, v: str) -> str:
        if not v:
            raise ValueError("Vendor private key cannot be empty")
        try:
            serialization.load_pem_private_key(
                v.encode(),
                password=None,
            )
        except Exception as e:
            raise ValueError(f"Invalid vendor private key PEM: {e}") from e
        return v


async def register_vendor_with_issuer(settings: Settings) -> None:
    """Register the vendor with the issuer using its public key."""
    if not settings.issuer_base_url or not settings.vendor_private_key_pem:
        print(
            "Skipping vendor registration with issuer: "
            "issuer_base_url or vendor_private_key_pem not set."
        )
        return

    print("Registering vendor into issuer using public key.")

    try:
        reg_dto = RegistrationRequestDTO(
            client_public_key_der_b64=settings.vendor_public_key_der_b64
        )
        async with AsyncIssuerClient(settings.issuer_base_url) as issuer_client:
            await issuer_client.register(reg_dto)
            print("Vendor registered with issuer successfully.")
    except HttpResponseError as e:
        if e.response.status_code == 400:
            try:
                body = e.response.json() or {}
                detail = body.get("detail")
            except Exception:
                detail = e.response.text
            if detail and "Account already registered" in str(detail):
                print("Vendor already registered; skipping registration.")
                return
        print(f"Error registering vendor with issuer: {e}")
    except HttpRequestError as e:
        print(
            f"Could not connect to issuer at {settings.issuer_base_url} to register vendor: {e}"
        )
    except Exception as e:
        print(f"An unexpected error occurred during vendor registration: {e}")


def get_settings() -> Settings:
    database_echo_str = os.environ.get("VENDOR_DATABASE_ECHO")
    api_debug_str = os.environ.get("VENDOR_API_DEBUG")
    api_cors_origins_str = os.environ.get("VENDOR_API_CORS_ORIGINS")
    api_port_str = os.environ.get("VENDOR_API_PORT")
    api_workers_str = os.environ.get("VENDOR_API_WORKERS")

    vendor_private_key_pem = os.environ.get("VENDOR_PRIVATE_KEY_PEM")
    issuer_base_url = os.environ.get("ISSUER_BASE_URL")

    database_url = os.environ.get("VENDOR_DATABASE_URL")
    if database_url is None:
        raise ValueError("VENDOR_DATABASE_URL is required")

    api_host = os.environ.get("VENDOR_API_HOST") or "0.0.0.0"
    api_port = int(api_port_str) if api_port_str is not None else 8001
    database_echo = (database_echo_str or "false").lower() == "true"
    api_debug = (api_debug_str or "false").lower() == "true"
    api_workers = int(api_workers_str) if api_workers_str is not None else 1
    api_cors_origins = api_cors_origins_str.split(",") if api_cors_origins_str else []

    app_name = os.environ.get("VENDOR_APP_NAME") or "NanoMoni"
    app_version = os.environ.get("VENDOR_APP_VERSION") or "0.1.0"

    if issuer_base_url is None:
        raise ValueError("ISSUER_BASE_URL is required")
    if vendor_private_key_pem is None:
        raise ValueError("VENDOR_PRIVATE_KEY_PEM is required")

    private_key = serialization.load_pem_private_key(
        vendor_private_key_pem.encode(),
        password=None,
    )
    public_key = private_key.public_key()
    vendor_public_key_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    vendor_public_key_der_b64 = base64.b64encode(
        public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    ).decode("utf-8")

    return Settings(
        database_url=database_url,
        database_echo=database_echo,
        api_host=api_host,
        api_port=api_port,
        api_debug=api_debug,
        api_workers=api_workers,
        api_cors_origins=api_cors_origins,
        app_name=app_name,
        app_version=app_version,
        issuer_base_url=issuer_base_url,
        vendor_private_key_pem=vendor_private_key_pem,
        vendor_public_key_pem=vendor_public_key_pem,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
    )
