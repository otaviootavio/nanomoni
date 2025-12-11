from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization

from nanomoni.application.issuer.dtos import (
    OpenChannelRequestDTO,
    RegistrationRequestDTO,
)
from nanomoni.application.shared.payment_channel_payloads import (
    OffChainTxPayload,
    verify_and_deserialize_off_chain_tx,
)
from nanomoni.application.vendor.dtos import (
    CloseChannelDTO,
    OffChainTxResponseDTO,
    ReceivePaymentDTO,
)
from nanomoni.crypto.certificates import (
    DERB64,
    Envelope,
    PayloadB64,
    SignatureB64,
    generate_envelope,
    load_private_key_from_pem,
    load_public_key_from_der_b64,
)
from nanomoni.envs.client_env import get_settings
from nanomoni.infrastructure.issuer.issuer_client import IssuerClient
from nanomoni.infrastructure.vendor.vendor_client import VendorClient


def register_into_issuer_using_private_key(
    issuer_base_url: str, private_key_pem: str
) -> dict[str, object]:
    private_key = load_private_key_from_pem(private_key_pem)
    public_key = private_key.public_key()
    public_key_der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_key_der_b64 = base64.b64encode(public_key_der).decode("utf-8")

    print("Registering into issuer using public key")

    with IssuerClient(issuer_base_url) as issuer_client:
        dto = RegistrationRequestDTO(client_public_key_der_b64=public_key_der_b64)
        try:
            resp = issuer_client.register(dto)
            return resp.model_dump()
        except Exception:
            # Preserve existing behavior of surfacing registration errors
            raise


def open_payment_channel(
    issuer_base_url: str,
    vendor_public_key_der_b64: str,
    client_private_key_pem: str,
    amount: int,
) -> tuple[str, str, int, int]:
    client_private_key = load_private_key_from_pem(client_private_key_pem)

    client_public_key = client_private_key.public_key()

    client_public_key_der = client_public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    client_public_key_der_b64 = base64.b64encode(client_public_key_der).decode("utf-8")

    print("Opening payment channel using public keys.")

    # Build client-signed open envelope
    open_payload = {
        "vendor_public_key_der_b64": vendor_public_key_der_b64,
        "client_public_key_der_b64": client_public_key_der_b64,
        "amount": amount,
    }
    client_open_envelope = generate_envelope(client_private_key, open_payload)

    with IssuerClient(issuer_base_url) as issuer_client:
        # 1) Open channel
        open_dto = OpenChannelRequestDTO(
            client_public_key_der_b64=client_public_key_der_b64,
            open_payload_b64=client_open_envelope.payload_b64,
            open_signature_b64=client_open_envelope.signature_b64,
        )
        resp = issuer_client.open_payment_channel(open_dto)

        print("Payment channel opened")
        return (
            resp.computed_id,
            resp.salt_b64,
            resp.amount,
            resp.balance,
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
    client_private_key = load_private_key_from_pem(client_private_key_pem)

    payload = OffChainTxPayload(
        computed_id=computed_id,
        client_public_key_der_b64=client_public_key_der_b64,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        owed_amount=owed_amount,
    )

    envelope = generate_envelope(client_private_key, payload.model_dump())
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
    client_public_key = load_public_key_from_der_b64(DERB64(client_public_key_der_b64))
    envelope = Envelope(
        payload_b64=PayloadB64(payload_b64), signature_b64=SignatureB64(signature_b64)
    )

    # 1) Verify client's signature and decode payload in one step
    payload = verify_and_deserialize_off_chain_tx(client_public_key, envelope)

    # 2) Check for double spending
    if payload.owed_amount <= prev_owed_amount:
        raise ValueError(
            f"Owed amount must be increasing. Got {payload.owed_amount}, expected > {prev_owed_amount}"
        )
    return envelope


def send_payment_to_vendor(
    vendor_base_url: str,
    computed_id: str,
    client_off_tx_envelope: Envelope,
) -> OffChainTxResponseDTO:
    """Send an off-chain payment to the vendor API for processing.

    Returns the vendor's response with the processed transaction details.
    """
    with VendorClient(vendor_base_url) as vendor_client:
        request_dto = ReceivePaymentDTO(envelope=client_off_tx_envelope)
        response_dto = vendor_client.send_off_chain_payment(computed_id, request_dto)

        # Parse and log payment details (latest state for this channel)
        computed_id = response_dto.computed_id
        owed_amount = response_dto.owed_amount
        created_at = response_dto.created_at

        print(
            "Payment successfully processed by vendor. "
            f"Channel ID: {computed_id}, Owed Amount: {owed_amount}, Created At: {created_at}"
        )

        return response_dto


def request_vendor_close_channel(vendor_base_url: str, computed_id: str) -> None:
    """Ask the vendor to close the payment channel for the given computed_id."""
    with VendorClient(vendor_base_url) as vendor_client:
        dto = CloseChannelDTO(computed_id=computed_id)
        vendor_client.request_close_channel(dto)
        print(f"Requested vendor to close channel {computed_id}")


def main() -> None:
    settings = get_settings()
    issuer_base_url = settings.issuer_base_url
    vendor_base_url = settings.vendor_base_url
    client_private_key_pem = settings.client_private_key_pem
    client_public_key_der_b64: str = settings.client_public_key_der_b64

    register_into_issuer_using_private_key(issuer_base_url, client_private_key_pem)

    # Get vendor public key
    with VendorClient(vendor_base_url) as vendor_client:
        vendor_pk_dto = vendor_client.get_vendor_public_key()
        vendor_public_key_der_b64 = vendor_pk_dto.public_key_der_b64

    # TODO
    # This datas are not used for now
    # But it may be useful in the future
    # Ex: the client can open another channel based on a logic
    # in wich consider the balance as a hard-limit for the sum
    # of the amount of continuous payments.
    computed_id, salt_b64, amount, balance = open_payment_channel(
        issuer_base_url, vendor_public_key_der_b64, client_private_key_pem, 50000
    )

    # Loop to send 100,000 off-chain payments to the vendor API
    for i in range(1, 5000):
        client_off_tx = client_create_off_tx_to_vendor(
            computed_id,
            client_private_key_pem,
            i,  # Cumulative owed_amount
            client_public_key_der_b64,
            vendor_public_key_der_b64,
        )

        # Send payment to vendor API
        send_payment_to_vendor(
            vendor_base_url,
            computed_id,
            client_off_tx,
        )

    # After sending all micropayments, request the vendor to close the channel
    request_vendor_close_channel(vendor_base_url, computed_id)


if __name__ == "__main__":
    main()
