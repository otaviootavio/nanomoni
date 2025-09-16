from __future__ import annotations

import base64
import hashlib
import json
import os
from cryptography.exceptions import InvalidSignature

from ....domain.issuer.entities import (
    PaymentChannel,
    Account,
    PaymentChannelCertificatePayload,
)
from ....domain.issuer.repositories import (
    PaymentChannelRepository,
    AccountRepository,
)
from ...issuer_dtos import (
    OpenChannelRequestDTO,
    OpenChannelResponseDTO,
    CloseChannelRequestDTO,
    CloseChannelResponseDTO,
    GetPaymentChannelRequestDTO,
    PaymentChannelResponseDTO,
)
from ....crypto.certificates import (
    load_public_key_der_b64,
    verify_certificate,
    PayChanCertificatePayload,
    issuer_issue_paychan_certificate_envelope,
    load_private_key_pem,
)


class PaymentChannelService:
    """Service to manage opening and closing payment channels."""

    def __init__(
        self,
        account_repo: AccountRepository,
        channel_repo: PaymentChannelRepository,
        issuer_private_key_pem: str,
    ):
        self.account_repo = account_repo
        self.channel_repo = channel_repo
        self.issuer_private_key = load_private_key_pem(issuer_private_key_pem)

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
        # Ensure both accounts exist (no implicit creation here)
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
            raise ValueError("amount must be positive")
        if client_acc.balance < dto.amount:
            raise ValueError("Insufficient client balance to lock funds")

        # Verify client's intent: signature over canonicalized open request
        client_public_key = load_public_key_der_b64(dto.client_public_key_der_b64)
        open_payload = {
            "client_public_key_der_b64": dto.client_public_key_der_b64,
            "vendor_public_key_der_b64": dto.vendor_public_key_der_b64,
            "amount": dto.amount,
        }
        try:
            verify_certificate(
                client_public_key, open_payload, dto.client_signature_b64
            )
        except InvalidSignature:
            raise ValueError("Invalid client signature for open channel request")

        # Generate salt server-side
        salt_bytes = os.urandom(32)
        salt_b64 = base64.b64encode(salt_bytes).decode("utf-8")

        computed_id = self._compute_channel_id(
            dto.client_public_key_der_b64,
            dto.vendor_public_key_der_b64,
            salt_b64,
        )

        existing = await self.channel_repo.get_by_computed_id(computed_id)
        if existing and not existing.is_closed:
            raise ValueError("Payment channel already open")

        # Deduct funds from client (lock)
        await self.account_repo.update_balance(
            dto.client_public_key_der_b64, -dto.amount
        )

        channel = PaymentChannel(
            computed_id=computed_id,
            client_public_key_der_b64=dto.client_public_key_der_b64,
            vendor_public_key_der_b64=dto.vendor_public_key_der_b64,
            salt_b64=salt_b64,
            amount=dto.amount,
            balance=0,
        )
        created = await self.channel_repo.create(channel)

        # Issue a typed paychan certificate (signed by issuer) to the client
        paychan_payload = PayChanCertificatePayload(
            computed_id=computed_id,
            amount=dto.amount,
            balance=0,
            vendor_public_key_der_b64=dto.vendor_public_key_der_b64,
            client_public_key_der_b64=dto.client_public_key_der_b64,
        )
        paychan_certificate_b64, paychan_signature_b64 = (
            issuer_issue_paychan_certificate_envelope(
                self.issuer_private_key, paychan_payload
            )
        )

        return OpenChannelResponseDTO(
            channel_id=created.id,
            computed_id=created.computed_id,
            salt_b64=created.salt_b64,
            amount=created.amount,
            balance=created.balance,
            paychan_certificate_b64=paychan_certificate_b64,
            paychan_signature_b64=paychan_signature_b64,
        )

    async def close_channel(
        self, dto: CloseChannelRequestDTO
    ) -> CloseChannelResponseDTO:
        channel = await self.channel_repo.get_by_computed_id(dto.computed_id)
        if not channel:
            raise ValueError("Payment channel not found")
        if channel.is_closed:
            raise ValueError("Payment channel already closed")

        # Decode and validate certificate payload JSON, then verify signature
        certificate_bytes = base64.b64decode(dto.closing_certificate_b64)
        try:
            payload_dict = json.loads(certificate_bytes.decode("utf-8"))
        except Exception:
            raise ValueError("Invalid certificate payload format")

        try:
            payload = PaymentChannelCertificatePayload(**payload_dict)
        except Exception:
            raise ValueError("Certificate payload missing required fields")

        if payload.computed_id != dto.computed_id:
            raise ValueError("Certificate computed_id mismatch")
        if payload.amount != dto.owed_amount:
            raise ValueError("Certificate amount mismatch")

        # Verify client signature over canonical payload
        client_public_key = load_public_key_der_b64(dto.client_public_key_der_b64)
        try:
            verify_certificate(
                client_public_key, payload.model_dump(), dto.closing_signature_b64
            )
        except InvalidSignature:
            raise ValueError("Invalid closing certificate signature")

        # Verify vendor signature (intent to close)
        vendor_public_key = load_public_key_der_b64(dto.vendor_public_key_der_b64)
        try:
            verify_certificate(
                vendor_public_key, payload.model_dump(), dto.vendor_signature_b64
            )
        except InvalidSignature:
            raise ValueError("Invalid vendor signature for closing")

        if dto.owed_amount < 0 or dto.owed_amount > channel.amount:
            raise ValueError("Invalid owed amount")

        # Ensure vendor account exists
        vendor_acc = await self.account_repo.get_by_public_key(
            dto.vendor_public_key_der_b64
        )
        if not vendor_acc:
            vendor_acc = Account(
                public_key_der_b64=dto.vendor_public_key_der_b64, balance=0
            )
            await self.account_repo.upsert(vendor_acc)

        # Pay vendor owed_amount
        vendor_acc = await self.account_repo.update_balance(
            dto.vendor_public_key_der_b64, dto.owed_amount
        )
        # Return the remainder to client
        remainder = channel.amount - dto.owed_amount
        client_acc = await self.account_repo.update_balance(
            dto.client_public_key_der_b64, remainder
        )

        # Mark channel closed and persist the closing certificate, updating channel amounts
        await self.channel_repo.mark_closed(
            dto.computed_id,
            dto.closing_certificate_b64,
            amount=dto.owed_amount,
            balance=dto.owed_amount,
            vendor_signature_b64=dto.vendor_signature_b64,
        )

        return CloseChannelResponseDTO(
            computed_id=dto.computed_id,
            client_balance=client_acc.balance,
            vendor_balance=vendor_acc.balance,
        )

    async def get_channel(
        self, dto: GetPaymentChannelRequestDTO
    ) -> PaymentChannelResponseDTO:
        channel = await self.channel_repo.get_by_computed_id(dto.computed_id)
        if not channel:
            raise ValueError("Payment channel not found")
        return PaymentChannelResponseDTO(
            channel_id=channel.id,
            computed_id=channel.computed_id,
            salt_b64=channel.salt_b64,
            amount=channel.amount,
            balance=channel.balance,
        )
