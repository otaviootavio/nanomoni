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

    async def upsert(self, account: Account) -> Account:
        """
        Store accounts keyed directly by their public key to avoid an extra
        indirection (pk -> id -> entity).

        Key layout:
          - account:{public_key_der_b64} -> Account JSON
        """
        account_key = f"account:{account.public_key_der_b64}"
        await self.store.set(account_key, account.model_dump_json())
        # Return the stored/normalized representation
        stored_raw = await self.store.get(account_key)
        return (
            account if stored_raw is None else Account.model_validate_json(stored_raw)
        )

    async def get_by_public_key(self, public_key_der_b64: str) -> Optional[Account]:
        account_key = f"account:{public_key_der_b64}"
        data = await self.store.get(account_key)
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
