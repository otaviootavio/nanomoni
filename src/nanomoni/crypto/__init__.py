"""Shared cryptography utilities for Nanomoni.

This is the bottom layer: pure hashing and Merkle tree/index math. It must not
import from ``domain``, ``protocol``, ``application`` or any higher layer.
"""

from __future__ import annotations
