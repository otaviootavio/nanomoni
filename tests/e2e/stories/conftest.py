"""Shared fixtures for story tests."""

from __future__ import annotations

import pytest

from tests.e2e.helpers.issuer_client import IssuerTestClient
from tests.e2e.helpers.vendor_client import VendorTestClient


@pytest.fixture
def issuer_client(issuer_base_url: str, require_services: None) -> IssuerTestClient:
    """Provide an IssuerTestClient instance for story tests."""
    return IssuerTestClient(base_url=issuer_base_url)


@pytest.fixture
def vendor_client(vendor_base_url: str, require_services: None) -> VendorTestClient:
    """Provide a VendorTestClient instance for story tests."""
    return VendorTestClient(base_url=vendor_base_url)
