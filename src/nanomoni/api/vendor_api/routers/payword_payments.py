"""PayWord payment API routes (Vendor)."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from prometheus_client import Counter, Gauge, Histogram

from ....application.vendor.dtos import CloseChannelDTO
from ....application.vendor.payword_dtos import (
    PaywordPaymentResponseDTO,
    ReceivePaywordPaymentDTO,
)
from ....application.vendor.use_cases.payword_payment import PaywordPaymentService
from ..dependencies import get_payword_payment_service

router = APIRouter(prefix="/channels/payword", tags=["channels", "payword"])


PAYMENT_DURATION_BUCKETS = (
    [round(0.5 * i, 1) for i in range(1, 21)]  # 0.5ms..10ms (0.5ms resolution)
    + [float(x) for x in range(15, 55, 5)]  # 15, 20, 25, ..., 50ms (5ms resolution)
    + [float("inf")]
)

payword_payment_requests_total = Counter(
    "payword_payment_requests_total",
    "Total PayWord payment requests processed",
    ["status"],
)

payword_payment_request_duration_milliseconds = Histogram(
    "payword_payment_request_duration_milliseconds",
    "Wall time to process a PayWord payment request (ms)",
    ["status"],
    buckets=PAYMENT_DURATION_BUCKETS,
)

payword_payment_requests_inprogress = Gauge(
    "payword_payment_requests_inprogress",
    "Number of PayWord payment requests currently being processed",
    multiprocess_mode="livesum",
)


@router.post(
    "/{channel_id}/payments",
    response_model=PaywordPaymentResponseDTO,
    status_code=status.HTTP_201_CREATED,
)
async def receive_payword_payment(
    payment_data: ReceivePaywordPaymentDTO,
    channel_id: str = Path(..., description="Payment channel identifier"),
    payment_service: PaywordPaymentService = Depends(get_payword_payment_service),
) -> PaywordPaymentResponseDTO:
    """Receive and validate a PayWord (hash-chain) payment from a client."""
    start_time = time.perf_counter()
    payword_payment_requests_inprogress.inc()
    try:
        result = await payment_service.receive_payword_payment(channel_id, payment_data)
        payword_payment_requests_total.labels(status="success").inc()
        elapsed = (time.perf_counter() - start_time) * 1000
        payword_payment_request_duration_milliseconds.labels(status="success").observe(
            elapsed
        )
        return result
    except ValueError as e:
        payword_payment_requests_total.labels(status="client_error").inc()
        elapsed = (time.perf_counter() - start_time) * 1000
        payword_payment_request_duration_milliseconds.labels(
            status="client_error"
        ).observe(elapsed)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        payword_payment_requests_total.labels(status="server_error").inc()
        elapsed = (time.perf_counter() - start_time) * 1000
        payword_payment_request_duration_milliseconds.labels(
            status="server_error"
        ).observe(elapsed)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process PayWord payment: {str(e)}",
        )
    finally:
        payword_payment_requests_inprogress.dec()


@router.post(
    "/{channel_id}/closure-requests",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def settle_payword_channel(
    payload: CloseChannelDTO,
    channel_id: str = Path(..., description="Payment channel identifier"),
    payment_service: PaywordPaymentService = Depends(get_payword_payment_service),
) -> Response:
    if payload.channel_id != channel_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Channel ID mismatch between path and payload",
        )
    try:
        await payment_service.settle_channel(channel_id, payload)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to close PayWord channel: {str(e)}",
        )
