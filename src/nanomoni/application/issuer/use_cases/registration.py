"""Use cases for the issuer application layer."""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization

from ....domain.issuer.entities import Account
from ....domain.issuer.repositories import (
    AccountRepository,
)
from ..dtos import (
    RegistrationRequestDTO,
    RegistrationResponseDTO,
    IssuerPublicKeyDTO,
)


class RegistrationService:
    """Service orchestrating issuer registration flow."""

    def __init__(
        self,
        issuer_private_key_pem: str,
        account_repo: AccountRepository,
    ):
        self.account_repo = account_repo
        self.issuer_private_key = serialization.load_pem_private_key(
            issuer_private_key_pem.encode(), password=None
        )

    def get_issuer_public_key(self) -> IssuerPublicKeyDTO:
        public_key = self.issuer_private_key.public_key()

        der = public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        der_b64 = base64.b64encode(der).decode("utf-8")
        return IssuerPublicKeyDTO(der_b64=der_b64)

    async def register(self, dto: RegistrationRequestDTO) -> RegistrationResponseDTO:
        # Register client with default balance 1000000 if not already present
        account = await self.account_repo.get_by_public_key(
            dto.client_public_key_der_b64
        )
        if not account:
            account = Account(
                public_key_der_b64=dto.client_public_key_der_b64, balance=10_000_000
            )
            await self.account_repo.upsert(account)

        return RegistrationResponseDTO(
            client_public_key_der_b64=account.public_key_der_b64,
            balance=account.balance,
        )

    async def get_account(self, public_key_der_b64: str) -> RegistrationResponseDTO:
        """
        Fetch an existing account by public key.

        Note: The RegistrationResponseDTO field name is historical; it is used for both
        client and vendor accounts in this codebase.
        """
        account = await self.account_repo.get_by_public_key(public_key_der_b64)
        if not account:
            raise ValueError("Account not found")
        return RegistrationResponseDTO(
            client_public_key_der_b64=account.public_key_der_b64,
            balance=account.balance,
        )
