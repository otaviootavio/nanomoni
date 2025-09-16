from __future__ import annotations

import os

from pydantic import BaseModel, field_validator
from cryptography.hazmat.primitives import serialization
from urllib.parse import urlparse


class Settings(BaseModel):
    client_private_key_pem: str
    vendor_private_key_pem: str
    vendor_base_url: str
    issuer_base_url: str

    @field_validator("client_private_key_pem")
    @classmethod
    def validate_client_private_key_pem(cls, v: str) -> str:
        """Validate that the client private key is a valid PEM-encoded private key."""
        if not v:
            raise ValueError("Client private key cannot be empty")
        try:
            serialization.load_pem_private_key(
                v.encode(),
                password=None,
            )
        except Exception as e:
            raise ValueError(f"Invalid client private key PEM: {e}") from e
        return v

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

    @field_validator("vendor_base_url")
    @classmethod
    def validate_vendor_base_url(cls, v: str) -> str:
        if not v:
            raise ValueError("Vendor base URL cannot be empty")
        parsed = urlparse(v)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Vendor base URL must start with http:// or https://")
        if not parsed.netloc:
            raise ValueError("Vendor base URL must include a host")
        return v

    @field_validator("issuer_base_url")
    @classmethod
    def validate_issuer_base_url(cls, v: str) -> str:
        if not v:
            raise ValueError("Issuer base URL cannot be empty")
        parsed = urlparse(v)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Issuer base URL must start with http:// or https://")
        if not parsed.netloc:
            raise ValueError("Issuer base URL must include a host")
        return v


def get_settings() -> Settings:
    return Settings(
        client_private_key_pem=os.environ.get("CLIENT_PRIVATE_KEY_PEM"),
        vendor_private_key_pem=os.environ.get("VENDOR_PRIVATE_KEY_PEM"),
        vendor_base_url=os.environ.get("VENDOR_BASE_URL"),
        issuer_base_url=os.environ.get("ISSUER_BASE_URL"),
    )
