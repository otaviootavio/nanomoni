"""Shared domain utilities.

This package is domain-accessible and should not depend on application code.
"""

from .issuer_client_protocol import IssuerClientProtocol, IssuerClientFactory

__all__ = ["IssuerClientProtocol", "IssuerClientFactory"]
