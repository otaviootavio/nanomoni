from __future__ import annotations

import base64
import json
from typing import Dict, Any

import httpx
from cryptography.hazmat.primitives import serialization

from nanomoni.envs.client_env import get_settings
from nanomoni.crypto.certificates import (
    sign_bytes,
    canonicalize_json,
    issuer_verify_paychan_certificate_envelope,
    load_public_key_der_b64,
    issue_payload_envelope,
    verify_payload_envelope,
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
        # 1) Start registration: send our public key
        start_payload = {"client_public_key_der_b64": public_key_der_b64}
        r = client.post(
            f"{issuer_base_url}/issuer/registration/start", json=start_payload
        )
        r.raise_for_status()
        start_data = r.json()
        challenge_id = start_data["challenge_id"]
        nonce_b64 = start_data["nonce_b64"]

        # 2) Solve challenge: sign the nonce and complete registration
        nonce_bytes = base64.b64decode(nonce_b64)
        signature_der_b64 = sign_bytes(private_key, nonce_bytes)
        complete_payload = {
            "challenge_id": challenge_id,
            "signature_der_b64": signature_der_b64,
        }
        try:
            r2 = client.post(
                f"{issuer_base_url}/issuer/registration/complete", json=complete_payload
            )
            r2.raise_for_status()
            return r2.json()
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

    open_payload = {
        "vendor_public_key_der_b64": vendor_public_key_der_b64,
        "client_public_key_der_b64": client_public_key_der_b64,
        "amount": amount,
    }
    message_bytes = canonicalize_json(open_payload)
    client_signature_b64 = sign_bytes(client_private_key, message_bytes)

    with httpx.Client(timeout=10.0) as client:
        r = client.post(
            f"{issuer_base_url}/issuer/payment-channel/open",
            json={
                **open_payload,
                "client_signature_b64": client_signature_b64,
            },
        )
        r.raise_for_status()
        data = r.json()

        # Fetch issuer public key to validate the paychan certificate
        r_pk = client.get(f"{issuer_base_url}/issuer/public-key")
        r_pk.raise_for_status()
        issuer_public_key_der_b64 = r_pk.json()["der_b64"]
        issuer_public_key = load_public_key_der_b64(issuer_public_key_der_b64)

        # Verify and parse the paychan certificate
        cert_b64 = data["paychan_certificate_b64"]
        sig_b64 = data["paychan_signature_b64"]
        payload = issuer_verify_paychan_certificate_envelope(
            issuer_public_key, cert_b64, sig_b64
        )

        print(
            "Payment channel opened and certificate verified:",
            {
                "channel_id": data["channel_id"],
                "computed_id": data["computed_id"],
                "salt_b64": data["salt_b64"],
                "amount": data["amount"],
                "balance": data["balance"],
                "paychan_payload": payload.model_dump(),
            },
        )
        return (
            data["computed_id"],
            data["salt_b64"],
            data["amount"],
            data["balance"],
        )


def client_create_off_tx_to_vendor(
    computed_id: str,
    client_private_key_pem: str,
    amount: int,
) -> tuple[str, str]:
    """Client creates an off-chain payment transaction envelope for vendor.

    Payload fields: {"computed_id", "amount"}
    Returns: (certificate_b64, signature_b64)
    """
    client_private_key = serialization.load_pem_private_key(
        client_private_key_pem.encode(), password=None
    )
    payload = {"computed_id": computed_id, "amount": amount}
    return issue_payload_envelope(client_private_key, payload)


def vendor_validate_client_off_tx(
    issuer_base_url: str,
    vendor_private_key_pem: str,
    client_public_key_der_b64: str,
    certificate_b64: str,
    signature_b64: str,
) -> Dict[str, Any]:
    """Vendor validates client's off-chain payment envelope using client's public key.

    Returns the decoded payload dict on success.
    """
    client_public_key = load_public_key_der_b64(client_public_key_der_b64)
    payload = verify_payload_envelope(client_public_key, certificate_b64, signature_b64)
    print("Validated client off-chain tx:", payload)
    return payload


def vendor_close_pay_chan_using_off_tx(
    issuer_base_url: str,
    computed_id: str,
    owed_amount: int,
    closing_certificate_b64: str,
    closing_signature_b64: str,
    vendor_private_key_pem: str,
    client_public_key_der_b64: str,
    vendor_public_key_der_b64: str,
) -> Dict[str, Any]:
    """Vendor signs the off-chain certificate and submits close request to issuer."""
    vendor_private_key = serialization.load_pem_private_key(
        vendor_private_key_pem.encode(), password=None
    )
    # Sign over the canonical payload JSON (not the envelope bytes)
    certificate_bytes = base64.b64decode(closing_certificate_b64)
    payload_dict = json.loads(certificate_bytes.decode("utf-8"))
    canonical_bytes = canonicalize_json(payload_dict)
    vendor_signature_b64 = sign_bytes(vendor_private_key, canonical_bytes)

    with httpx.Client(timeout=10.0) as client:
        r = client.post(
            f"{issuer_base_url}/issuer/payment-channel/close",
            json={
                "computed_id": computed_id,
                "owed_amount": owed_amount,
                "closing_certificate_b64": closing_certificate_b64,
                "closing_signature_b64": closing_signature_b64,
                "vendor_signature_b64": vendor_signature_b64,
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

    client_off_tx = client_create_off_tx_to_vendor(
        computed_id, client_private_key_pem, 10
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

    vendor_validate_client_off_tx(
        issuer_base_url,
        vendor_private_key_pem,
        client_public_key_der_b64,
        client_off_tx[0],
        client_off_tx[1],
    )

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
