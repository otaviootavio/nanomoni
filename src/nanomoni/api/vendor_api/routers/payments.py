"""Payment API routes (Vendor)."""

from __future__ import annotations

import time

from cryptography.exceptions import InvalidSignature
from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from prometheus_client import Counter, Histogram

from ....application.vendor.dtos import (
    CloseChannelDTO,
    OffChainTxResponseDTO,
    ReceivePaymentDTO,
)
from ....application.vendor.use_cases.payment import PaymentService
from ..dependencies import get_payment_service

router = APIRouter(prefix="/channels", tags=["channels"])


payment_requests_total = Counter(
    "payment_requests_total",
    "Total payment requests processed",
    ["status"],
)

payment_request_duration_seconds = Histogram(
    "payment_request_duration_seconds",
    "Wall time to process a payment request",
    ["status"],
)


@router.post(
    "/{channel_id}/payments",
    response_model=OffChainTxResponseDTO,
    status_code=status.HTTP_201_CREATED,
)
async def receive_payment(
    payment_data: ReceivePaymentDTO,
    channel_id: str = Path(..., description="Payment channel identifier"),
    payment_service: PaymentService = Depends(get_payment_service),
) -> OffChainTxResponseDTO:
    """Receive and validate an off-chain payment from a client."""
    start_time = time.perf_counter()
    try:
        result = await payment_service.receive_payment(payment_data)
        payment_requests_total.labels(status="success").inc()
        elapsed = time.perf_counter() - start_time
        payment_request_duration_seconds.labels(status="success").observe(elapsed)
        return result
    except InvalidSignature:
        payment_requests_total.labels(status="client_error").inc()
        elapsed = time.perf_counter() - start_time
        payment_request_duration_seconds.labels(status="client_error").observe(elapsed)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature on payment envelope",
        )
    except ValueError as e:
        payment_requests_total.labels(status="client_error").inc()
        elapsed = time.perf_counter() - start_time
        payment_request_duration_seconds.labels(status="client_error").observe(elapsed)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        payment_requests_total.labels(status="server_error").inc()
        elapsed = time.perf_counter() - start_time
        payment_request_duration_seconds.labels(status="server_error").observe(elapsed)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process payment: {str(e)}",
        )


@router.post(
    "/{channel_id}/closure-requests",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def close_channel(
    payload: CloseChannelDTO,
    channel_id: str = Path(..., description="Payment channel identifier"),
    payment_service: PaymentService = Depends(get_payment_service),
) -> Response:
    try:
        await payment_service.close_channel(payload)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to close channel: {str(e)}",
        )
