from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class ProofReference:
    """Opaque ordinal reference to a payment step.

    The domain compares values ordinally (>, <=) but never interprets
    the value as a leaf index or hash-chain counter — that meaning lives
    in the crypto layer only.
    """

    value: int


class PaymentScheme(str, Enum):
    PAYWORD = "payword"
    PAYTREE = "paytree"
    PAYTREE_CHILD_PAIR = "paytree_child_pair"
