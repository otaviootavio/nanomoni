"""Domain-specific exceptions."""

from __future__ import annotations


class AccountNotFoundError(Exception):
    """Raised when an account lookup fails."""
