"""Exceptions for PayTree first-opt protocol."""

from __future__ import annotations


class NoSubTreeForSubPathError(Exception):
    """Raised when the verifier has no sub-root in repo for the given sub-proof."""

    pass
