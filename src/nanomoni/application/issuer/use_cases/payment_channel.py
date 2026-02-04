from __future__ import annotations

import base64
import hashlib
import os
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature

from ....domain.issuer.entities import Account, SignaturePaymentChannel
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
    verify_signature_bytes,
    dto_to_canonical_json_bytes,
    DERB64,
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
        return base64.urlsafe_b64encode(hasher.digest()).decode("utf-8").rstrip("=")

    async def open_channel(self, dto: OpenChannelRequestDTO) -> OpenChannelResponseDTO:
        # Verify client signature over the flat DTO fields
        client_public_key = load_public_key_from_der_b64(
            DERB64(dto.client_public_key_der_b64)
        )

        # Reconstruct canonical JSON from DTO fields (excluding signature)
        payload_bytes = dto_to_canonical_json_bytes(dto)

        try:
            verify_signature_bytes(
                client_public_key, payload_bytes, dto.open_signature_b64
            )
        except InvalidSignature:
            raise ValueError("Invalid client signature for open channel request")

        # Ensure client account exists
        client_acc = await self.account_repo.get_by_public_key(
            dto.client_public_key_der_b64
        )
        if not client_acc:
            raise ValueError("Client account not registered")

        # Ensure vendor account exists
        vendor_acc = await self.account_repo.get_by_public_key(
            dto.vendor_public_key_der_b64
        )
        if not vendor_acc:
            raise ValueError("Vendor account not registered")

        # Verify amount
        if dto.amount <= 0:
            raise ValueError("Amount must be positive")
        if client_acc.balance < dto.amount:
            raise ValueError("Insufficient client balance to lock funds")

        # Generate salt server-side
        salt_bytes = os.urandom(32)
        salt_b64 = base64.b64encode(salt_bytes).decode("utf-8")

        channel_id = self._compute_channel_id(
            dto.client_public_key_der_b64,
            dto.vendor_public_key_der_b64,
            salt_b64,
        )

        existing = await self.channel_repo.get_by_channel_id(channel_id)
        if existing and not existing.is_closed:
            raise ValueError("Payment channel already open")

        # Create the channel and lock the funds into the channel
        channel = SignaturePaymentChannel(
            channel_id=channel_id,
            client_public_key_der_b64=dto.client_public_key_der_b64,
            vendor_public_key_der_b64=dto.vendor_public_key_der_b64,
            salt_b64=salt_b64,
            amount=dto.amount,
            balance=0,
        )
        created = await self.channel_repo.create(channel)

        # Deduct funds only after the channel is persisted. If the balance update
        # fails for any reason, attempt to roll back by deleting the channel.
        try:
            await self.account_repo.update_balance(
                dto.client_public_key_der_b64, -dto.amount
            )
        except Exception:
            await self.channel_repo.delete_by_channel_id(channel_id)
            raise

        # Issue a plain response describing the opened channel
        return OpenChannelResponseDTO(
            channel_id=created.channel_id,
            client_public_key_der_b64=created.client_public_key_der_b64,
            vendor_public_key_der_b64=created.vendor_public_key_der_b64,
            salt_b64=created.salt_b64,
            amount=created.amount,
            balance=created.balance,
        )

    async def settle_channel(
        self, dto: CloseChannelRequestDTO
    ) -> CloseChannelResponseDTO:
        # Close-channel payload is a "thin" statement: (channel_id, cumulative_owed_amount).
        # The Issuer infers client/vendor keys from the PaymentChannel stored by channel_id.
        channel_id = dto.channel_id
        cumulative_owed_amount = dto.cumulative_owed_amount

        channel = await self.channel_repo.get_by_channel_id(channel_id)
        if not channel:
            raise ValueError("Payment channel not found")
        if channel.is_closed:
            raise ValueError("Payment channel already closed")
        if not isinstance(channel, SignaturePaymentChannel):
            raise TypeError("Payment channel is not signature-mode")

        if cumulative_owed_amount < 0 or cumulative_owed_amount > channel.amount:
            raise ValueError("Invalid owed amount")

        # Reconstruct canonical JSON from DTO fields (excluding signatures)
        close_payload_bytes = dto_to_canonical_json_bytes(dto)

        # Verify client signature over reconstructed payload bytes
        client_public_key: ec.EllipticCurvePublicKey = load_public_key_from_der_b64(
            DERB64(channel.client_public_key_der_b64)
        )
        try:
            verify_signature_bytes(
                client_public_key, close_payload_bytes, dto.client_close_signature_b64
            )
        except InvalidSignature as err:
            raise ValueError("Invalid client signature for closing") from err

        # Verify vendor signature over same payload bytes
        vendor_public_key: ec.EllipticCurvePublicKey = load_public_key_from_der_b64(
            DERB64(channel.vendor_public_key_der_b64)
        )
        try:
            verify_signature_bytes(
                vendor_public_key, close_payload_bytes, dto.vendor_close_signature_b64
            )
        except InvalidSignature:
            raise ValueError("Invalid vendor signature for closing")

        # Ensure vendor account exists
        vendor_key = channel.vendor_public_key_der_b64

        vendor_acc = await self.account_repo.get_by_public_key(vendor_key)
        if not vendor_acc:
            vendor_acc = Account(public_key_der_b64=vendor_key, balance=0)
            await self.account_repo.upsert(vendor_acc)

        # Return the remainder to client
        remainder = channel.amount - cumulative_owed_amount

        # The following three operations must behave transactionally:
        # 1) credit vendor, 2) refund client remainder, 3) mark channel closed.
        # If any step fails, roll back prior balance changes before propagating
        # the error to avoid leaving inconsistent balances.
        vendor_acc = await self.account_repo.update_balance(
            vendor_key, cumulative_owed_amount
        )
        try:
            client_acc = await self.account_repo.update_balance(
                channel.client_public_key_der_b64, remainder
            )
        except Exception:
            # Roll back vendor credit if client refund fails.
            await self.account_repo.update_balance(vendor_key, -cumulative_owed_amount)
            raise

        try:
            # Reconstruct close_payload_b64 for storage (backward compatibility)
            close_payload_b64 = base64.b64encode(close_payload_bytes).decode("utf-8")
            # Mark channel closed and persist the closing signature, updating channel amounts
            await self.channel_repo.mark_closed(
                channel_id,
                close_payload_b64,
                dto.client_close_signature_b64,
                amount=channel.amount,
                balance=cumulative_owed_amount,
                vendor_close_signature_b64=dto.vendor_close_signature_b64,
            )
        except Exception as close_err:
            # Roll back both balance updates if closing persistence fails.
            rollback_errors: list[Exception] = []
            try:
                await self.account_repo.update_balance(
                    vendor_key, -cumulative_owed_amount
                )
            except Exception as e:
                rollback_errors.append(e)
            try:
                await self.account_repo.update_balance(
                    channel.client_public_key_der_b64, -remainder
                )
            except Exception as e:
                rollback_errors.append(e)

            if rollback_errors:
                raise RuntimeError(
                    "Failed to mark channel closed and failed to roll back balances"
                ) from close_err
            raise

        return CloseChannelResponseDTO(
            channel_id=channel_id,
            client_balance=client_acc.balance,
            vendor_balance=vendor_acc.balance,
        )

    async def get_channel(
        self, dto: GetPaymentChannelRequestDTO
    ) -> PaymentChannelResponseDTO:
        channel = await self.channel_repo.get_by_channel_id(dto.channel_id)
        if not channel:
            raise ValueError("Payment channel not found")
        if not isinstance(channel, SignaturePaymentChannel):
            raise TypeError("Payment channel is not signature-mode")
        data = channel.model_dump()
        return PaymentChannelResponseDTO(**data)
