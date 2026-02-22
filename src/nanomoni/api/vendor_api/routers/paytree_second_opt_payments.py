"""PayTree Second Opt payment API routes (Vendor)."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from prometheus_client import Counter, Gauge, Histogram

from ....application.vendor.dtos import CloseChannelDTO
from ....application.vendor.paytree_second_opt_dtos import (
    PaytreeSecondOptPaymentResponseDTO,
    ReceivePaytreeSecondOptPaymentDTO,
)
from ....application.vendor.use_cases.paytree_second_opt_payment import (
    PaytreeSecondOptPaymentService,
)
from ..dependencies import get_paytree_second_opt_payment_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/channels/paytree_second_opt",
    tags=["channels", "paytree_second_opt"],
)

PAYMENT_DURATION_BUCKETS = (
    [round(0.5 * i, 1) for i in range(1, 21)]
    + [float(x) for x in range(15, 55, 5)]
    + [float("inf")]
)

paytree_second_opt_payment_requests_total = Counter(
    "paytree_second_opt_payment_requests_total",
    "Total PayTree Second Opt payment requests processed",
    ["status"],
)
paytree_second_opt_payment_request_duration_milliseconds = Histogram(
    "paytree_second_opt_payment_request_duration_milliseconds",
    "Wall time to process a PayTree Second Opt payment request (ms)",
    ["status"],
    buckets=PAYMENT_DURATION_BUCKETS,
)
paytree_second_opt_payment_requests_inprogress = Gauge(
    "paytree_second_opt_payment_requests_inprogress",
    "Number of PayTree Second Opt payment requests currently being processed",
    multiprocess_mode="livesum",
)


@router.post(
    "/{channel_id}/payments",
    response_model=PaytreeSecondOptPaymentResponseDTO,
    status_code=status.HTTP_201_CREATED,
)
async def receive_paytree_second_opt_payment(
    payment_data: ReceivePaytreeSecondOptPaymentDTO,
    channel_id: str = Path(..., description="Payment channel identifier"),
    payment_service: PaytreeSecondOptPaymentService = Depends(
        get_paytree_second_opt_payment_service
    ),
) -> PaytreeSecondOptPaymentResponseDTO:
    """Receive and validate a PayTree Second Opt payment from a client."""
    start_time = time.perf_counter()
    paytree_second_opt_payment_requests_inprogress.inc()
    try:
        result = await payment_service.receive_payment(channel_id, payment_data)
        paytree_second_opt_payment_requests_total.labels(status="success").inc()
        elapsed = (time.perf_counter() - start_time) * 1000
        paytree_second_opt_payment_request_duration_milliseconds.labels(
            status="success"
        ).observe(elapsed)
        return result
    except ValueError as e:
        paytree_second_opt_payment_requests_total.labels(status="client_error").inc()
        elapsed = (time.perf_counter() - start_time) * 1000
        paytree_second_opt_payment_request_duration_milliseconds.labels(
            status="client_error"
        ).observe(elapsed)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        logger.exception("Failed to process PayTree Second Opt payment")
        paytree_second_opt_payment_requests_total.labels(status="server_error").inc()
        elapsed = (time.perf_counter() - start_time) * 1000
        paytree_second_opt_payment_request_duration_milliseconds.labels(
            status="server_error"
        ).observe(elapsed)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process PayTree Second Opt payment",
        )
    finally:
        paytree_second_opt_payment_requests_inprogress.dec()


@router.post(
    "/{channel_id}/closure-requests",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def settle_paytree_second_opt_channel(
    payload: CloseChannelDTO,
    channel_id: str = Path(..., description="Payment channel identifier"),
    payment_service: PaytreeSecondOptPaymentService = Depends(
        get_paytree_second_opt_payment_service
    ),
) -> Response:
    try:
        await payment_service.settle_channel(payload)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to close PayTree Second Opt channel: {str(e)}",
        )
