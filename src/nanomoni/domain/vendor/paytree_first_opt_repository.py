"""PayTree First Opt domain repository interface."""

from __future__ import annotations

from abc import abstractmethod
from typing import Optional

from .entities import PaytreeFirstOptPaymentChannel, PaytreeFirstOptState
from .payment_channel_repository_base import PaymentChannelRepositoryBase


class PaytreeFirstOptRepository(PaymentChannelRepositoryBase):
    """Repository interface for PayTree First Opt payment channels."""

    @abstractmethod
    async def get_paytree_first_opt_state(
        self, channel_id: str
    ) -> Optional[PaytreeFirstOptState]:
        """Get the latest PayTree First Opt state for this channel."""
        pass

    @abstractmethod
    async def get_paytree_first_opt_channel_state_and_sibling_cache(
        self,
        *,
        channel_id: str,
        i: int,
        max_i: int,
        siblings_count: int,
    ) -> tuple[
        Optional[PaytreeFirstOptPaymentChannel],
        Optional[PaytreeFirstOptState],
        dict[str, str],
    ]:
        """
        Get channel metadata, latest state, and per-index sibling cache in one call.
        """
        pass

    @abstractmethod
    async def save_paytree_first_opt_payment(
        self,
        channel: PaytreeFirstOptPaymentChannel,
        new_state: PaytreeFirstOptState,
        node_entries: dict[str, str],
    ) -> tuple[int, Optional[PaytreeFirstOptState]]:
        """
        Atomically update the channel's latest PayTree First Opt state.
        """
        pass

    @abstractmethod
    async def save_channel_and_initial_paytree_first_opt_state(
        self,
        channel: PaytreeFirstOptPaymentChannel,
        initial_state: PaytreeFirstOptState,
        node_entries: dict[str, str],
    ) -> tuple[int, Optional[PaytreeFirstOptState]]:
        """
        Atomically save channel metadata AND the first PayTree First Opt state.
        """
        pass

    @abstractmethod
    async def get_paytree_first_opt_siblings_for_settlement(
        self, *, channel_id: str, i: int, max_i: int
    ) -> list[str]:
        """Load full sibling list from per-node storage for settlement."""
        pass
