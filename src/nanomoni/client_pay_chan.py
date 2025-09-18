from __future__ import annotations

import base64
import json
from typing import Dict, Any

import httpx
from cryptography.hazmat.primitives import serialization

from nanomoni.envs.client_env import get_settings
from nanomoni.crypto.certificates import (
    generate_envelope,
    verify_envelope,
    load_public_key_from_der_b64,
    Envelope,
    sign_bytes,
)


def register_into_issuer_using_private_key(
    issuer_base_url: str, private_key_pem: str
) -> Dict[str, Any]:
    private_key = serialization.load_pem_private_key(
        private_key_pem.encode(), password=None
    )
    public_key = private_key.public_key()
    public_key_der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_key_der_b64 = base64.b64encode(public_key_der).decode("utf-8")

    print(f"Registering into issuer using public key: {public_key_der_b64}")

    with httpx.Client(timeout=10.0) as client:
        # 1) Register with issuer by sending public key
        reg_payload = {"client_public_key_der_b64": public_key_der_b64}
        try:
            r = client.post(f"{issuer_base_url}/issuer/register", json=reg_payload)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            if e.response is not None and e.response.status_code == 400:
                try:
                    detail = e.response.json().get("detail")
                except Exception:
                    detail = e.response.text
                if detail and "Account already registered" in str(detail):
                    print("User already registered; skipping registration.")
                    return {"status": "already_registered"}
            raise


def open_payment_channel(
    issuer_base_url: str,
    vendor_private_key_pem: str,
    client_private_key_pem: str,
    amount: int,
) -> tuple[str, str, int, int]:
    vendor_private_key = serialization.load_pem_private_key(
        vendor_private_key_pem.encode(), password=None
    )
    client_private_key = serialization.load_pem_private_key(
        client_private_key_pem.encode(), password=None
    )

    vendor_public_key = vendor_private_key.public_key()
    client_public_key = client_private_key.public_key()

    vendor_public_key_der = vendor_public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    client_public_key_der = client_public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    vendor_public_key_der_b64 = base64.b64encode(vendor_public_key_der).decode("utf-8")
    client_public_key_der_b64 = base64.b64encode(client_public_key_der).decode("utf-8")

    print(
        f"Opening payment channel using public keys: {vendor_public_key_der_b64} and {client_public_key_der_b64}"
    )

    # Build client-signed open envelope
    open_payload = {
        "vendor_public_key_der_b64": vendor_public_key_der_b64,
        "client_public_key_der_b64": client_public_key_der_b64,
        "amount": amount,
    }
    client_open_envelope = generate_envelope(client_private_key, open_payload)

    with httpx.Client(timeout=10.0) as client:
        r = client.post(
            f"{issuer_base_url}/issuer/payment-channel/open",
            json={
                "client_public_key_der_b64": client_public_key_der_b64,
                "open_payload_b64": client_open_envelope.payload_b64,
                "open_signature_b64": client_open_envelope.signature_b64,
            },
        )
        r.raise_for_status()
        data = r.json()

        # Fetch issuer public key to validate the issuer's envelope
        r_pk = client.get(f"{issuer_base_url}/issuer/public-key")
        r_pk.raise_for_status()
        issuer_public_key_der_b64 = r_pk.json()["der_b64"]
        issuer_public_key = load_public_key_from_der_b64(issuer_public_key_der_b64)

        # Verify and parse the issuer envelope
        issuer_envelope = Envelope(
            payload_b64=data["open_envelope_payload_b64"],
            signature_b64=data["open_envelope_signature_b64"],
        )
        verify_envelope(issuer_public_key, issuer_envelope)
        opened_payload_bytes = base64.b64decode(issuer_envelope.payload_b64)
        opened_payload = json.loads(opened_payload_bytes.decode("utf-8"))

        print(
            "Payment channel opened and issuer envelope verified:",
            opened_payload,
        )
        return (
            opened_payload["computed_id"],
            opened_payload["salt_b64"],
            opened_payload["amount"],
            opened_payload["balance"],
        )


def client_create_off_tx_to_vendor(
    computed_id: str,
    client_private_key_pem: str,
    owed_amount: int,
    client_public_key_der_b64: str,
    vendor_public_key_der_b64: str,
) -> tuple[str, str]:
    """Client creates an off-chain close request envelope for vendor.

    Payload fields: {"computed_id", "client_public_key_der_b64", "vendor_public_key_der_b64", "owed_amount"}
    Returns: (payload_b64, signature_b64)
    """
    client_private_key = serialization.load_pem_private_key(
        client_private_key_pem.encode(), password=None
    )
    payload = {
        "computed_id": computed_id,
        "client_public_key_der_b64": client_public_key_der_b64,
        "vendor_public_key_der_b64": vendor_public_key_der_b64,
        "owed_amount": owed_amount,
    }
    envelope = generate_envelope(client_private_key, payload)
    return envelope.payload_b64, envelope.signature_b64


def vendor_validate_client_off_tx(
    issuer_base_url: str,
    vendor_private_key_pem: str,
    client_public_key_der_b64: str,
    payload_b64: str,
    signature_b64: str,
) -> Dict[str, Any]:
    """Vendor validates client's off-chain payment envelope using client's public key.

    Returns the decoded payload dict on success.
    """
    client_public_key = load_public_key_from_der_b64(client_public_key_der_b64)
    envelope = Envelope(payload_b64=payload_b64, signature_b64=signature_b64)
    verify_envelope(client_public_key, envelope)
    payload = json.loads(base64.b64decode(payload_b64).decode("utf-8"))
    print("Validated client off-chain tx:", payload)
    return payload


def vendor_close_pay_chan_using_off_tx(
    issuer_base_url: str,
    computed_id: str,
    owed_amount: int,
    close_payload_b64: str,
    client_close_signature_b64: str,
    vendor_private_key_pem: str,
    client_public_key_der_b64: str,
    vendor_public_key_der_b64: str,
) -> Dict[str, Any]:
    """Vendor signs the client's close envelope payload and submits close request to issuer."""
    vendor_private_key = serialization.load_pem_private_key(
        vendor_private_key_pem.encode(), password=None
    )
    # Sign the exact payload bytes embedded in the client's envelope
    payload_bytes = base64.b64decode(close_payload_b64)
    vendor_close_signature_b64 = sign_bytes(vendor_private_key, payload_bytes)

    with httpx.Client(timeout=10.0) as client:
        r = client.post(
            f"{issuer_base_url}/issuer/payment-channel/close",
            json={
                "close_payload_b64": close_payload_b64,
                "client_close_signature_b64": client_close_signature_b64,
                "vendor_close_signature_b64": vendor_close_signature_b64,
                "client_public_key_der_b64": client_public_key_der_b64,
                "vendor_public_key_der_b64": vendor_public_key_der_b64,
            },
        )
        r.raise_for_status()
        data = r.json()
        print("Channel closed:", data)
        return data


def main() -> None:
    settings = get_settings()
    issuer_base_url = settings.issuer_base_url
    vendor_private_key_pem = settings.vendor_private_key_pem
    client_private_key_pem = settings.client_private_key_pem

    register_into_issuer_using_private_key(issuer_base_url, vendor_private_key_pem)
    register_into_issuer_using_private_key(issuer_base_url, client_private_key_pem)

    computed_id, salt_b64, amount, balance = open_payment_channel(
        issuer_base_url, vendor_private_key_pem, client_private_key_pem, 10
    )

    # Compute DER b64 public keys from PEMs for submission to close endpoint
    vendor_public_key_der_b64 = base64.b64encode(
        serialization.load_pem_private_key(
            vendor_private_key_pem.encode(), password=None
        )
        .public_key()
        .public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    ).decode("utf-8")
    client_public_key_der_b64 = base64.b64encode(
        serialization.load_pem_private_key(
            client_private_key_pem.encode(), password=None
        )
        .public_key()
        .public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    ).decode("utf-8")

    # 2) Client sends an off-chain payment to the vendor; vendor verifies it
    client_off_tx = client_create_off_tx_to_vendor(
        computed_id,
        client_private_key_pem,
        10,
        client_public_key_der_b64,
        vendor_public_key_der_b64,
    )
    vendor_validate_client_off_tx(
        issuer_base_url,
        vendor_private_key_pem,
        client_public_key_der_b64,
        client_off_tx[0],
        client_off_tx[1],
    )

    # 3) Vendor closes the channel using the client's off-chain certificate
    vendor_close_pay_chan_using_off_tx(
        issuer_base_url,
        computed_id,
        10,
        client_off_tx[0],
        client_off_tx[1],
        vendor_private_key_pem,
        client_public_key_der_b64,
        vendor_public_key_der_b64,
    )


if __name__ == "__main__":
    main()
