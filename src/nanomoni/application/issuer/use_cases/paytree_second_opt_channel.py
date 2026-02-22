"""Use cases for the issuer PayTree Second Opt flow."""

from __future__ import annotations

import base64
import binascii
import hashlib
import os

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ec

from ....application.issuer.dtos import (
    CloseChannelResponseDTO,
    GetPaymentChannelRequestDTO,
    OpenChannelRequestDTO,
)
from ....application.issuer.paytree_second_opt_dtos import (
    PaytreeSecondOptOpenChannelResponseDTO,
    PaytreeSecondOptPaymentChannelResponseDTO,
    PaytreeSecondOptSettlementRequestDTO,
)
from ....application.shared.paytree_second_opt_payloads import (
    PaytreeSecondOptSettlementPayload,
)
from ....application.shared.serialization import payload_to_bytes
from ....crypto.certificates import (
    DERB64,
    dto_to_canonical_json_bytes,
    load_public_key_from_der_b64,
    verify_signature_bytes,
)
from ....crypto.paytree import (
    b64_to_bytes,
    compute_cumulative_owed_amount,
    verify_paytree_proof,
)
from ....domain.issuer.entities import Account, PaytreeSecondOptPaymentChannel
from ....domain.issuer.repositories import AccountRepository, PaymentChannelRepository


class PaytreeSecondOptChannelService:
    """Service to manage opening and settling PayTree Second Opt channels."""

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

    async def open_channel(
        self, dto: OpenChannelRequestDTO
    ) -> PaytreeSecondOptOpenChannelResponseDTO:
        if (
            dto.paytree_second_opt_root_b64 is None
            or dto.paytree_second_opt_unit_value is None
            or dto.paytree_second_opt_max_i is None
        ):
            raise ValueError(
                "PayTree Second Opt fields are required for channel opening"
            )

        payload_bytes = dto_to_canonical_json_bytes(dto)

        try:
            client_public_key = load_public_key_from_der_b64(
                DERB64(dto.client_public_key_der_b64)
            )
            verify_signature_bytes(
                client_public_key, payload_bytes, dto.open_signature_b64
            )
        except (InvalidSignature, binascii.Error):
            raise ValueError("Invalid client signature for open channel request")

        client_acc = await self.account_repo.get_by_public_key(
            dto.client_public_key_der_b64
        )
        if not client_acc:
            raise ValueError("Client account not registered")

        vendor_acc = await self.account_repo.get_by_public_key(
            dto.vendor_public_key_der_b64
        )
        if not vendor_acc:
            raise ValueError("Vendor account not registered")

        if dto.amount <= 0:
            raise ValueError("Amount must be positive")
        if client_acc.balance < dto.amount:
            raise ValueError("Insufficient client balance to lock funds")

        try:
            _ = b64_to_bytes(dto.paytree_second_opt_root_b64)
        except Exception as e:
            raise ValueError(f"Invalid paytree_second_opt_root_b64: {e}") from e

        max_owed = compute_cumulative_owed_amount(
            i=dto.paytree_second_opt_max_i,
            unit_value=dto.paytree_second_opt_unit_value,
        )
        if max_owed > dto.amount:
            raise ValueError(
                "PayTree Second Opt max owed exceeds channel amount "
                f"(max_owed={max_owed}, amount={dto.amount})"
            )

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

        channel = PaytreeSecondOptPaymentChannel(
            channel_id=channel_id,
            client_public_key_der_b64=dto.client_public_key_der_b64,
            vendor_public_key_der_b64=dto.vendor_public_key_der_b64,
            salt_b64=salt_b64,
            amount=dto.amount,
            balance=0,
            paytree_second_opt_root_b64=dto.paytree_second_opt_root_b64,
            paytree_second_opt_unit_value=dto.paytree_second_opt_unit_value,
            paytree_second_opt_max_i=dto.paytree_second_opt_max_i,
        )
        created = await self.channel_repo.create(channel)
        if not isinstance(created, PaytreeSecondOptPaymentChannel):
            raise RuntimeError(
                "Unexpected: persisted channel is not PayTree Second Opt-enabled"
            )

        try:
            await self.account_repo.update_balance(
                dto.client_public_key_der_b64, -dto.amount
            )
        except Exception:
            await self.channel_repo.delete_by_channel_id(channel_id)
            raise

        return PaytreeSecondOptOpenChannelResponseDTO(
            channel_id=created.channel_id,
            client_public_key_der_b64=created.client_public_key_der_b64,
            vendor_public_key_der_b64=created.vendor_public_key_der_b64,
            salt_b64=created.salt_b64,
            amount=created.amount,
            balance=created.balance,
            paytree_second_opt_root_b64=created.paytree_second_opt_root_b64,
            paytree_second_opt_unit_value=created.paytree_second_opt_unit_value,
            paytree_second_opt_max_i=created.paytree_second_opt_max_i,
        )

    async def settle_channel(
        self, channel_id: str, dto: PaytreeSecondOptSettlementRequestDTO
    ) -> CloseChannelResponseDTO:
        channel = await self.channel_repo.get_by_channel_id(channel_id)
        if not channel:
            raise ValueError("Payment channel not found")
        if channel.is_closed:
            raise ValueError("Payment channel already closed")
        if not isinstance(channel, PaytreeSecondOptPaymentChannel):
            raise ValueError("Payment channel is not PayTree Second Opt-enabled")

        if dto.vendor_public_key_der_b64 != channel.vendor_public_key_der_b64:
            raise ValueError("Mismatched vendor public key for channel")
        if dto.i > channel.paytree_second_opt_max_i:
            raise ValueError("i exceeds PayTree Second Opt max_i for this channel")

        settlement_payload = PaytreeSecondOptSettlementPayload(
            channel_id=channel_id,
            i=dto.i,
            leaf_b64=dto.leaf_b64,
            siblings_b64=dto.siblings_b64,
        )
        payload_bytes = payload_to_bytes(settlement_payload)
        vendor_public_key = load_public_key_from_der_b64(
            DERB64(channel.vendor_public_key_der_b64)
        )
        try:
            verify_signature_bytes(
                vendor_public_key, payload_bytes, dto.vendor_signature_b64
            )
        except InvalidSignature:
            raise ValueError(
                "Invalid vendor signature for PayTree Second Opt settlement"
            )

        try:
            _ = b64_to_bytes(channel.paytree_second_opt_root_b64)
        except Exception as e:
            raise ValueError(f"Invalid PayTree Second Opt root encoding: {e}") from e

        if not verify_paytree_proof(
            i=dto.i,
            leaf_b64=dto.leaf_b64,
            siblings_b64=dto.siblings_b64,
            root_b64=channel.paytree_second_opt_root_b64,
        ):
            raise ValueError("Invalid PayTree Second Opt proof (root mismatch)")

        cumulative_owed_amount = compute_cumulative_owed_amount(
            i=dto.i, unit_value=channel.paytree_second_opt_unit_value
        )
        if cumulative_owed_amount > channel.amount:
            raise ValueError("Invalid owed amount")

        vendor_acc = await self.account_repo.get_by_public_key(
            channel.vendor_public_key_der_b64
        )
        if not vendor_acc:
            vendor_acc = Account(
                public_key_der_b64=channel.vendor_public_key_der_b64, balance=0
            )
            await self.account_repo.upsert(vendor_acc)

        remainder = channel.amount - cumulative_owed_amount
        vendor_acc = await self.account_repo.update_balance(
            channel.vendor_public_key_der_b64, cumulative_owed_amount
        )
        try:
            client_acc = await self.account_repo.update_balance(
                channel.client_public_key_der_b64, remainder
            )
        except Exception:
            await self.account_repo.update_balance(
                channel.vendor_public_key_der_b64, -cumulative_owed_amount
            )
            raise

        try:
            await self.channel_repo.mark_closed(
                channel_id,
                close_payload_b64=None,
                client_close_signature_b64=None,
                amount=channel.amount,
                balance=cumulative_owed_amount,
                vendor_close_signature_b64=dto.vendor_signature_b64,
            )
        except Exception as close_err:
            rollback_errors: list[Exception] = []
            try:
                await self.account_repo.update_balance(
                    channel.vendor_public_key_der_b64, -cumulative_owed_amount
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
    ) -> PaytreeSecondOptPaymentChannelResponseDTO:
        channel = await self.channel_repo.get_by_channel_id(dto.channel_id)
        if not channel:
            raise ValueError("Payment channel not found")
        if not isinstance(channel, PaytreeSecondOptPaymentChannel):
            raise ValueError("Payment channel is not PayTree Second Opt-enabled")
        return PaytreeSecondOptPaymentChannelResponseDTO(**channel.model_dump())
