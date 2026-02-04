from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class OpenChannelRequestPayload(BaseModel):
    """Payload carried by the client-signed open-channel request envelope."""

    model_config = ConfigDict(extra="forbid")

    client_public_key_der_b64: str
    vendor_public_key_der_b64: str
    amount: int


class SignatureChannelSettlementPayload(BaseModel):
    """Signed close-channel statement.

    This is the payload that BOTH client and vendor sign during settlement/closure.
    Public keys are inferred from the stored PaymentChannel by channel_id.
    """

    model_config = ConfigDict(extra="forbid")

    channel_id: str
    cumulative_owed_amount: int


class SignatureChannelPaymentPayload(BaseModel):
    """Payload for a signature-mode off-chain payment from client to vendor.

    This is a client-signed monotonic statement of cumulative_owed_amount for a channel.
    We optimize space by omitting public keys; vendor/issuer infer them from channel_id.
    """

    model_config = ConfigDict(extra="forbid")

    channel_id: str
    cumulative_owed_amount: int
