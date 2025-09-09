from __future__ import annotations

import os

from pydantic import BaseModel, field_validator
from cryptography.hazmat.primitives import serialization


class Settings(BaseModel):
    client_private_key_pem: str

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


def get_settings() -> Settings:
    return Settings(
        client_private_key_pem=os.environ.get("CLIENT_PRIVATE_KEY_PEM"),
    )
