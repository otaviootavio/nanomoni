"""Use cases for the issuer PayTree (Merkle tree) flow."""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ec

from ....application.issuer.dtos import OpenChannelRequestDTO
from ....application.issuer.dtos import (
    CloseChannelResponseDTO,
    GetPaymentChannelRequestDTO,
)
from ....application.issuer.paytree_dtos import (
    PaytreeOpenChannelResponseDTO,
    PaytreePaymentChannelResponseDTO,
    PaytreeSettlementRequestDTO,
)
from ....application.shared.paytree_payloads import (
    PaytreeOpenChannelRequestPayload,
    PaytreeSettlementPayload,
)
from ....application.shared.serialization import payload_to_bytes
from ....crypto.certificates import (
    DERB64,
    Envelope,
    PayloadB64,
    SignatureB64,
    json_to_bytes,
    load_public_key_from_der_b64,
    verify_envelope_and_get_payload_bytes,
    verify_signature_bytes,
)
from ....crypto.paytree import (
    b64_to_bytes,
    compute_cumulative_owed_amount,
    verify_paytree_proof,
)
from ....domain.issuer.entities import Account, PaymentChannel
from ....domain.issuer.repositories import AccountRepository, PaymentChannelRepository


class PaytreeChannelService:
    """Service to manage opening and settling PayTree-enabled payment channels."""

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

    async def open_channel(
        self, dto: OpenChannelRequestDTO
    ) -> PaytreeOpenChannelResponseDTO:
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

        open_req_payload = PaytreeOpenChannelRequestPayload.model_validate_json(
            payload_bytes.decode("utf-8")
        )

        if open_req_payload.client_public_key_der_b64 != dto.client_public_key_der_b64:
            raise ValueError("Mismatched client public key between field and payload")

        client_acc = await self.account_repo.get_by_public_key(
            open_req_payload.client_public_key_der_b64
        )
        if not client_acc:
            raise ValueError("Client account not registered")

        vendor_acc = await self.account_repo.get_by_public_key(
            open_req_payload.vendor_public_key_der_b64
        )
        if not vendor_acc:
            raise ValueError("Vendor account not registered")

        if open_req_payload.amount <= 0:
            raise ValueError("Amount must be positive")
        if client_acc.balance < open_req_payload.amount:
            raise ValueError("Insufficient client balance to lock funds")

        paytree_hash_alg = open_req_payload.paytree_hash_alg or "sha256"
        if paytree_hash_alg != "sha256":
            raise ValueError("Unsupported PayTree hash algorithm")

        try:
            _ = b64_to_bytes(open_req_payload.paytree_root_b64)
        except Exception as e:
            raise ValueError(f"Invalid paytree_root_b64: {e}") from e

        max_owed = compute_cumulative_owed_amount(
            i=open_req_payload.paytree_max_i,
            unit_value=open_req_payload.paytree_unit_value,
        )
        if max_owed > open_req_payload.amount:
            raise ValueError(
                "PayTree max owed exceeds channel amount "
                f"(max_owed={max_owed}, amount={open_req_payload.amount})"
            )

        salt_bytes = os.urandom(32)
        salt_b64 = base64.b64encode(salt_bytes).decode("utf-8")
        channel_id = self._compute_channel_id(
            open_req_payload.client_public_key_der_b64,
            open_req_payload.vendor_public_key_der_b64,
            salt_b64,
        )

        existing = await self.channel_repo.get_by_channel_id(channel_id)
        if existing and not existing.is_closed:
            raise ValueError("Payment channel already open")

        channel = PaymentChannel(
            channel_id=channel_id,
            client_public_key_der_b64=open_req_payload.client_public_key_der_b64,
            vendor_public_key_der_b64=open_req_payload.vendor_public_key_der_b64,
            salt_b64=salt_b64,
            amount=open_req_payload.amount,
            balance=0,
            paytree_root_b64=open_req_payload.paytree_root_b64,
            paytree_unit_value=open_req_payload.paytree_unit_value,
            paytree_max_i=open_req_payload.paytree_max_i,
            paytree_hash_alg=paytree_hash_alg,
        )
        created = await self.channel_repo.create(channel)

        # Deduct funds only after the channel is persisted. If the balance update
        # fails for any reason, attempt to roll back by deleting the channel.
        try:
            await self.account_repo.update_balance(
                open_req_payload.client_public_key_der_b64, -open_req_payload.amount
            )
        except Exception:
            await self.channel_repo.delete_by_channel_id(channel_id)
            raise

        if (
            created.paytree_root_b64 is None
            or created.paytree_unit_value is None
            or created.paytree_max_i is None
        ):
            raise RuntimeError("Unexpected: persisted PayTree fields are missing")

        return PaytreeOpenChannelResponseDTO(
            channel_id=created.channel_id,
            client_public_key_der_b64=created.client_public_key_der_b64,
            vendor_public_key_der_b64=created.vendor_public_key_der_b64,
            salt_b64=created.salt_b64,
            amount=created.amount,
            balance=created.balance,
            paytree_root_b64=created.paytree_root_b64,
            paytree_unit_value=created.paytree_unit_value,
            paytree_max_i=created.paytree_max_i,
            paytree_hash_alg=created.paytree_hash_alg or "sha256",
        )

    async def settle_channel(
        self, channel_id: str, dto: PaytreeSettlementRequestDTO
    ) -> CloseChannelResponseDTO:
        channel = await self.channel_repo.get_by_channel_id(channel_id)
        if not channel:
            raise ValueError("Payment channel not found")
        if channel.is_closed:
            raise ValueError("Payment channel already closed")

        if dto.vendor_public_key_der_b64 != channel.vendor_public_key_der_b64:
            raise ValueError("Mismatched vendor public key for channel")

        if (
            channel.paytree_root_b64 is None
            or channel.paytree_unit_value is None
            or channel.paytree_max_i is None
        ):
            raise ValueError("Payment channel is not PayTree-enabled")

        paytree_hash_alg = channel.paytree_hash_alg or "sha256"
        if paytree_hash_alg != "sha256":
            raise ValueError("Unsupported PayTree hash algorithm")

        if dto.i > channel.paytree_max_i:
            raise ValueError("i exceeds PayTree max_i for this channel")

        settlement_payload = PaytreeSettlementPayload(
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
            raise ValueError("Invalid vendor signature for PayTree settlement")

        # Validate root encoding (verify_paytree_proof will also validate, but this gives clearer error)
        try:
            _ = b64_to_bytes(channel.paytree_root_b64)
        except Exception as e:
            raise ValueError(f"Invalid PayTree root encoding: {e}") from e

        if not verify_paytree_proof(
            i=dto.i,
            leaf_b64=dto.leaf_b64,
            siblings_b64=dto.siblings_b64,
            root_b64=channel.paytree_root_b64,
        ):
            raise ValueError("Invalid PayTree proof (root mismatch)")

        cumulative_owed_amount = compute_cumulative_owed_amount(
            i=dto.i, unit_value=channel.paytree_unit_value
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
        # The following three operations must behave transactionally:
        # 1) credit vendor, 2) refund client remainder, 3) mark channel closed.
        # If any step fails, roll back prior balance changes before propagating
        # the error to avoid leaving inconsistent balances.
        vendor_acc = await self.account_repo.update_balance(
            channel.vendor_public_key_der_b64, cumulative_owed_amount
        )
        try:
            client_acc = await self.account_repo.update_balance(
                channel.client_public_key_der_b64, remainder
            )
        except Exception:
            # Roll back vendor credit if client refund fails.
            await self.account_repo.update_balance(
                channel.vendor_public_key_der_b64, -cumulative_owed_amount
            )
            raise

        try:
            await self.channel_repo.mark_closed(
                channel_id,
                close_payload_b64="",
                client_close_signature_b64="",
                amount=channel.amount,
                balance=cumulative_owed_amount,
                vendor_close_signature_b64=dto.vendor_signature_b64,
            )
        except Exception as close_err:
            # Roll back both balance updates if closing persistence fails.
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
    ) -> PaytreePaymentChannelResponseDTO:
        channel = await self.channel_repo.get_by_channel_id(dto.channel_id)
        if not channel:
            raise ValueError("Payment channel not found")

        if (
            channel.paytree_root_b64 is None
            or channel.paytree_unit_value is None
            or channel.paytree_max_i is None
        ):
            raise ValueError("Payment channel is not PayTree-enabled")

        data = channel.model_dump()
        return PaytreePaymentChannelResponseDTO(**data)
