"""Prometheus query utilities and sanitization."""

from __future__ import annotations

import re


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
