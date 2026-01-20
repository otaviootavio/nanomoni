"""ClientActor simulates client-side operations (key generation, signing)."""

from __future__ import annotations

import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from nanomoni.application.issuer.dtos import (
    RegistrationRequestDTO,
    OpenChannelRequestDTO,
)
from nanomoni.application.shared.payment_channel_payloads import (
    OpenChannelRequestPayload,
    SignaturePaymentPayload,
)
from nanomoni.application.shared.payword_payloads import (
    PaywordOpenChannelRequestPayload,
)
from nanomoni.application.shared.paytree_payloads import (
    PaytreeOpenChannelRequestPayload,
)
from nanomoni.crypto.certificates import Envelope, generate_envelope
from nanomoni.crypto.payword import Payword
from nanomoni.crypto.paytree import Paytree


class ClientActor:
    """Simulates client-side operations: key generation, signing, and envelope creation."""

    def __init__(self) -> None:
        """Initialize a new client actor with a generated key pair."""
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.public_key = self.private_key.public_key()
        public_key_der = self.public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        self.public_key_der_b64 = base64.b64encode(public_key_der).decode("utf-8")

    def create_registration_request(self) -> RegistrationRequestDTO:
        """Create a registration request with this client's public key."""
        return RegistrationRequestDTO(client_public_key_der_b64=self.public_key_der_b64)

    def create_open_channel_request(
        self, vendor_public_key_der_b64: str, amount: int
    ) -> OpenChannelRequestDTO:
        """
        Create an open channel request signed by this client.

        Args:
            vendor_public_key_der_b64: Vendor's public key in DER base64 format
            amount: Amount to lock in the channel

        Returns:
            OpenChannelRequestDTO with signed envelope
        """
        payload = OpenChannelRequestPayload(
            client_public_key_der_b64=self.public_key_der_b64,
            vendor_public_key_der_b64=vendor_public_key_der_b64,
            amount=amount,
        )
        envelope = generate_envelope(self.private_key, payload.model_dump())

        return OpenChannelRequestDTO(
            client_public_key_der_b64=self.public_key_der_b64,
            open_payload_b64=envelope.payload_b64,
            open_signature_b64=envelope.signature_b64,
        )

    def create_payment_envelope(
        self,
        channel_id: str,
        cumulative_owed_amount: int,
    ) -> Envelope:
        """
        Create a signed payment envelope for an off-chain transaction.

        Args:
            channel_id: Payment channel identifier string provided by the API
            cumulative_owed_amount: Amount owed to vendor

        Returns:
            Signed Envelope containing the payment payload
        """
        payload = SignaturePaymentPayload(
            channel_id=channel_id,
            cumulative_owed_amount=cumulative_owed_amount,
        )
        return generate_envelope(self.private_key, payload.model_dump())

    def create_open_channel_request_payword(
        self,
        vendor_public_key_der_b64: str,
        *,
        amount: int,
        unit_value: int,
        max_k: int,
        pebble_count: int,
    ) -> tuple[OpenChannelRequestDTO, Payword]:
        """
        Create an open channel request with an embedded PayWord commitment.

        Returns:
            (OpenChannelRequestDTO, Payword) so tests can generate tokens efficiently.

            Note: token generation is **not** O(1) in general. Proof generation hashes
            forward from the nearest cached pebble checkpoint to the requested index.
            Worst-case hashing work is proportional to the largest gap between pebbles
            (roughly O(max_k / pebble_count); O(max_k) when pebble_count=0).
        """
        if unit_value <= 0:
            raise ValueError("unit_value must be > 0")

        payword = Payword.create(max_k=max_k, pebble_count=pebble_count)
        root_b64 = payword.commitment_root_b64

        payload = PaywordOpenChannelRequestPayload(
            client_public_key_der_b64=self.public_key_der_b64,
            vendor_public_key_der_b64=vendor_public_key_der_b64,
            amount=amount,
            payword_root_b64=root_b64,
            payword_unit_value=unit_value,
            payword_max_k=max_k,
            payword_hash_alg="sha256",
        )
        envelope = generate_envelope(self.private_key, payload.model_dump())

        return (
            OpenChannelRequestDTO(
                client_public_key_der_b64=self.public_key_der_b64,
                open_payload_b64=envelope.payload_b64,
                open_signature_b64=envelope.signature_b64,
            ),
            payword,
        )

    def create_open_channel_request_payword_with_root(
        self,
        vendor_public_key_der_b64: str,
        *,
        amount: int,
        unit_value: int,
        max_k: int,
        payword_root_b64: str,
    ) -> OpenChannelRequestDTO:
        """
        Create an open channel request embedding an existing PayWord commitment root.

        This is useful for stress tests where generating a fresh PayWord chain per client
        (O(max_k) hashing) would dominate runtime. The issuer/vendor still verify tokens
        with O(k) hashing during payment/settlement.
        """
        if unit_value <= 0:
            raise ValueError("unit_value must be > 0")

        payload = PaywordOpenChannelRequestPayload(
            client_public_key_der_b64=self.public_key_der_b64,
            vendor_public_key_der_b64=vendor_public_key_der_b64,
            amount=amount,
            payword_root_b64=payword_root_b64,
            payword_unit_value=unit_value,
            payword_max_k=max_k,
            payword_hash_alg="sha256",
        )
        envelope = generate_envelope(self.private_key, payload.model_dump())

        return OpenChannelRequestDTO(
            client_public_key_der_b64=self.public_key_der_b64,
            open_payload_b64=envelope.payload_b64,
            open_signature_b64=envelope.signature_b64,
        )

    def create_open_channel_request_paytree(
        self,
        vendor_public_key_der_b64: str,
        *,
        amount: int,
        unit_value: int,
        max_i: int,
    ) -> tuple[OpenChannelRequestDTO, Paytree]:
        """
        Create an open channel request with an embedded PayTree commitment.

        Returns:
            (OpenChannelRequestDTO, Paytree) so tests can generate proofs efficiently.
        """
        if unit_value <= 0:
            raise ValueError("unit_value must be > 0")

        paytree = Paytree.create(max_i=max_i)
        root_b64 = paytree.commitment_root_b64

        payload = PaytreeOpenChannelRequestPayload(
            client_public_key_der_b64=self.public_key_der_b64,
            vendor_public_key_der_b64=vendor_public_key_der_b64,
            amount=amount,
            paytree_root_b64=root_b64,
            paytree_unit_value=unit_value,
            paytree_max_i=max_i,
            paytree_hash_alg="sha256",
        )
        envelope = generate_envelope(self.private_key, payload.model_dump())

        return (
            OpenChannelRequestDTO(
                client_public_key_der_b64=self.public_key_der_b64,
                open_payload_b64=envelope.payload_b64,
                open_signature_b64=envelope.signature_b64,
            ),
            paytree,
        )
