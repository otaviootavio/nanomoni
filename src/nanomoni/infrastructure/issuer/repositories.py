"""Issuer repositories implemented over a storage abstraction."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from ...domain.issuer.entities import (
    Account,
    PaymentChannel,
)
from ...domain.issuer.repositories import (
    AccountRepository,
    PaymentChannelRepository,
)
from ..storage import KeyValueStore


class AccountRepositoryImpl(AccountRepository):
    """Account repository backed by KeyValueStore."""

    def __init__(self, store: KeyValueStore):
        self.store = store

    @staticmethod
    def _pk_key(public_key_der_b64: str) -> str:
        return f"account:pk:{public_key_der_b64}"

    async def upsert(self, account: Account) -> Account:
        pk_key = self._pk_key(account.public_key_der_b64)
        account_id = await self.store.get(pk_key)
        # Always store entity keyed by id and index by pk
        account_key = f"account:{account.id if account_id is None else account_id}"
        if account_id is None:
            await self.store.set(pk_key, str(account.id))
            account_key = f"account:{account.id}"
        await self.store.set(account_key, account.model_dump_json())
        return (
            account
            if account_id is None
            else Account.model_validate_json(
                await self.store.get(account_key)  # type: ignore[arg-type]
            )
        )

    async def get_by_public_key(self, public_key_der_b64: str) -> Optional[Account]:
        pk_key = self._pk_key(public_key_der_b64)
        account_id = await self.store.get(pk_key)
        if not account_id:
            return None
        data = await self.store.get(f"account:{account_id}")
        if not data:
            return None
        return Account.model_validate_json(data)

    async def update_balance(self, public_key_der_b64: str, delta: int) -> Account:
        account = await self.get_by_public_key(public_key_der_b64)
        if not account:
            # Create account if not exists
            account = Account(public_key_der_b64=public_key_der_b64, balance=0)
        new_balance = account.balance + delta
        if new_balance < 0:
            raise ValueError("Insufficient balance")
        account.balance = new_balance
        await self.upsert(account)
        return account


class PaymentChannelRepositoryImpl(PaymentChannelRepository):
    """Payment channel repository backed by KeyValueStore."""

    def __init__(self, store: KeyValueStore):
        self.store = store

    @staticmethod
    def _channel_key_by_id(channel_id: UUID) -> str:
        return f"payment_channel:{channel_id}"

    @staticmethod
    def _computed_id_key(computed_id: str) -> str:
        return f"payment_channel:computed:{computed_id}"

    async def create(self, channel: PaymentChannel) -> PaymentChannel:
        # store by id
        await self.store.set(
            self._channel_key_by_id(channel.id), channel.model_dump_json()
        )
        # index by computed id
        await self.store.set(
            self._computed_id_key(channel.computed_id), str(channel.id)
        )
        return channel

    async def get_by_computed_id(self, computed_id: str) -> Optional[PaymentChannel]:
        channel_id = await self.store.get(self._computed_id_key(computed_id))
        if not channel_id:
            return None
        data = await self.store.get(self._channel_key_by_id(UUID(channel_id)))
        if not data:
            return None
        return PaymentChannel.model_validate_json(data)

    async def mark_closed(
        self,
        computed_id: str,
        close_payload_b64: str,
        client_close_signature_b64: str,
        *,
        amount: int,
        balance: int,
        vendor_close_signature_b64: str,
    ) -> PaymentChannel:
        existing = await self.get_by_computed_id(computed_id)
        if not existing:
            raise ValueError("Payment channel not found")
        if existing.is_closed:
            return existing
        existing.is_closed = True
        existing.close_payload_b64 = close_payload_b64
        existing.client_close_signature_b64 = client_close_signature_b64
        existing.vendor_close_signature_b64 = vendor_close_signature_b64
        from datetime import datetime, timezone

        existing.closed_at = datetime.now(timezone.utc)
        existing.amount = amount
        existing.balance = balance
        await self.store.set(
            self._channel_key_by_id(existing.id), existing.model_dump_json()
        )
        return existing
