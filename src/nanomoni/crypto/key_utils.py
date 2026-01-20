from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization


def compute_public_key_der_b64_from_private_pem(private_key_pem: str) -> str:
    private_key = serialization.load_pem_private_key(
        private_key_pem.encode(),
        password=None,
    )
    public_key = private_key.public_key()
    public_key_der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return base64.b64encode(public_key_der).decode("utf-8")
