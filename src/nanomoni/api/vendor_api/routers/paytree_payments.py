"""PayTree payment API routes (Vendor)."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from prometheus_client import Counter, Gauge, Histogram

from ....application.vendor.dtos import CloseChannelDTO
from ....application.vendor.paytree_dtos import (
    PaytreePaymentResponseDTO,
    ReceivePaytreePaymentDTO,
)
from ....application.vendor.use_cases.paytree_payment import PaytreePaymentService
from ..dependencies import get_paytree_payment_service

router = APIRouter(prefix="/channels/paytree", tags=["channels", "paytree"])


PAYMENT_DURATION_BUCKETS = (
    [round(0.5 * i, 1) for i in range(1, 21)]  # 0.5ms..10ms (0.5ms resolution)
    + [float(x) for x in range(15, 55, 5)]  # 15, 20, 25, ..., 50ms (5ms resolution)
    + [float("inf")]
)

paytree_payment_requests_total = Counter(
    "paytree_payment_requests_total",
    "Total PayTree payment requests processed",
    ["status"],
)

paytree_payment_request_duration_milliseconds = Histogram(
    "paytree_payment_request_duration_milliseconds",
    "Wall time to process a PayTree payment request (ms)",
    ["status"],
    buckets=PAYMENT_DURATION_BUCKETS,
)

paytree_payment_requests_inprogress = Gauge(
    "paytree_payment_requests_inprogress",
    "Number of PayTree payment requests currently being processed",
    multiprocess_mode="livesum",
)


@router.post(
    "/{channel_id}/payments",
    response_model=PaytreePaymentResponseDTO,
    status_code=status.HTTP_201_CREATED,
)
async def receive_paytree_payment(
    payment_data: ReceivePaytreePaymentDTO,
    channel_id: str = Path(..., description="Payment channel identifier"),
    payment_service: PaytreePaymentService = Depends(get_paytree_payment_service),
) -> PaytreePaymentResponseDTO:
    """Receive and validate a PayTree (Merkle proof) payment from a client."""
    start_time = time.perf_counter()
    paytree_payment_requests_inprogress.inc()
    try:
        result = await payment_service.receive_paytree_payment(channel_id, payment_data)
        paytree_payment_requests_total.labels(status="success").inc()
        elapsed = (time.perf_counter() - start_time) * 1000
        paytree_payment_request_duration_milliseconds.labels(status="success").observe(
            elapsed
        )
        return result
    except ValueError as e:
        paytree_payment_requests_total.labels(status="client_error").inc()
        elapsed = (time.perf_counter() - start_time) * 1000
        paytree_payment_request_duration_milliseconds.labels(
            status="client_error"
        ).observe(elapsed)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        paytree_payment_requests_total.labels(status="server_error").inc()
        elapsed = (time.perf_counter() - start_time) * 1000
        paytree_payment_request_duration_milliseconds.labels(
            status="server_error"
        ).observe(elapsed)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process PayTree payment: {str(e)}",
        )
    finally:
        paytree_payment_requests_inprogress.dec()


@router.post(
    "/{channel_id}/closure-requests",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def settle_paytree_channel(
    payload: CloseChannelDTO,
    channel_id: str = Path(..., description="Payment channel identifier"),
    payment_service: PaytreePaymentService = Depends(get_paytree_payment_service),
) -> Response:
    try:
        await payment_service.settle_channel(payload)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to close PayTree channel: {str(e)}",
        )
