from __future__ import annotations

from typing import Any, Dict, Optional, Type
from types import TracebackType

from ...application.vendor.dtos import CloseChannelDTO
from ..http.http_client import HttpClient
from ...crypto.certificates import Envelope


class VendorClient:
    """Synchronous client for talking to the Vendor HTTP API."""

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        # vendor_base_url is expected to already contain any API prefix (e.g. /api/v1)
        self._http = HttpClient(base_url, timeout=timeout)

    def get_vendor_public_key(self) -> str:
        """Fetch the vendor's public key (DER b64) from the vendor API."""
        resp = self._http.get("/vendor/keys/public")
        data = resp.json()
        return data["public_key_der_b64"]

    def send_off_chain_payment(
        self,
        computed_id: str,
        envelope: Envelope,
    ) -> Dict[str, Any]:
        """Send an off-chain payment envelope to the vendor."""
        payload = {
            "envelope": {
                "payload_b64": envelope.payload_b64,
                "signature_b64": envelope.signature_b64,
            }
        }
        path = f"/vendor/channels/{computed_id}/payments"
        resp = self._http.post(path, json=payload)
        return resp.json()

    def request_close_channel(self, dto: CloseChannelDTO) -> None:
        """Ask the vendor to close a payment channel."""
        path = f"/vendor/channels/{dto.computed_id}/closure-requests"
        self._http.post(path, json=dto.model_dump())

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "VendorClient":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.close()
