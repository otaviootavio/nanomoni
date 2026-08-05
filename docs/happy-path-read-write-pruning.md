# Happy-path read/write pruning review

This document summarizes a systematic review of the **happy path** (single channel: open → payments → settle → close) and identifies where read or write operations can be pruned.

---

## 1. Prunable (recommended)

### 1.1 Issuer: account upsert — read-after-write

**Where:** `infrastructure/issuer/account_repository_impl.py` — `AccountRepositoryImpl.upsert()`

**Current behavior:** After `store.set(account_key, account.model_dump_json())` we do `stored_raw = await self.store.get(account_key)` and return the deserialized stored value (or `account` if `stored_raw is None`).

**Usage:** Callers either ignore the return value (registration, paytree/payword/signature channel settle when ensuring vendor account exists) or use it only as “the account we just wrote” (e.g. `update_balance` returns the updated account). No caller depends on Redis-normalized data differing from the in-memory `account`.

**Prune:** Remove the `get` after `set`. Return `account` directly. This removes one read per account upsert on the happy path (registration, vendor ensure, and every balance update).

---

## 2. Prunable with small API changes

### 2.1 Vendor: `get_by_channel_id` — second key read for non-signature modes

**Where:** `infrastructure/vendor/payment_channel_repository_base_impl.py` — `get_by_channel_id()`

**Current behavior:** Always `mget([channel_key, state_key])` where `state_key = "signature_state:latest:{channel_id}"`. For `SignaturePaymentChannel` we attach `signature_state` from that key; for Payword/Paytree we never use it.

**Prune:** Fetch only the channel first (`get(channel_key)`), deserialize, then **only if** the channel is a `SignaturePaymentChannel` do a second `get(state_key)` and attach. For Payword/Paytree this removes one key read per `get_by_channel_id` (payment receive and settle paths).

**API/impl:** Same public API; implementation change only (conditional second get).

---

### 2.2 Vendor: `mark_closed` + `update` — duplicate channel read

**Where:**  
- `application/vendor/use_cases/paytree_payment.py` (and payword/signature analogues): `settle_channel()` calls `get_by_channel_id()`, then later `mark_closed(channel_id, ...)`.  
- `mark_closed()` does `channel = await self.get_by_channel_id(channel_id)` then `update(channel)`.  
- `update()` does `existing_raw = await self.store.get(channel_key)` to get `old_is_closed` for index updates.

So on close we effectively read the channel **twice** (once in settle, once inside `mark_closed` via `get_by_channel_id`) and **update** reads it again.

**Prune options:**

- **A)** `mark_closed(..., channel: Optional[PaymentChannelBase] = None)`. If `channel` is provided, skip `get_by_channel_id` and use it for `update`. Removes one full channel fetch on settle.
- **B)** `update(payment_channel, *, old_is_closed: Optional[bool] = None)`. When `old_is_closed` is provided, skip the internal `get(channel_key)` and use it for zset moves. Removes one read when caller already has the channel (e.g. from `mark_closed`).

Doing both A and B removes two reads on the vendor close path.

---

## 3. Writes not read on the happy path (optional / policy)

### 3.1 Vendor: sorted-set indexes for channels

**Where:** `payment_channel_repository_base_impl.py` — `save_channel()` and `update()`

**Current behavior:** We maintain:

- `payment_channels:all` (zadd on create; used by `get_all`)
- `payment_channels:open` / `payment_channels:closed` (zadd/zrem on create and when `is_closed` changes in `update()`)

**Happy path:** A single channel is opened, used for payments, then closed. No code path in that flow calls `get_all(skip, limit)` or otherwise reads these sets.

**Conclusion:** These index writes are **not read on the happy path**. They are only needed for “list channels” (admin/API). Pruning is possible only if we make index maintenance optional (e.g. lazy or disabled for a “minimal” persistence mode); otherwise we must keep them for correct `get_all` behavior.

---

## 4. Summary table

| Location                         | Operation              | Prunable? | Notes                                              |
|---------------------------------|------------------------|-----------|----------------------------------------------------|
| Issuer account_repository upsert| Read after set         | Yes       | Return input `account`; remove `get` (implemented).|
| Vendor get_by_channel_id        | Second key in mget     | Yes       | Conditional second get for signature only.         |
| Vendor mark_closed              | get_by_channel_id      | Yes       | Accept optional `channel` to avoid re-fetch.        |
| Vendor update                   | get(channel_key)       | Yes       | Accept optional `old_is_closed` to skip read.       |
| Vendor save_channel / update    | zadd/zrem indexes      | Optional  | Not read on happy path; only for get_all.          |

---

## 5. Implemented change

- **AccountRepositoryImpl.upsert:** Removed the read-after-write; the method now returns the input `account` after `set`, pruning one Redis read per upsert on the happy path.
