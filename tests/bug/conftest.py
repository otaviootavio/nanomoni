"""Shared pytest fixtures for bug demonstration tests.

These tests require external services (Issuer, Vendor, Redis) to be running.
"""

from __future__ import annotations

# Import the require_services fixture from e2e conftest
from tests.e2e.conftest import require_services  # noqa: F401

# The fixture is now available to all tests in this directory
