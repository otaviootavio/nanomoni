"""Account repository implementation."""

from __future__ import annotations

from typing import Optional

from ...domain.issuer.entities import Account
from ...domain.issuer.repositories import AccountRepository
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
