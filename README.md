

### Managing secrets
We are not using `.env` files but rather `env.sh` files that export the variables as environment variables.

They are defined in `/envs/**`. We also provide an example that contains dummy text. To quickstart the project, copy and paste the content into `./envs/env.sh`.

### Running with Docker

```
docker compose up alloy pyroscope redis-vendor cadvisor grafana prometheus redis-issuer 
```

### Running with Python for development

Use Poetry for managing packages and pyenv for managing Python versions.

- Reference for pyenv: https://github.com/pyenv/pyenv
- Reference for Poetry: https://python-poetry.org/docs/managing-environments/

We are using Python 3.9, so run:

```bash
pyenv install 3.9
```

```bash
pyenv local 3.9
```

```bash
poetry env use python3.9
```

To add the interpreter to VS Code:
```bash
poetry env info --path
```

Then add the path to `Python: Select Interpreter` visible in the command palette (Ctrl+Shift+P or Cmd+Shift+P on macOS).


### Generate the envs
Then, create the envs
```bash
envs/issuer-env.example.sh
```

```bash
envs/vendor-env.example.sh
```

```bash
envs/client-env.example.sh
```

### Start the DBs
```bash
docker compose up redis-vendor redis-issuer -d
```

### Run the scripts
For each step below, run in a new terminal.

First, run the issuer
```bash
./scripts/issuer-entrypoint.sh
```

Then, run the vendor
```bash
./scripts/vendor-entrypoint.sh
```

Finally, run the client.
```bash
./scripts/client-entrypoint.sh
```

### Running with Docker 

```bash
docker build . -t  nanomoni
```

```bash
# 1. Source the environment variables
. ./envs/env.sh 

# 2. Verify the variable is set (this is correct)
echo ${SECRET} 

# 3. Run Docker with the environment variable
docker run -e SECRET=$SECRET nanomoni
```

### Linter
```bash
ruff format src/
```

```bash
ruff check src/
```

### Static checker
```bash
mypy src/
```

### Running Tests

Run all tests:
```bash
poetry run pytest
```

Run integration tests with custom iterations:
```bash
poetry run pytest tests/integration/ --race-iterations=1000 -s
```

## Race Condition Testing

The payment channel system handles concurrent off-chain payments. Two race conditions are tested:

### 1. Lost Update on Subsequent Payments (`test_lost_update.py`)

**Scenario**: A payment channel has an existing transaction (`owed_amount=10`). Two concurrent payments arrive:
- Payment A: `owed_amount=20`
- Payment B: `owed_amount=25`

**The Problem (TOCTOU)**: Without atomic operations, both payments read the current state (`owed=10`), both pass validation (`20 > 10` and `25 > 10`), and the last write wins—potentially overwriting the higher amount with the lower one.

**The Fix**: A Lua script in Redis atomically performs read-check-write. The script enforces `new_amount > current_amount` within a single atomic operation, ensuring the higher amount always wins.

### 2. Lost Update on First Payment (`test_lost_update_on_first_payment.py`)

**Scenario**: A new payment channel has no transactions yet. Two concurrent payments both race to be the first:
- Payment A: `owed_amount=20` (first payment attempt)
- Payment B: `owed_amount=25` (first payment attempt)

**The Problem**: Both requests see `latest_tx=None` in Python and believe they're making the first payment. Without atomic handling, both could succeed with the lower amount winning.

**The Fix**: The same Lua script handles this case. Only one request can take the "first payment" path (`if not current_raw then SET`). The second request sees the first's transaction and must pass the comparison check.

### Test Methodology

Both tests use an **adaptive PI controller** to maximize race condition detection:
- Runs thousands of iterations with real Redis
- Dynamically adjusts timing between concurrent requests to target 50% race occurrence
- Tracks statistics on lost updates, correct results, and errors

Expected results with the atomic Lua script implementation:
```
Lost updates detected: 0
Lost update rate: 0.00%
```

### 3. Vulnerable Implementation Tests

A deliberately broken (non-atomic) implementation (`vulnerable_repository.py`) is included in the test folder to prove the race condition is real. These tests **expect** to find lost updates, serving as documentation and regression validation.

- `test_vulnerable_subsequent_payment.py` - Race on subsequent payments (with initial tx)
- `test_vulnerable_first_payment.py` - Race on first payment (no initial tx)

```bash
# Run vulnerable tests to see the race condition in action
poetry run pytest tests/integration/test_vulnerable_*.py -v --race-iterations=500 -s
```

# TODO
- [x] Add cAdvisor + Prometheus + Graphana
- [x] Create Kerner component UML
- [x] Create Issuer component UML
- [x] Create Client component UML
- [x] Create System data flow overview UML
- [x] Create Phase 1 / setup UML
- [x] Create Phase 2 / payments UML
- [x] Create Phase 3 / close sequence diagram UML