from __future__ import annotations

import base64
import os
from typing import Optional

from pydantic import BaseModel, computed_field, field_validator
from cryptography.hazmat.primitives import serialization
from urllib.parse import urlparse


class Settings(BaseModel):
    client_private_key_pem: str
    vendor_base_url: str
    issuer_base_url: str
    client_payment_count: int = 1
    client_channel_amount: int = 1
    client_payment_mode: str = "signature"
    client_payword_unit_value: int = 1
    client_payword_max_k: Optional[int] = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def client_public_key_der_b64(self) -> str:
        """DER-encoded base64 public key."""
        private_key = serialization.load_pem_private_key(
            self.client_private_key_pem.encode(),
            password=None,
        )
        public_key = private_key.public_key()
        public_key_der = public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return base64.b64encode(public_key_der).decode("utf-8")

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
    client_private_key_pem = os.environ.get("CLIENT_PRIVATE_KEY_PEM")
    vendor_base_url = os.environ.get("VENDOR_BASE_URL")
    issuer_base_url = os.environ.get("ISSUER_BASE_URL")
    client_payment_count_str = os.environ.get("CLIENT_PAYMENT_COUNT")
    client_channel_amount_str = os.environ.get("CLIENT_CHANNEL_AMOUNT")
    client_payment_mode = (os.environ.get("CLIENT_PAYMENT_MODE") or "signature").lower()
    client_payword_unit_value_str = os.environ.get("CLIENT_PAYWORD_UNIT_VALUE")
    client_payword_max_k_str = os.environ.get("CLIENT_PAYWORD_MAX_K")
    if not (client_private_key_pem and vendor_base_url and issuer_base_url):
        raise ValueError(
            "CLIENT_PRIVATE_KEY_PEM, VENDOR_BASE_URL, and ISSUER_BASE_URL are required"
        )
    if client_payment_count_str is None or client_channel_amount_str is None:
        raise ValueError("CLIENT_PAYMENT_COUNT and CLIENT_CHANNEL_AMOUNT are required")

    try:
        client_payment_count = int(client_payment_count_str)
    except ValueError as e:
        raise ValueError(
            f"Invalid integer for CLIENT_PAYMENT_COUNT: {client_payment_count_str!r}"
        ) from e

    try:
        client_channel_amount = int(client_channel_amount_str)
    except ValueError as e:
        raise ValueError(
            f"Invalid integer for CLIENT_CHANNEL_AMOUNT: {client_channel_amount_str!r}"
        ) from e

    client_payword_unit_value_value = client_payword_unit_value_str or "1"
    try:
        client_payword_unit_value = int(client_payword_unit_value_value)
    except ValueError as e:
        raise ValueError(
            f"Invalid integer for CLIENT_PAYWORD_UNIT_VALUE: {client_payword_unit_value_value!r}"
        ) from e

    if client_payword_max_k_str:
        try:
            client_payword_max_k = int(client_payword_max_k_str)
        except ValueError as e:
            raise ValueError(
                f"Invalid integer for CLIENT_PAYWORD_MAX_K: {client_payword_max_k_str!r}"
            ) from e
    else:
        client_payword_max_k = None

    return Settings(
        client_private_key_pem=client_private_key_pem,
        vendor_base_url=vendor_base_url,
        issuer_base_url=issuer_base_url,
        client_payment_count=client_payment_count,
        client_channel_amount=client_channel_amount,
        client_payment_mode=client_payment_mode,
        client_payword_unit_value=client_payword_unit_value,
        client_payword_max_k=client_payword_max_k,
    )
