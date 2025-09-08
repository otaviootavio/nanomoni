# NanoMoni Clients

This folder contains a simple demo client that makes requests compatible with the server's ECDSA middleware.

What it does:
- Generates an ephemeral ECDSA key (secp256r1)
- Registers with the Issuer (separate process) using a challenge/response proving key ownership
- Receives a basic certificate containing its public key and initial balance
- Signs the raw HTTP request body using SHA-256 + ECDSA for protected app endpoints
- Sends headers `X-Public-Key` (base64 DER) and `X-Signature` (base64 DER)
- Performs a tiny CRUD flow: create a user, create a task, update it, delete it

Requirements:
- Vendor API running (default): `http://127.0.0.1:8000`
- Issuer API running (default): `http://127.0.0.1:8001`
- Python dependencies are already in the project (httpx, cryptography). If you installed with Poetry, you're good.

Run:
```bash
# Run vendor API
poetry run python -m nanomoni.main

# In another terminal, run issuer API
poetry run python -m nanomoni.issuer_main

# Then run the client
poetry run python clients/demo_client.py
```

Environment variables (optional):
- `BASE_URL` (default: `http://127.0.0.1:8000`)
- `ISSUER_BASE_URL` (default: `http://127.0.0.1:8001/api/v1`)

Notes:
- Registration flow:
  1. Client sends its public key DER (base64) to `ISSUER_BASE_URL/issuer/registration/start` and receives a random `nonce_b64` plus a `challenge_id`.
  2. Client signs the nonce with its private key and posts `{challenge_id, signature_der_b64}` to `ISSUER_BASE_URL/issuer/registration/complete`.
  3. Issuer verifies and stores the client with an initial balance (currently hardcoded to 100), and returns a simple certificate payload.
- The client then signs exactly the bytes it sends as the HTTP body for protected CRUD endpoints to match the middleware verification on the server.
- For DELETE requests (no body), it signs the empty byte string.
- Public key header is sent as base64-encoded DER to avoid newline issues with PEM in HTTP headers. 