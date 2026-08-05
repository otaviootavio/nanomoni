from __future__ import annotations

import json
import math
import os
from functools import lru_cache
from typing import List, Optional

from pydantic import BaseModel, field_validator
from cryptography.hazmat.primitives import serialization
from urllib.parse import urlparse


class Settings(BaseModel):
    # One PEM-encoded private key per virtual client (own keypair + channel +
    # payment loop, driven concurrently in-process). The client count is
    # simply len(client_private_key_pems) -- there is no separate count field.
    client_private_key_pems: List[str]
    vendor_base_url: str
    issuer_base_url: str
    # OS processes the virtual clients are spread across. One asyncio loop
    # saturates a single core -- the payment loop and its crypto both hold the
    # GIL -- so this is what turns extra client cores into extra throughput.
    client_processes: int = 1
    # Pin each of those processes to a single core of the container's cpuset.
    client_pin_processes_to_cores: bool = False
    # Consecutive vendor ports to spread virtual clients over, one per vendor
    # worker (keep equal to VENDOR_API_WORKERS). 1 sends everything to the port
    # in vendor_base_url.
    client_vendor_port_count: int = 1
    client_payment_count: int = 1
    client_channel_amount: int = 1
    # signature | payword | paytree | paytree_first_opt (paytree with pruned proofs, opt type 1)
    # | paytree_child_pair (heap-indexed child reveal per payment)
    client_payment_mode: str = "signature"
    client_payword_unit_value: int = 1
    client_payword_max_k: Optional[int] = None
    client_paytree_unit_value: int = 1
    client_paytree_max_i: Optional[int] = None
    # Target throughput ceiling in payments/sec; 0 means no limit (max
    # throughput). Senders take a per-payment delay, derived from this by the
    # ``inter_payment_delay_s`` property below.
    client_target_tps: float = 0.0

    @property
    def inter_payment_delay_s(self) -> float:
        """Seconds to wait between consecutive payments to hit ``client_target_tps``.

        Returns 0.0 (no pacing) when the target TPS is 0.
        """
        return 1.0 / self.client_target_tps if self.client_target_tps > 0 else 0.0

    @field_validator("client_private_key_pems")
    @classmethod
    def validate_client_private_key_pems(cls, v: List[str]) -> List[str]:
        """Validate that every entry is a non-empty, PEM-encoded private key."""
        if not v:
            raise ValueError("client_private_key_pems cannot be empty")
        for pem in v:
            if not pem:
                raise ValueError("Client private key cannot be empty")
            try:
                serialization.load_pem_private_key(
                    pem.encode(),
                    password=None,
                )
            except Exception as e:
                raise ValueError(f"Invalid client private key PEM: {e}") from e
        return v

    @field_validator("vendor_base_url")
    @classmethod
    def validate_vendor_base_url(cls, v: str) -> str:
        if not v:
            raise ValueError("Vendor base URL cannot be empty")
        parsed = urlparse(v)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Vendor base URL must start with http:// or https://")
        if not parsed.netloc:
            raise ValueError("Vendor base URL must include a host")
        return v

    @field_validator("issuer_base_url")
    @classmethod
    def validate_issuer_base_url(cls, v: str) -> str:
        if not v:
            raise ValueError("Issuer base URL cannot be empty")
        parsed = urlparse(v)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Issuer base URL must start with http:// or https://")
        if not parsed.netloc:
            raise ValueError("Issuer base URL must include a host")
        return v

    @field_validator("client_processes")
    @classmethod
    def validate_client_processes(cls, v: int) -> int:
        if v < 1:
            raise ValueError("client_processes must be at least 1")
        return v

    @field_validator("client_vendor_port_count")
    @classmethod
    def validate_client_vendor_port_count(cls, v: int) -> int:
        if v < 1:
            raise ValueError("client_vendor_port_count must be at least 1")
        return v

    @field_validator("client_target_tps")
    @classmethod
    def validate_target_tps(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("client_target_tps must be a finite number")
        if v < 0:
            raise ValueError("client_target_tps must be non-negative")
        return v


@lru_cache
def get_settings() -> Settings:
    client_private_key_pems_str = os.environ.get("CLIENT_PRIVATE_KEY_PEMS")
    vendor_base_url = os.environ.get("VENDOR_BASE_URL")
    issuer_base_url = os.environ.get("ISSUER_BASE_URL")
    client_payment_count_str = os.environ.get("CLIENT_PAYMENT_COUNT")
    client_channel_amount_str = os.environ.get("CLIENT_CHANNEL_AMOUNT")
    client_payment_mode = (os.environ.get("CLIENT_PAYMENT_MODE") or "signature").lower()
    client_payword_unit_value_str = os.environ.get("CLIENT_PAYWORD_UNIT_VALUE")
    client_payword_max_k_str = os.environ.get("CLIENT_PAYWORD_MAX_K")
    client_paytree_unit_value_str = os.environ.get("CLIENT_PAYTREE_UNIT_VALUE")
    client_paytree_max_i_str = os.environ.get("CLIENT_PAYTREE_MAX_I")
    client_processes_str = os.environ.get("CLIENT_PROCESSES")
    client_pin_processes_str = os.environ.get("CLIENT_PIN_PROCESSES_TO_CORES")
    client_vendor_port_count_str = os.environ.get("CLIENT_VENDOR_PORT_COUNT")
    if not (client_private_key_pems_str and vendor_base_url and issuer_base_url):
        raise ValueError(
            "CLIENT_PRIVATE_KEY_PEMS, VENDOR_BASE_URL, and ISSUER_BASE_URL are required"
        )
    if client_payment_count_str is None or client_channel_amount_str is None:
        raise ValueError("CLIENT_PAYMENT_COUNT and CLIENT_CHANNEL_AMOUNT are required")

    try:
        client_private_key_pems = json.loads(client_private_key_pems_str)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Invalid JSON array for CLIENT_PRIVATE_KEY_PEMS: {client_private_key_pems_str!r}"
        ) from e
    if not isinstance(client_private_key_pems, list) or not all(
        isinstance(pem, str) for pem in client_private_key_pems
    ):
        raise ValueError("CLIENT_PRIVATE_KEY_PEMS must be a JSON array of PEM strings")

    try:
        client_payment_count = int(client_payment_count_str)
    except ValueError as e:
        raise ValueError(
            f"Invalid integer for CLIENT_PAYMENT_COUNT: {client_payment_count_str!r}"
        ) from e

    try:
        client_channel_amount = int(client_channel_amount_str)
    except ValueError as e:
        raise ValueError(
            f"Invalid integer for CLIENT_CHANNEL_AMOUNT: {client_channel_amount_str!r}"
        ) from e

    client_payword_unit_value_value = client_payword_unit_value_str or "1"
    try:
        client_payword_unit_value = int(client_payword_unit_value_value)
    except ValueError as e:
        raise ValueError(
            f"Invalid integer for CLIENT_PAYWORD_UNIT_VALUE: {client_payword_unit_value_value!r}"
        ) from e

    if client_payword_max_k_str:
        try:
            client_payword_max_k = int(client_payword_max_k_str)
        except ValueError as e:
            raise ValueError(
                f"Invalid integer for CLIENT_PAYWORD_MAX_K: {client_payword_max_k_str!r}"
            ) from e
    else:
        client_payword_max_k = None

    client_paytree_unit_value_value = client_paytree_unit_value_str or "1"
    try:
        client_paytree_unit_value = int(client_paytree_unit_value_value)
    except ValueError as e:
        raise ValueError(
            f"Invalid integer for CLIENT_PAYTREE_UNIT_VALUE: {client_paytree_unit_value_value!r}"
        ) from e

    if client_paytree_max_i_str:
        try:
            client_paytree_max_i = int(client_paytree_max_i_str)
        except ValueError as e:
            raise ValueError(
                f"Invalid integer for CLIENT_PAYTREE_MAX_I: {client_paytree_max_i_str!r}"
            ) from e
    else:
        client_paytree_max_i = None

    try:
        client_processes = int(client_processes_str) if client_processes_str else 1
    except ValueError as e:
        raise ValueError(
            f"Invalid integer for CLIENT_PROCESSES: {client_processes_str!r}"
        ) from e

    client_pin_processes_to_cores = (
        client_pin_processes_str or "false"
    ).lower() == "true"

    try:
        client_vendor_port_count = (
            int(client_vendor_port_count_str) if client_vendor_port_count_str else 1
        )
    except ValueError as e:
        raise ValueError(
            f"Invalid integer for CLIENT_VENDOR_PORT_COUNT: {client_vendor_port_count_str!r}"
        ) from e

    client_target_tps_str = os.environ.get("CLIENT_TARGET_TPS")
    if client_target_tps_str:
        try:
            client_target_tps = float(client_target_tps_str)
        except ValueError as e:
            raise ValueError(
                f"Invalid float for CLIENT_TARGET_TPS: {client_target_tps_str!r}"
            ) from e
    else:
        client_target_tps = 0.0

    return Settings(
        client_private_key_pems=client_private_key_pems,
        vendor_base_url=vendor_base_url,
        issuer_base_url=issuer_base_url,
        client_processes=client_processes,
        client_pin_processes_to_cores=client_pin_processes_to_cores,
        client_vendor_port_count=client_vendor_port_count,
        client_payment_count=client_payment_count,
        client_channel_amount=client_channel_amount,
        client_payment_mode=client_payment_mode,
        client_payword_unit_value=client_payword_unit_value,
        client_payword_max_k=client_payword_max_k,
        client_paytree_unit_value=client_paytree_unit_value,
        client_paytree_max_i=client_paytree_max_i,
        client_target_tps=client_target_tps,
    )
