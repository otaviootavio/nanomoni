"""Use cases for the issuer application layer."""

from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from ..domain.issuer.entities import IssuerClient, Account
from ..domain.issuer.repositories import (
    IssuerClientRepository,
    AccountRepository,
)
from .issuer_dtos import (
    RegistrationRequestDTO,
    RegistrationCertificateDTO,
    IssuerPublicKeyDTO,
)

from ..crypto.certificates import (
    RegistrationCertificatePayload,
    issuer_issue_registration_certificate,
)


class IssuerService:
    """Service orchestrating issuer registration flow."""

    def __init__(
        self,
        client_repo: IssuerClientRepository,
        issuer_private_key_pem: str,
        account_repo: AccountRepository,
    ):
        self.client_repo = client_repo
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

    async def register(
        self, dto: RegistrationRequestDTO
    ) -> RegistrationCertificateDTO:
        # Register client with default balance 100 if not already present
        client = await self.client_repo.get_by_public_key(
            dto.client_public_key_der_b64
        )
        if not client:
            client = IssuerClient(
                public_key_der_b64=dto.client_public_key_der_b64, balance=100
            )
            await self.client_repo.create(client)

            # Ensure Account is created/updated to mirror IssuerClient balance
            account = Account(
                public_key_der_b64=client.public_key_der_b64,
                balance=client.balance,
            )
            await self.account_repo.upsert(account)

        # Generate and sign the certificate (not persisted on the client)
        certificate_payload = RegistrationCertificatePayload(
            client_public_key_der_b64=client.public_key_der_b64,
            balance=client.balance,
        )
        certificate_b64, certificate_signature_b64 = (
            issuer_issue_registration_certificate(
                self.issuer_private_key, certificate_payload
            )
        )

        return RegistrationCertificateDTO(
            client_public_key_der_b64=client.public_key_der_b64,
            balance=client.balance,
            certificate_b64=certificate_b64,
            certificate_signature_b64=certificate_signature_b64,
        )
