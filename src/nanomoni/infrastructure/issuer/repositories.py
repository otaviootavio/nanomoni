"""Issuer-related SQLite repository implementations."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from ...domain.issuer.entities import IssuerClient, IssuerChallenge
from ...domain.issuer.repositories import (
    IssuerClientRepository,
    IssuerChallengeRepository,
)
from ..database import DatabaseClient


class SQLiteIssuerClientRepository(IssuerClientRepository):
    """SQLite implementation for issuer clients."""

    def __init__(self, db_client: DatabaseClient):
        self.db_client = db_client

    async def create(self, client: IssuerClient) -> IssuerClient:
        async with self.db_client.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO issuer_clients (id, public_key_der_b64, balance, created_at)
                VALUES (?, ?, ?, ?)
            """,
                (
                    str(client.id),
                    client.public_key_der_b64,
                    client.balance,
                    client.created_at.isoformat(),
                ),
            )
            conn.commit()
            return client

    async def get_by_public_key(
        self, public_key_der_b64: str
    ) -> Optional[IssuerClient]:
        async with self.db_client.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM issuer_clients WHERE public_key_der_b64 = ?",
                (public_key_der_b64,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return IssuerClient(
                id=UUID(row["id"]),
                public_key_der_b64=row["public_key_der_b64"],
                balance=int(row["balance"]),
                created_at=datetime.fromisoformat(row["created_at"]),
            )


class SQLiteIssuerChallengeRepository(IssuerChallengeRepository):
    """SQLite implementation for issuer challenges."""

    def __init__(self, db_client: DatabaseClient):
        self.db_client = db_client

    async def create(self, challenge: IssuerChallenge) -> IssuerChallenge:
        async with self.db_client.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO issuer_challenges (id, client_public_key_der_b64, nonce_b64, created_at)
                VALUES (?, ?, ?, ?)
            """,
                (
                    str(challenge.id),
                    challenge.client_public_key_der_b64,
                    challenge.nonce_b64,
                    challenge.created_at.isoformat(),
                ),
            )
            conn.commit()
            return challenge

    async def get_by_id(self, challenge_id: UUID) -> Optional[IssuerChallenge]:
        async with self.db_client.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM issuer_challenges WHERE id = ?",
                (str(challenge_id),),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return IssuerChallenge(
                id=UUID(row["id"]),
                client_public_key_der_b64=row["client_public_key_der_b64"],
                nonce_b64=row["nonce_b64"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )

    async def delete(self, challenge_id: UUID) -> bool:
        async with self.db_client.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM issuer_challenges WHERE id = ?", (str(challenge_id),)
            )
            conn.commit()
            return cursor.rowcount > 0
