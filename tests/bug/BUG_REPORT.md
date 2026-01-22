# Bug Report: First Payment Index Inconsistencies

## Summary

This report documents potential bugs and inconsistencies in the first payment validation logic between Payword and Paytree modes in the nanomoni micropayment system.

## Bug 1: Paytree Allows Zero Payment (i=0)

### Description

In Paytree mode, the vendor accepts `i=0` as a valid first payment, which results in `cumulative_owed_amount = 0`. This allows a client to "use" the service without paying anything.

### Root Cause

In `src/nanomoni/application/vendor/use_cases/paytree_payment.py:168`:

```python
prev_i = latest_state.i if latest_state else -1
```

When there's no previous state (cache miss / first payment), `prev_i = -1`. The validation on line 175 checks:

```python
if dto.i <= prev_i:
    # reject
```

This means `i > -1` is required, so `i >= 0` is accepted.

### Impact

- **Severity**: Medium
- **Attack Vector**: A malicious client can:
  1. Open a Paytree channel (locking funds)
  2. Send a payment with `i=0` (paying nothing)
  3. Request settlement
  4. Get full refund while vendor receives nothing

If the vendor provided any service before settlement, they lose money.

### Suggested Fix

Change line 168 to:

```python
prev_i = latest_state.i if latest_state else 0
```

This would require `i > 0`, meaning `i >= 1` for the first payment, consistent with Payword behavior.

---

## Bug 2: Inconsistency Between Payword and Paytree

### Description

Payword and Paytree have different minimum first payment requirements:

| Mode    | Initial Reference | First Valid Index | Minimum Payment |
|---------|-------------------|-------------------|-----------------|
| Payword | `prev_k = 0`      | `k >= 1`          | `unit_value`    |
| Paytree | `prev_i = -1`     | `i >= 0`          | `0`             |

### Root Cause

Different initial values for the "previous index" in cache miss scenarios:

**Payword** (`payword_payment.py:169`):
```python
prev_k = latest_state.k if latest_state else 0
```

**Paytree** (`paytree_payment.py:168`):
```python
prev_i = latest_state.i if latest_state else -1
```

### Impact

- **Severity**: Low (design inconsistency)
- Users may expect consistent behavior across payment modes
- Documentation may be inaccurate if it assumes both modes behave the same

### Suggested Fix

Option A: Change Paytree to use `prev_i = 0` (consistent with Payword)

Option B: Change Payword to use `prev_k = -1` (consistent with Paytree)

Option C: Document the difference as intentional design

---

## Bug 3: cumulative_owed_amount Formula Allows Zero

### Description

Both modes calculate `cumulative_owed_amount = index * unit_value`. When `index = 0`, this results in zero payment.

### Code Reference

**Paytree** (`crypto/paytree.py:229-235`):
```python
def compute_cumulative_owed_amount(*, i: int, unit_value: int) -> int:
    if i < 0:
        raise ValueError("i must be >= 0")
    return i * unit_value
```

**Payword** (`crypto/payword.py:206-212`):
```python
def compute_cumulative_owed_amount(*, k: int, unit_value: int) -> int:
    if k < 0:
        raise ValueError("k must be >= 0")
    return k * unit_value
```

### Suggested Fix

Option A: Change formula to `(index + 1) * unit_value` for Paytree

Option B: Validate `index >= 1` in the payment service (preferred - keeps crypto layer simple)

---

## Reproduction

Run the bug demonstration tests:

```bash
# Start required services
docker compose up -d issuer vendor redis-issuer redis-vendor

# Run bug tests
pytest tests/bug/ -v

# Run specific test
pytest tests/bug/test_first_payment_index_bugs.py::TestPaytreeZeroIndexBug -v
```

## Test Cases

| Test | Description | Expected Result |
|------|-------------|-----------------|
| `test_paytree_accepts_i_zero_first_payment` | Send i=0 as first Paytree payment | Accepted (BUG) |
| `test_payword_rejects_k_zero` | Send k=0 as first Payword payment | Rejected (CORRECT) |
| `test_payword_accepts_k_one` | Send k=1 as first Payword payment | Accepted (CORRECT) |
| `test_first_payment_inconsistency` | Compare minimum payments between modes | Inconsistent (BUG) |
| `test_paytree_settlement_with_zero_payment` | Full attack scenario | Vendor receives 0 (BUG) |

## Files Affected

- `src/nanomoni/application/vendor/use_cases/paytree_payment.py` (line 168)
- `src/nanomoni/application/vendor/use_cases/payword_payment.py` (line 169)
- `src/nanomoni/crypto/paytree.py` (lines 229-235)
- `src/nanomoni/crypto/payword.py` (lines 206-212)
