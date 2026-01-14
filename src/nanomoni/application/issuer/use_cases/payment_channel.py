from __future__ import annotations

import base64
import hashlib
import os
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature

from ....domain.issuer.entities import PaymentChannel, Account
from ....domain.issuer.repositories import (
    PaymentChannelRepository,
    AccountRepository,
)
from ..dtos import (
    OpenChannelRequestDTO,
    OpenChannelResponseDTO,
    CloseChannelRequestDTO,
    CloseChannelResponseDTO,
    GetPaymentChannelRequestDTO,
    PaymentChannelResponseDTO,
)
from ....crypto.certificates import (
    load_public_key_from_der_b64,
    Envelope,
    PayloadB64,
    SignatureB64,
    verify_envelope,
    verify_envelope_and_get_payload_bytes,
    DERB64,
)
from ....application.shared.payment_channel_payloads import (
    OpenChannelRequestPayload,
    CloseChannelRequestPayload,
)


class PaymentChannelService:
    """Service to manage opening and closing payment channels."""

    issuer_private_key: ec.EllipticCurvePrivateKey

    def __init__(
        self,
        account_repo: AccountRepository,
        channel_repo: PaymentChannelRepository,
        issuer_private_key: ec.EllipticCurvePrivateKey,
    ):
        self.account_repo = account_repo
        self.channel_repo = channel_repo
        self.issuer_private_key = issuer_private_key

    @staticmethod
    def _compute_channel_id(
        client_public_key_der_b64: str, vendor_public_key_der_b64: str, salt_b64: str
    ) -> str:
        hasher = hashlib.sha256()
        hasher.update(base64.b64decode(client_public_key_der_b64))
        hasher.update(base64.b64decode(vendor_public_key_der_b64))
        hasher.update(base64.b64decode(salt_b64))
        return hasher.hexdigest()

    async def open_channel(self, dto: OpenChannelRequestDTO) -> OpenChannelResponseDTO:
        # Deserialize and verify client-provided open-channel envelope
        client_public_key = load_public_key_from_der_b64(
            DERB64(dto.client_public_key_der_b64)
        )
        client_envelope: Envelope = Envelope(
            payload_b64=PayloadB64(dto.open_payload_b64),
            signature_b64=SignatureB64(dto.open_signature_b64),
        )
        try:
            payload_bytes = verify_envelope_and_get_payload_bytes(
                client_public_key, client_envelope
            )
        except InvalidSignature:
            raise ValueError("Invalid client signature for open channel request")

        # Parse payload to structured data
        open_req_payload = OpenChannelRequestPayload.model_validate_json(
            payload_bytes.decode("utf-8")
        )

        # Ensure the declared public key matches the payload
        if open_req_payload.client_public_key_der_b64 != dto.client_public_key_der_b64:
            raise ValueError("Mismatched client public key between field and payload")

        # Ensure client account exists
        client_acc = await self.account_repo.get_by_public_key(
            open_req_payload.client_public_key_der_b64
        )
        if not client_acc:
            raise ValueError("Client account not registered")

        # Ensure vendor account exists
        vendor_acc = await self.account_repo.get_by_public_key(
            open_req_payload.vendor_public_key_der_b64
        )
        if not vendor_acc:
            raise ValueError("Vendor account not registered")

        # Verify amount
        if open_req_payload.amount <= 0:
            raise ValueError("Amount must be positive")
        if client_acc.balance < open_req_payload.amount:
            raise ValueError("Insufficient client balance to lock funds")

        # Generate salt server-side
        salt_bytes = os.urandom(32)
        salt_b64 = base64.b64encode(salt_bytes).decode("utf-8")

        computed_id = self._compute_channel_id(
            open_req_payload.client_public_key_der_b64,
            open_req_payload.vendor_public_key_der_b64,
            salt_b64,
        )

        existing = await self.channel_repo.get_by_computed_id(computed_id)
        if existing and not existing.is_closed:
            raise ValueError("Payment channel already open")

        # Create the channel and lock the funds into the channel
        channel = PaymentChannel(
            computed_id=computed_id,
            client_public_key_der_b64=open_req_payload.client_public_key_der_b64,
            vendor_public_key_der_b64=open_req_payload.vendor_public_key_der_b64,
            salt_b64=salt_b64,
            amount=open_req_payload.amount,
            balance=0,
            payword_root_b64=None,
            payword_unit_value=None,
            payword_max_k=None,
            payword_hash_alg=None,
        )
        created = await self.channel_repo.create(channel)

        # Deduct funds only after the channel is persisted. If the balance update
        # fails for any reason, attempt to roll back by deleting the channel.
        try:
            await self.account_repo.update_balance(
                open_req_payload.client_public_key_der_b64, -open_req_payload.amount
            )
        except Exception:
            await self.channel_repo.delete_by_computed_id(computed_id)
            raise

        # Issue a plain response describing the opened channel
        return OpenChannelResponseDTO(
            computed_id=created.computed_id,
            client_public_key_der_b64=created.client_public_key_der_b64,
            vendor_public_key_der_b64=created.vendor_public_key_der_b64,
            salt_b64=created.salt_b64,
            amount=created.amount,
            balance=created.balance,
        )

    async def close_channel(
        self, dto: CloseChannelRequestDTO
    ) -> CloseChannelResponseDTO:
        # Deserialize and verify client close-channel envelope (client signature)
        client_public_key: ec.EllipticCurvePublicKey = load_public_key_from_der_b64(
            DERB64(dto.client_public_key_der_b64)
        )
        client_envelope: Envelope = Envelope(
            payload_b64=PayloadB64(dto.close_payload_b64),
            signature_b64=SignatureB64(dto.client_close_signature_b64),
        )
        try:
            client_payload_bytes = verify_envelope_and_get_payload_bytes(
                client_public_key, client_envelope
            )
        except InvalidSignature:
            raise ValueError("Invalid closing certificate signature")
        except Exception:
            raise ValueError("Invalid certificate payload format")

        # Deserialize and verify vendor close-channel envelope (vendor signature)
        vendor_public_key: ec.EllipticCurvePublicKey = load_public_key_from_der_b64(
            DERB64(dto.vendor_public_key_der_b64)
        )
        vendor_envelope: Envelope = Envelope(
            payload_b64=PayloadB64(dto.close_payload_b64),
            signature_b64=SignatureB64(dto.vendor_close_signature_b64),
        )
        try:
            verify_envelope(vendor_public_key, vendor_envelope)
        except InvalidSignature:
            raise ValueError("Invalid vendor signature for closing")

        # Parse and validate the close payload using already-decoded bytes
        close_payload: CloseChannelRequestPayload = (
            CloseChannelRequestPayload.model_validate_json(
                client_payload_bytes.decode("utf-8")
            )
        )

        # Ensure channel exists
        channel = await self.channel_repo.get_by_computed_id(close_payload.computed_id)
        if not channel:
            raise ValueError("Payment channel not found")
        if channel.is_closed:
            raise ValueError("Payment channel already closed")

        # Basic consistency checks
        if close_payload.client_public_key_der_b64 != channel.client_public_key_der_b64:
            raise ValueError("Mismatched client public key for channel")
        if close_payload.vendor_public_key_der_b64 != channel.vendor_public_key_der_b64:
            raise ValueError("Mismatched vendor public key for channel")

        if close_payload.owed_amount < 0 or close_payload.owed_amount > channel.amount:
            raise ValueError("Invalid owed amount")

        # Ensure vendor account exists
        vendor_acc = await self.account_repo.get_by_public_key(
            close_payload.vendor_public_key_der_b64
        )
        if not vendor_acc:
            vendor_acc = Account(
                public_key_der_b64=close_payload.vendor_public_key_der_b64, balance=0
            )
            await self.account_repo.upsert(vendor_acc)

        # Return the remainder to client
        remainder = channel.amount - close_payload.owed_amount

        # The following three operations must behave transactionally:
        # 1) credit vendor, 2) refund client remainder, 3) mark channel closed.
        # If any step fails, roll back prior balance changes before propagating
        # the error to avoid leaving inconsistent balances.
        vendor_acc = await self.account_repo.update_balance(
            close_payload.vendor_public_key_der_b64, close_payload.owed_amount
        )
        try:
            client_acc = await self.account_repo.update_balance(
                close_payload.client_public_key_der_b64, remainder
            )
        except Exception:
            # Roll back vendor credit if client refund fails.
            await self.account_repo.update_balance(
                close_payload.vendor_public_key_der_b64, -close_payload.owed_amount
            )
            raise

        try:
            # Mark channel closed and persist the closing signature, updating channel amounts
            await self.channel_repo.mark_closed(
                close_payload.computed_id,
                dto.close_payload_b64,
                dto.client_close_signature_b64,
                amount=channel.amount,
                balance=close_payload.owed_amount,
                vendor_close_signature_b64=dto.vendor_close_signature_b64,
            )
        except Exception as close_err:
            # Roll back both balance updates if closing persistence fails.
            rollback_errors: list[Exception] = []
            try:
                await self.account_repo.update_balance(
                    close_payload.vendor_public_key_der_b64, -close_payload.owed_amount
                )
            except Exception as e:
                rollback_errors.append(e)
            try:
                await self.account_repo.update_balance(
                    close_payload.client_public_key_der_b64, -remainder
                )
            except Exception as e:
                rollback_errors.append(e)

            if rollback_errors:
                raise RuntimeError(
                    "Failed to mark channel closed and failed to roll back balances"
                ) from close_err
            raise

        return CloseChannelResponseDTO(
            computed_id=close_payload.computed_id,
            client_balance=client_acc.balance,
            vendor_balance=vendor_acc.balance,
        )

    async def get_channel(
        self, dto: GetPaymentChannelRequestDTO
    ) -> PaymentChannelResponseDTO:
        channel = await self.channel_repo.get_by_computed_id(dto.computed_id)
        if not channel:
            raise ValueError("Payment channel not found")
        # Signature flow response should not expose PayWord fields.
        data = channel.model_dump(
            exclude={
                "payword_root_b64",
                "payword_unit_value",
                "payword_max_k",
                "payword_hash_alg",
            }
        )
        return PaymentChannelResponseDTO(**data)
