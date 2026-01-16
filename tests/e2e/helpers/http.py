"""Small HTTP helpers for E2E tests (aiohttp-based)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


class TestHttpStatusError(RuntimeError):
    """Raised when an HTTP response is not successful in E2E helper clients."""

    def __init__(self, response: "AiohttpResponse") -> None:
        self.response = response
        super().__init__(f"HTTP {response.status_code}: {response.text}")


@dataclass(frozen=True)
class AiohttpResponse:
    """Tiny response wrapper with a stable surface area used in tests."""

    status_code: int
    content: bytes

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        if not self.content:
            return None
        return json.loads(self.text)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise TestHttpStatusError(self)
