"""PayTree standard payment API routes (Vendor)."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from prometheus_client import Counter, Gauge, Histogram

from ....application.vendor.dtos import CloseChannelDTO
from ....application.vendor.paytree_dtos import (
    PaytreePaymentResponseDTO,
    ReceivePaytreeStdPaymentDTO,
)
from ....application.vendor.use_cases.paytree_std_payment import (
    PaytreeStdPaymentService,
)
from ..dependencies import get_paytree_std_payment_service
from ..metrics import PAYMENT_DURATION_BUCKETS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/channels/paytree/std", tags=["channels", "paytree-std"])

paytree_std_payment_requests_total = Counter(
    "paytree_std_payment_requests_total",
    "Total PayTree std payment requests processed",
    ["status"],
)

paytree_std_payment_request_duration_milliseconds = Histogram(
    "paytree_std_payment_request_duration_milliseconds",
    "Wall time to process a PayTree std payment request (ms)",
    ["status"],
    buckets=PAYMENT_DURATION_BUCKETS,
)

paytree_std_payment_requests_inprogress = Gauge(
    "paytree_std_payment_requests_inprogress",
    "Number of PayTree std payment requests currently being processed",
    multiprocess_mode="livesum",
)


@router.post(
    "/{channel_id}/payments",
    response_model=PaytreePaymentResponseDTO,
    status_code=status.HTTP_201_CREATED,
)
async def receive_paytree_std_payment(
    payment_data: ReceivePaytreeStdPaymentDTO,
    channel_id: str = Path(..., description="Payment channel identifier"),
    payment_service: PaytreeStdPaymentService = Depends(
        get_paytree_std_payment_service
    ),
) -> PaytreePaymentResponseDTO:
    start_time = time.perf_counter()
    paytree_std_payment_requests_inprogress.inc()
    try:
        result = await payment_service.receive_payment(channel_id, payment_data)
        paytree_std_payment_requests_total.labels(status="success").inc()
        elapsed = (time.perf_counter() - start_time) * 1000
        paytree_std_payment_request_duration_milliseconds.labels(
            status="success"
        ).observe(elapsed)
        return result
    except ValueError as e:
        paytree_std_payment_requests_total.labels(status="client_error").inc()
        elapsed = (time.perf_counter() - start_time) * 1000
        paytree_std_payment_request_duration_milliseconds.labels(
            status="client_error"
        ).observe(elapsed)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        logger.exception("Failed to process PayTree std payment")
        paytree_std_payment_requests_total.labels(status="server_error").inc()
        elapsed = (time.perf_counter() - start_time) * 1000
        paytree_std_payment_request_duration_milliseconds.labels(
            status="server_error"
        ).observe(elapsed)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process PayTree std payment",
        )
    finally:
        paytree_std_payment_requests_inprogress.dec()


@router.post(
    "/{channel_id}/closure-requests",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def settle_paytree_std_channel(
    payload: CloseChannelDTO,
    channel_id: str = Path(..., description="Payment channel identifier"),
    payment_service: PaytreeStdPaymentService = Depends(
        get_paytree_std_payment_service
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
            detail=f"Failed to close PayTree std channel: {str(e)}",
        )
