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
    deserialize_off_chain_tx,
    OffChainTxPayload,
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

    print(f"Registering into issuer using public key")

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
    vendor_public_key_der_b64: str,
    client_private_key_pem: str,
    amount: int,
) -> tuple[str, str, int, int]:
    client_private_key = serialization.load_pem_private_key(
        client_private_key_pem.encode(), password=None
    )

    client_public_key = client_private_key.public_key()

    client_public_key_der = client_public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    client_public_key_der_b64 = base64.b64encode(client_public_key_der).decode("utf-8")

    print(f"Opening payment channel using public keys.")

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

        print("Payment channel opened and issuer envelope verified")
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
) -> Envelope:
    """Client creates an off-chain close request envelope for vendor.

    Payload fields: {"computed_id", "client_public_key_der_b64", "vendor_public_key_der_b64", "owed_amount"}
    Returns: Envelope
    """
    client_private_key = serialization.load_pem_private_key(
        client_private_key_pem.encode(), password=None
    )

    payload: OffChainTxPayload = {
        "computed_id": computed_id,
        "client_public_key_der_b64": client_public_key_der_b64,
        "vendor_public_key_der_b64": vendor_public_key_der_b64,
        "owed_amount": owed_amount,
    }

    envelope = generate_envelope(client_private_key, payload)
    return envelope


def vendor_validate_client_off_tx(
    client_public_key_der_b64: str,
    payload_b64: str,
    signature_b64: str,
    prev_owed_amount: int,
) -> Envelope:
    """Vendor validates client's off-chain payment envelope using client's public key.

    Returns the envelope on success.
    """
    client_public_key = load_public_key_from_der_b64(client_public_key_der_b64)
    envelope = Envelope(payload_b64=payload_b64, signature_b64=signature_b64)

    # 1) Verify client's signature
    verify_envelope(client_public_key, envelope)

    # 2) Decode and validate payload
    payload = deserialize_off_chain_tx(envelope)

    # 3) Check for double spending
    if payload.owed_amount <= prev_owed_amount:
        raise ValueError(
            f"Owed amount must be increasing. Got {payload.owed_amount}, expected > {prev_owed_amount}"
        )
    return envelope


def send_payment_to_vendor(
    vendor_base_url: str,
    client_off_tx_envelope: Envelope,
    client_public_key_der_b64: str,
) -> Dict[str, Any]:
    """Send an off-chain payment to the vendor API for processing.

    Returns the vendor's response with the processed transaction details.
    """
    payment_payload = {
        "envelope": {
            "payload_b64": client_off_tx_envelope.payload_b64,
            "signature_b64": client_off_tx_envelope.signature_b64,
        },
        "client_public_key_der_b64": client_public_key_der_b64,
    }

    with httpx.Client(timeout=10.0) as client:
        try:
            r = client.post(
                f"{vendor_base_url}/payments/receive",
                json=payment_payload,
            )
            r.raise_for_status()
            response_data = r.json()

            # Parse and log payment details
            payment_id = response_data.get("id")
            computed_id = response_data.get("computed_id")
            owed_amount = response_data.get("owed_amount")
            created_at = response_data.get("created_at")

            print(
                f"Payment successfully processed by vendor. Payment ID: {payment_id}, Channel ID: {computed_id}, Owed Amount: {owed_amount}, Created At: {created_at}"
            )

            return response_data
        except httpx.HTTPStatusError as e:
            if e.response is not None:
                try:
                    error_detail = e.response.json().get("detail", e.response.text)
                except Exception:
                    error_detail = e.response.text
                print(f"Vendor rejected payment: {error_detail}")
                raise ValueError(f"Vendor payment failed: {error_detail}")
            raise
        except Exception as e:
            print(f"Failed to send payment to vendor: {e}")
            raise


def request_vendor_close_channel(vendor_base_url: str, computed_id: str) -> None:
    """Ask the vendor to close the payment channel for the given computed_id."""
    with httpx.Client(timeout=10.0) as client:
        r = client.post(
            f"{vendor_base_url}/payments/close",
            json={"computed_id": computed_id},
        )
        r.raise_for_status()
        print(f"Requested vendor to close channel {computed_id}")


def main() -> None:
    settings = get_settings()
    issuer_base_url = settings.issuer_base_url
    vendor_base_url = settings.vendor_base_url
    client_private_key_pem = settings.client_private_key_pem
    client_public_key_der_b64 = settings.client_public_key_der_b64

    register_into_issuer_using_private_key(issuer_base_url, client_private_key_pem)

    # Get vendor public key
    with httpx.Client(timeout=10.0) as client:
        r = client.get(f"{vendor_base_url}/vendor/public-key")
        r.raise_for_status()
        vendor_public_key_der_b64 = r.json()["public_key_der_b64"]

    # TODO
    # This datas are not used for now
    # But it may be useful in the future
    # Ex: the client can open another channel based on a logic
    # in wich consider the balance as a hard-limit for the sum
    # of the amount of continuous payments.
    computed_id, salt_b64, amount, balance = open_payment_channel(
        issuer_base_url, vendor_public_key_der_b64, client_private_key_pem, 1234
    )

    # Loop to send 10,000 off-chain payments to the vendor API
    last_vendor_response = None
    for i in range(1, 501):
        client_off_tx = client_create_off_tx_to_vendor(
            computed_id,
            client_private_key_pem,
            i,  # Cumulative owed_amount
            client_public_key_der_b64,
            vendor_public_key_der_b64,
        )

        # Send payment to vendor API
        last_vendor_response = send_payment_to_vendor(
            vendor_base_url,
            client_off_tx,
            client_public_key_der_b64,
        )

    # After sending all micropayments, request the vendor to close the channel
    request_vendor_close_channel(vendor_base_url, computed_id)


if __name__ == "__main__":
    main()
