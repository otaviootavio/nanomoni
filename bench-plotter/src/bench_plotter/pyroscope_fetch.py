"""Fetch a merged CPU profile from Pyroscope's HTTP render API.

Pyroscope's ``/pyroscope/render`` selector puts the profile type as the
leading (metric) name, not a label -- ``{service_name="...",
profile_type="..."}`` (as shown in the Pyroscope UI) must be sent as
``process_cpu:...{service_name="..."}``. ``format=json`` returns a
"flamebearer" payload: a merged call tree over ``[from, until]``, not a time
series. Flamebearer decoding lives in :mod:`bench_plotter.flamebearer`.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import httpx

from bench_plotter.settings import pyroscope_base_url


async def render(
    *,
    query: str,
    start_unix: float,
    end_unix: float,
    base_url: str | None = None,
) -> dict[str, Any]:
    base = (base_url or pyroscope_base_url()).rstrip("/")
    params = {
        "query": query,
        "from": str(int(start_unix)),
        "until": str(int(end_unix)),
        "format": "json",
    }
    url = urljoin(base + "/", "pyroscope/render")
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, params=params)
        try:
            payload = r.json()
        except Exception:
            r.raise_for_status()
            raise
    if "flamebearer" not in payload:
        err = payload.get("message") or payload.get("error") or "unknown error"
        raise ValueError(f"Pyroscope query failed: {err}")
    return payload
