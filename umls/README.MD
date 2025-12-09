mkdir -p png
docker run --rm -v $(pwd):/data plantuml/plantuml -tpng -o png *.puml


## System Overview

note over Client, Issuer
  **Off-Chain Payment Channel System**
  Enables high-frequency micropayments without blockchain overhead
end note

== High-Level Flow ==


note over Client, Vendor
  **Key Innovation:**
  • Only 1 Issuer verification (first payment)
  • 9,998 payments validated locally by Vendor
  • Minimal storage: Only latest payment state kept
end note


note over Client
  Client balance: 9M
  Channel balance: 1M
  Ready for off-chain payments
end note

note right of Vendor
    First payment: Verify with Issuer
    Subsequent: Local validation only
  end note
  
note over Client, Issuer
  **Final State:**
  • Total on-chain operations: 2 (open + close)
  • Total off-chain payments: 9,999
  • Efficiency gain: 4,999x reduction in on-chain transactions
end note


# title "Phase 1a: Client Registration"

note over Client
  **Goal:** Register client with Issuer
  and obtain initial account balance
end note


note over Client, IssuerDB
  **Result:**
  • Client registered successfully
  • Account balance: 10,000,000
  • Client can now open payment channels
end note

note right: Initial balance funded by Issuer

# title "Phase 1b: Payment Channel Opening"

note over Client
  **Prerequisites:**
  • Client is registered (has account)
  • Client balance: 10,000,000
  • Target: Open channel with 1,000,000
end note

note over Client, IssuerDB
  **Channel is now OPEN**
  • Client balance: 9,000,000
  • Channel amount: 1,000,000 (locked)
  • Channel ID: computed_id
  • Client can now make off-chain payments to vendor
end note


# title "Phase 2a: First Payment (Channel Verification)"

note over Client
  **Prerequisites:**
  • Channel opened: abc123
  • Channel amount: 1,000,000
  • First payment to vendor
end note

note right: Ensures authenticity


note right of Vendor
  **Channel Verification Required**
  First payment needs Issuer validation
end note

note over Vendor
  **Verification details (first payment):**
  1. Decode envelope → get computed_id and keys
  2. Fetch PaymentChannel from Issuer by computed_id
  3. Validate channel:
     • channel not closed
     • PaymentChannel.vendor_public_key_der_b64 == this vendor's configured public key
  4. Validate payment:
     • owed_amount > 0
     • owed_amount ≤ channel.amount
  5. Validate keys:
     • payload.client_public_key_der_b64 == channel.client_public_key_der_b64
     • payload.vendor_public_key_der_b64 == channel.vendor_public_key_der_b64
     • payload.vendor_public_key_der_b64 == this vendor's configured public key (payment is addressed to this vendor)
  6. Verify client signature using channel.client_public_key_der_b64
  7. Cache channel locally (only after all checks pass)
end note

note over Client, IssuerDB
  **Result:**
  • First payment accepted
  • Channel verified with Issuer
  • Channel cached locally at Vendor
  • Subsequent payments can use cached data
end note

note right: Lock funds in channel

# Phase 2b: Subsequent Payments (Cached Validation)


note over Client
  **Prerequisites:**
  • First payment completed
  • Channel cached at Vendor
  • Current owed_amount: 1
end note


note over Client, Vendor
  **Key Optimization:**
  • After first payment, channel is cached at Vendor
  • Payments #2 through #9,999 use local validation only
  • No Issuer calls needed for 9,998 payments
end note

note over Vendor
  **Verification details (subsequent payments):**
  1. Decode envelope → get computed_id and keys
  2. Fetch latest OffChainTx by computed_id
  3. Fetch cached PaymentChannel by computed_id
  4. Check:
     • owed_amount > previous.owed_amount
     • owed_amount ≤ channel.amount
  5. Validate keys:
     • payload.client_public_key_der_b64 == channel.client_public_key_der_b64
     • payload.vendor_public_key_der_b64 == channel.vendor_public_key_der_b64
     • payload.vendor_public_key_der_b64 == this vendor's configured public key (payment is addressed to this vendor)
  6. Verify client signature using channel.client_public_key_der_b64
  7. (No re-cache) Cached channel was already validated against Issuer and this vendor on first payment
end note

note over Client, VendorDB
  **Result:**
  • 9,999 total payments completed
  • Latest state: owed_amount = 9,999
  • Ready to close channel
end note


note over Client, VendorDB
  **Key Benefits:**
  • **No Issuer calls** for 9,998 payments
  • **Local validation only** (extremely fast)
  • **Minimal storage**: Only 1 OffChainTx record (latest state)
  • **Scalability**: Can handle thousands of payments/second
  
  **Performance:**
  • 1 Issuer verification (first payment)
  • 9,998 local validations (subsequent payments)
end note


note right of Vendor
      **Use Cached Channel**
      No Issuer call needed!
end note

note right: Storage optimization:\nOnly keep latest payment state

    

# Phase 3a: Channel Closure Initiation

**Prerequisites:**
- Channel abc123 is open
- Latest payment: owed_amount = 9,999
- Client wants to close the channel

**Key Insight:**
Client doesn't sign a new closure request. The last off-chain payment signature will be reused for settlement.

**Flow:**
1. Client sends POST /payments/close with computed_id: "abc123"
2. Vendor retrieves PaymentChannel from local DB
3. Vendor retrieves latest OffChainTx (contains client signature from last payment)
4. Vendor loads vendor private key
5. Vendor signs close payload with vendor private key → creates vendor_close_signature_b64

**Result:**
Vendor now has both signatures needed for settlement:
- Client signature (from last payment)
- Vendor signature (just created)

**Next:** Vendor submits to Issuer with both signatures


# Phase 3b: Issuer Settlement & Finalization

**Prerequisites:**
- Vendor has prepared settlement
- Has client signature (from last payment)
- Has vendor signature (just created)

**Request to Issuer:**
```
POST /payment-channel/close
{
  client_public_key,
  vendor_public_key,
  close_payload_b64,
  client_close_signature_b64,
  vendor_close_signature_b64
}
```

**Issuer Validation Steps:**
1. Load client public key
2. Verify client signature → Client authorized this amount ✓
3. Load vendor public key
4. Verify vendor signature → Vendor confirmed receipt ✓
5. Get PaymentChannel from DB
6. Validate: 0 <= 9,999 <= 1,000,000 ✓

**Final Settlement:**
1. UPDATE vendor Account: balance += 9,999 (transfer funds to vendor)
2. UPDATE client Account: balance += (1,000,000 - 9,999) (return remainder to client)
3. UPDATE PaymentChannel: is_closed: true, balance: 9,999, closed_at: now
4. Return 200 OK to Vendor

**Vendor Confirms:**
1. UPDATE local PaymentChannel (is_closed: true)
2. Return 204 No Content to Client

**Final State:**
- Client balance: 9,990,001 (9M + 990,001 remainder)
- Vendor balance: 9,999
- Channel closed permanently
- Total on-chain operations: 2 (open + close)
- Total off-chain payments: 9,999
- **Efficiency gain: 4,999x reduction in on-chain transactions**