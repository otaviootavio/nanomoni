"""Shared fixtures for story tests."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


@pytest.fixture
def issuer_client() -> IssuerTestClient:
    """Provide an IssuerTestClient instance for story tests."""
    return IssuerTestClient()


@pytest.fixture
def vendor_client() -> VendorTestClient:
    """Provide a VendorTestClient instance for story tests."""
    return VendorTestClient()

