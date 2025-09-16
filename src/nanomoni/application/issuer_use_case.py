"""Use cases for the issuer application layer."""

from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from ..domain.issuer.entities import IssuerClient, IssuerChallenge, Account
from ..domain.issuer.repositories import (
    IssuerClientRepository,
    IssuerChallengeRepository,
    AccountRepository,
)
from .issuer_dtos import (
    StartRegistrationRequestDTO,
    StartRegistrationResponseDTO,
    CompleteRegistrationRequestDTO,
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
        challenge_repo: IssuerChallengeRepository,
        issuer_private_key_pem: str,
        account_repo: AccountRepository,
    ):
        self.client_repo = client_repo
        self.challenge_repo = challenge_repo
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

    async def start_registration(
        self, dto: StartRegistrationRequestDTO
    ) -> StartRegistrationResponseDTO:
        # Create a challenge nonce
        nonce = os.urandom(32)
        nonce_b64 = base64.b64encode(nonce).decode("utf-8")
        challenge = IssuerChallenge(
            client_public_key_der_b64=dto.client_public_key_der_b64,
            nonce_b64=nonce_b64,
        )
        created = await self.challenge_repo.create(challenge)
        return StartRegistrationResponseDTO(
            challenge_id=created.id, nonce_b64=nonce_b64
        )

    async def complete_registration(
        self, dto: CompleteRegistrationRequestDTO
    ) -> RegistrationCertificateDTO:
        # Load challenge
        challenge = await self.challenge_repo.get_by_id(dto.challenge_id)
        if not challenge:
            raise ValueError("Challenge not found or expired")

        # Verify signature over nonce using provided client public key
        client_pk_der = base64.b64decode(challenge.client_public_key_der_b64)
        public_key = serialization.load_der_public_key(client_pk_der)
        signature_bytes = base64.b64decode(dto.signature_der_b64)
        nonce_bytes = base64.b64decode(challenge.nonce_b64)

        try:
            public_key.verify(signature_bytes, nonce_bytes, ec.ECDSA(hashes.SHA256()))
        except InvalidSignature:
            raise ValueError("Invalid signature for challenge")

        # Register client with default balance 100 if not already present
        client = await self.client_repo.get_by_public_key(
            challenge.client_public_key_der_b64
        )
        if not client:
            client = IssuerClient(
                public_key_der_b64=challenge.client_public_key_der_b64, balance=100
            )
            await self.client_repo.create(client)

        # Ensure Account is created/updated to mirror IssuerClient balance
        existing_account = await self.account_repo.get_by_public_key(
            client.public_key_der_b64
        )
        if existing_account is not None:
            raise ValueError(
                "Account already registered; refusing to overwrite existing balance"
            )

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

        # Remove challenge (one-time use)
        await self.challenge_repo.delete(challenge.id)

        return RegistrationCertificateDTO(
            client_public_key_der_b64=client.public_key_der_b64,
            balance=client.balance,
            certificate_b64=certificate_b64,
            certificate_signature_b64=certificate_signature_b64,
        )
