"""PaymentRepository — unified repository interface for proof-based payment channels."""

from __future__ import annotations

from typing import Optional, Protocol

from .entities import PaymentChannel, PaymentChannelBase, PaymentState
from ...crypto.scheme import CryptoProof


class PaymentRepository(Protocol):
    async def get_channel(self, channel_id: str) -> Optional[PaymentChannel]: ...

    async def get_state(self, channel_id: str) -> Optional[PaymentState]: ...

    async def get_channel_and_state(
        self, channel_id: str
    ) -> tuple[Optional[PaymentChannel], Optional[PaymentState]]: ...

    async def save_payment(
        self,
        channel: PaymentChannel,
        new_state: PaymentState,
        proof: CryptoProof,
    ) -> tuple[int, Optional[PaymentState]]:
        """Save a payment atomically.

        Returns (status, state_or_None):
          1 = success
          0 = stale/not-increasing (returns current state)
          2 = channel missing in vendor cache
          3 = capacity exceeded (proof_reference > max_steps)
        """
        ...

    async def save_channel_and_initial_state(
        self,
        channel: PaymentChannel,
        state: PaymentState,
        proof: CryptoProof,
    ) -> tuple[int, Optional[PaymentState]]:
        """Atomically write channel + first payment state + proof.

        Returns same status codes as save_payment.
        """
        ...

    async def get_crypto_proof_raw(self, channel_id: str) -> Optional[str]:
        """Return the raw JSON of the latest stored CryptoProof, or None."""
        ...

    async def mark_closed(
        self,
        channel_id: str,
        *,
        amount: int,
        balance: int,
    ) -> PaymentChannelBase: ...
