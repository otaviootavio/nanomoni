"""PayTree Second Opt domain repository interface."""

from __future__ import annotations

from abc import abstractmethod
from typing import Optional

from .entities import PaytreeSecondOptPaymentChannel, PaytreeSecondOptState
from .payment_channel_repository_base import PaymentChannelRepositoryBase


class PaytreeSecondOptRepository(PaymentChannelRepositoryBase):
    """Repository interface for PayTree Second Opt payment channels."""

    @abstractmethod
    async def get_paytree_second_opt_state(
        self, channel_id: str
    ) -> Optional[PaytreeSecondOptState]:
        """Get the latest PayTree Second Opt state for this channel."""
        pass

    @abstractmethod
    async def get_paytree_second_opt_channel_and_latest_state(
        self, channel_id: str
    ) -> tuple[
        Optional[PaytreeSecondOptPaymentChannel], Optional[PaytreeSecondOptState]
    ]:
        """Get PayTree Second Opt channel metadata and latest state in one call."""
        pass

    @abstractmethod
    async def get_paytree_second_opt_channel_state_and_sibling_cache(
        self, *, channel_id: str, i: int, max_i: int
    ) -> tuple[
        Optional[PaytreeSecondOptPaymentChannel],
        Optional[PaytreeSecondOptState],
        dict[str, str],
    ]:
        """
        Get channel metadata, latest state, and per-index sibling cache in one call.
        """
        pass

    @abstractmethod
    async def save_paytree_second_opt_payment(
        self,
        channel: PaytreeSecondOptPaymentChannel,
        new_state: PaytreeSecondOptState,
        node_entries: dict[str, str],
    ) -> tuple[int, Optional[PaytreeSecondOptState]]:
        """
        Atomically update the channel's latest PayTree Second Opt state.
        """
        pass

    @abstractmethod
    async def save_channel_and_initial_paytree_second_opt_state(
        self,
        channel: PaytreeSecondOptPaymentChannel,
        initial_state: PaytreeSecondOptState,
        node_entries: dict[str, str],
    ) -> tuple[int, Optional[PaytreeSecondOptState]]:
        """
        Atomically save channel metadata AND the first PayTree Second Opt state.
        """
        pass

    @abstractmethod
    async def get_paytree_second_opt_sibling_cache_for_index(
        self,
        *,
        channel_id: str,
        i: int,
        max_i: int,
        trusted_level: Optional[int] = None,
    ) -> dict[str, str]:
        """Load per-index sibling cache entries needed for proof reconstruction."""
        pass

    @abstractmethod
    async def get_paytree_second_opt_siblings_for_settlement(
        self, *, channel_id: str, i: int, max_i: int
    ) -> list[str]:
        """Load full sibling list from per-node storage for settlement."""
        pass
