"""Use case tests for PaymentService - fast unit tests using in-memory implementations."""

from __future__ import annotations

import pytest

from nanomoni.application.vendor.dtos import ReceivePaymentDTO
from nanomoni.application.vendor.use_cases.payment import PaymentService
from tests.e2e.helpers.client_actor import ClientActor
from tests.fixtures import InMemoryPaymentChannelRepository
from tests.use_cases.helpers.issuer_client_adapter import UseCaseIssuerClient
from nanomoni.domain.shared import IssuerClientFactory


@pytest.mark.asyncio
async def test_payment_service_receives_first_payment(
    payment_channel_repository: InMemoryPaymentChannelRepository,
    issuer_client_factory: IssuerClientFactory,
    issuer_client: UseCaseIssuerClient,
    vendor_public_key_der_b64: str,
) -> None:
    """
    Test that PaymentService can receive and process a first payment.

    This test uses in-memory repositories and use case-based issuer client,
    making it fast and independent of external services.
    """
    # Setup: Register client and vendor, open a channel
    client = ClientActor()
    await issuer_client.register_account(client.public_key_der_b64)
    await issuer_client.register_account(vendor_public_key_der_b64)

    open_request = client.create_open_channel_request(vendor_public_key_der_b64, 1000)
    channel_response = await issuer_client.open_channel(open_request)
    channel_id = channel_response.channel_id

    # Create service
    service = PaymentService(
        payment_channel_repository=payment_channel_repository,
        issuer_client_factory=issuer_client_factory,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
        vendor_private_key_pem=None,  # Not needed for receiving payments
    )

    # Create payment DTO using ClientActor's create_payment_envelope method
    first_payment_owed = 100
    payment_envelope = client.create_payment_envelope(channel_id, first_payment_owed)
    payment_dto = ReceivePaymentDTO(envelope=payment_envelope)

    # When: Service receives payment
    result = await service.receive_payment(payment_dto)

    # Then: Payment should be accepted
    assert result.channel_id == channel_id
    assert result.cumulative_owed_amount == first_payment_owed


@pytest.mark.asyncio
async def test_payment_service_verifies_channel_with_issuer(
    payment_channel_repository: InMemoryPaymentChannelRepository,
    issuer_client_factory: IssuerClientFactory,
    issuer_client: UseCaseIssuerClient,
    vendor_public_key_der_b64: str,
) -> None:
    """
    Test that PaymentService verifies channel existence with issuer.

    This demonstrates how the service uses the issuer client factory.
    """
    # Setup: Register client and vendor, open a channel
    client = ClientActor()
    await issuer_client.register_account(client.public_key_der_b64)
    await issuer_client.register_account(vendor_public_key_der_b64)

    open_request = client.create_open_channel_request(vendor_public_key_der_b64, 1000)
    channel_response = await issuer_client.open_channel(open_request)
    channel_id = channel_response.channel_id

    # Create service
    service = PaymentService(
        payment_channel_repository=payment_channel_repository,
        issuer_client_factory=issuer_client_factory,
        vendor_public_key_der_b64=vendor_public_key_der_b64,
    )

    # When: Service verifies channel
    channel = await service._verify_payment_channel(channel_id)

    # Then: Channel should be returned
    assert channel.channel_id == channel_id
    assert channel.vendor_public_key_der_b64 == vendor_public_key_der_b64
    assert not channel.is_closed
