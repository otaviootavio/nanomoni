from __future__ import annotations

import os
import base64
import httpx

from pydantic import BaseModel, field_validator
from cryptography.hazmat.primitives import serialization


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


def _register_vendor_with_issuer(
    issuer_base_url: str, vendor_private_key_pem: str
) -> None:
    if not issuer_base_url or not vendor_private_key_pem:
        print(
            "Skipping vendor registration with issuer: "
            "issuer_base_url or vendor_private_key_pem not set."
        )
        return

    private_key = serialization.load_pem_private_key(
        vendor_private_key_pem.encode(), password=None
    )
    public_key = private_key.public_key()
    public_key_der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_key_der_b64 = base64.b64encode(public_key_der).decode("utf-8")

    print("Registering vendor into issuer using public key.")

    try:
        with httpx.Client(timeout=10.0) as client:
            reg_payload = {"client_public_key_der_b64": public_key_der_b64}
            r = client.post(f"{issuer_base_url}/issuer/register", json=reg_payload)
            r.raise_for_status()
            print("Vendor registered with issuer successfully.")
    except httpx.HTTPStatusError as e:
        if e.response is not None and e.response.status_code == 400:
            try:
                detail = e.response.json().get("detail")
            except Exception:
                detail = e.response.text
            if detail and "Account already registered" in str(detail):
                print("Vendor already registered; skipping registration.")
                return
        print(f"Error registering vendor with issuer: {e}")
    except httpx.RequestError as e:
        print(
            f"Could not connect to issuer at {issuer_base_url} to register vendor: {e}"
        )
    except Exception as e:
        print(f"An unexpected error occurred during vendor registration: {e}")


def get_settings() -> Settings:
    database_echo_str = os.environ.get("VENDOR_DATABASE_ECHO")
    api_debug_str = os.environ.get("VENDOR_API_DEBUG")
    api_cors_origins_str = os.environ.get("VENDOR_API_CORS_ORIGINS")
    api_port_str = os.environ.get("VENDOR_API_PORT")

    vendor_private_key_pem = os.environ.get("VENDOR_PRIVATE_KEY_PEM")
    issuer_base_url = os.environ.get("ISSUER_BASE_URL")

    _register_vendor_with_issuer(issuer_base_url, vendor_private_key_pem)

    vendor_public_key_pem = None
    if vendor_private_key_pem:
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
        issuer_base_url=issuer_base_url,
        vendor_private_key_pem=vendor_private_key_pem,
        vendor_public_key_pem=vendor_public_key_pem,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
    )
