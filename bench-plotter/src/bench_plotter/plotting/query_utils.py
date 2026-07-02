"""Prometheus query utilities and sanitization."""

from __future__ import annotations

import re
import asyncio
from typing import Callable, Dict, Any


def sanitize_query(s: str) -> str:
    """
    Sanitize a PromQL query string by fixing common syntax issues.

    Args:
        s: Query string to sanitize

    Returns:
        Sanitized query string
    """
    s = s.replace("!\\=", "!=")
    s = s.replace("\\=", "=")
    s = s.replace('\\"', '"')
    s = s.replace("\\'", "'")
    s = re.sub(r"(\w)!(\"\")", r"\1!=\2", s)

    def _pow_match(m: re.Match[str]) -> str:
        try:
            a = int(m.group(1))
            b = int(m.group(2))
            return str(a**b)
        except Exception:
            return m.group(0)

    s = re.sub(r"(\d+)\s*\^\s*(\d+)", _pow_match, s)
    return s


def query_with_fallbacks(
    q: str,
    start_time: float,
    end_time: float,
    query_range_func: Callable[..., Any],
    instant_query_func: Callable[..., Any],
) -> Dict[str, Any]:
    """
    Try original query, then a few safer variants if no data returned.

    Args:
        q: PromQL query string
        start_time: Start timestamp in seconds
        end_time: End timestamp in seconds
        query_range_func: Function to execute range queries
        instant_query_func: Function to execute instant queries

    Returns:
        First successful payload or the last attempted payload
    """

    def run_query(qs: str) -> Dict[str, Any]:
        try:
            return asyncio.run(
                query_range_func(query=qs, start_unix=start_time, end_unix=end_time)
            )
        except Exception as e:
            return {"status": "error", "error": str(e)}

    q_sanitized = sanitize_query(q)

    # 1) Try original (sanitized)
    payload = run_query(q_sanitized)
    res = payload.get("data", {}).get("result", []) if isinstance(payload, dict) else []
    if res:
        return payload

    # 2) Try removing job label (broaden query)
    q_no_job = re.sub(r"\bjob\s*=\s*\"[^\"]*\"\s*,?", "", q_sanitized)
    if q_no_job != q:
        payload = run_query(q_no_job)
        res = (
            payload.get("data", {}).get("result", [])
            if isinstance(payload, dict)
            else []
        )
        if res:
            return payload

    # 2b) Try removing image filters
    q_no_image = re.sub(r",?\s*image!?=\\?\"\\\"", "", q_sanitized)
    if q_no_image != q_sanitized:
        payload = run_query(q_no_image)
        res = (
            payload.get("data", {}).get("result", [])
            if isinstance(payload, dict)
            else []
        )
        if res:
            return payload

    # 2c) Try removing container-specific label selector
    q_no_container_label = re.sub(
        r",?\s*container_label_com_docker_compose_service\s*=\s*\"[^\"]*\"\s*,?",
        "",
        q_sanitized,
    )
    if q_no_container_label != q_sanitized:
        payload = run_query(q_no_container_label)
        res = (
            payload.get("data", {}).get("result", [])
            if isinstance(payload, dict)
            else []
        )
        if res:
            return payload

    # 2d) Try stripping all label selectors
    q_strip_labels = re.sub(r"\{[^}]*\}", "", q_sanitized, count=1)
    if q_strip_labels != q_sanitized:
        payload = run_query(q_strip_labels)
        res = (
            payload.get("data", {}).get("result", [])
            if isinstance(payload, dict)
            else []
        )
        if res:
            return payload

    # 3) Try switching seconds/milliseconds in bucket names
    q_swap_bucket = q.replace("seconds_bucket", "milliseconds_bucket")
    if q_swap_bucket != q:
        payload = run_query(q_swap_bucket)
        res = (
            payload.get("data", {}).get("result", [])
            if isinstance(payload, dict)
            else []
        )
        if res:
            return payload

    q_swap_bucket2 = q.replace("milliseconds_bucket", "seconds_bucket")
    if q_swap_bucket2 != q:
        payload = run_query(q_swap_bucket2)
        res = (
            payload.get("data", {}).get("result", [])
            if isinstance(payload, dict)
            else []
        )
        if res:
            return payload

    # 4) Try increasing rate window
    q_rate_5 = re.sub(r"\[1m\]", "[5m]", q)
    if q_rate_5 != q:
        payload = run_query(q_rate_5)
        res = (
            payload.get("data", {}).get("result", [])
            if isinstance(payload, dict)
            else []
        )
        if res:
            return payload

    q_rate_15 = re.sub(r"\[1m\]", "[15m]", q)
    if q_rate_15 != q:
        payload = run_query(q_rate_15)
        res = (
            payload.get("data", {}).get("result", [])
            if isinstance(payload, dict)
            else []
        )
        if res:
            return payload

    # Try instant query
    try:
        instant_payload = asyncio.run(instant_query_func(query=q_sanitized))
        instant_res = (
            instant_payload.get("data", {}).get("result", [])
            if isinstance(instant_payload, dict)
            else []
        )
        if instant_res:
            return instant_payload
    except Exception:
        pass

    return payload
