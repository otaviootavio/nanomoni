from __future__ import annotations

from pydantic import BaseModel

from ...crypto.certificates import json_to_bytes


def payload_to_bytes(payload: BaseModel) -> bytes:
    """Canonical bytes for signing/verifying Pydantic payloads.

    Centralizes the "model_dump() -> json bytes" convention so Vendor and Issuer
    never diverge in how they serialize the exact message being signed.
    """

    return json_to_bytes(payload.model_dump())
