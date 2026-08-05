---
name: env-variable
description: Add, remove, or use environment variables in NanoMoni. Use when adding a new config option, removing an env var, or when the user asks how to read or set configuration via environment variables.
---

# Environment Variables in NanoMoni

Configuration is centralized in **env modules** under `src/nanomoni/envs/`. Each component has its own module:

| Component | Module | Env prefix | Example script |
|-----------|--------|------------|----------------|
| Issuer | `issuer_env.py` | `ISSUER_*` | `envs/example.issuer.sh` |
| Vendor | `vendor_env.py` | `VENDOR_*` | `envs/example.vendor.sh` |
| Client | `client_env.py` | `CLIENT_*` | `envs/example.client.sh` |

Each module defines a Pydantic `Settings` model and an `@lru_cache`-decorated `get_settings()` that reads `os.environ.get("VAR_NAME")`, validates, and returns a `Settings` instance.

---

## Add an env variable

1. **Choose the right module** (issuer / vendor / client) and open `src/nanomoni/envs/<component>_env.py`.

2. **Add the field to the `Settings` model** with the correct type (e.g. `str`, `int`, `bool`, `list[str]`). Use a default or `Optional[...]` for optional vars.

3. **In `get_settings()`**:
   - Read with `os.environ.get("PREFIX_VAR_NAME")` (e.g. `ISSUER_API_PORT`).
   - **Required**: if `None`, `raise ValueError("PREFIX_VAR_NAME is required")`.
   - **Optional**: use `or "default"` or parse with a fallback (e.g. `int(x) if x else 8000`). For booleans use `(raw or "false").lower() == "true"`. For lists use `raw.split(",") if raw else []`.
   - Pass the value into the `Settings(...)` constructor.

4. **Add a validator** on the `Settings` model if the value needs validation (e.g. PEM format, URL format). See existing `@field_validator` in the same file.

5. **Update the example env script** in `envs/example.<issuer|vendor|client>.sh`: add an `export PREFIX_VAR_NAME="..."` with a short comment. Do not commit secrets; use placeholders or generation commands (e.g. `openssl ...`) where appropriate.

6. **Use the new setting** only via `get_settings()` (see “Use an env variable” below). Do not read `os.environ` for this value in application code.

---

## Remove an env variable

1. **Remove the field** from the `Settings` model in the correct `src/nanomoni/envs/<component>_env.py`.

2. **Remove the read and the argument** from `get_settings()` (the `os.environ.get(...)` line and the corresponding argument in `Settings(...)`).

3. **Remove or update any `@field_validator`** that referred to that field.

4. **Update** `envs/example.<issuer|vendor|client>.sh` (delete the `export` line).

5. **Find and fix all usages** of the removed setting (e.g. `settings.old_name`). Replace with a constant, another setting, or remove the behavior.

---

## Use an env variable

- **Application code**: Import `get_settings` from the appropriate env module and call it once (or use the dependency in FastAPI). Use the returned `Settings` object; do not read `os.environ` directly for these settings.

  ```python
  from nanomoni.envs.issuer_env import get_settings

  settings = get_settings()
  port = settings.api_port
  ```

- **Issuer or Vendor API (FastAPI)**: Use the existing **settings dependency** so settings are injected per request:

  - Issuer: `from ...envs.issuer_env import get_settings, Settings` and use `get_settings_dependency()` from `api/issuer_api/dependencies.py`.
  - Vendor: same pattern with `vendor_env` and `api/vendor_api/dependencies.py`.

  In route handlers, declare `settings: Settings` (or the dependency) and use `settings.attribute`.

- **Client or one-off scripts**: Call `get_settings()` from `nanomoni.envs.client_env` (or the right component) and use the returned object.

- **Special case**: `PROMETHEUS_MULTIPROC_DIR` is read via `os.environ.get(...)` in `main.py` / `issuer_main.py` and in the vendor API app for process-specific setup before the env modules are used. Only add similar raw `os.environ` reads for process/bootstrap concerns that cannot go through Settings.

---

## Conventions

- **Naming**: `PREFIX_NAME` in UPPER_SNAKE_CASE (e.g. `ISSUER_DATABASE_URL`, `VENDOR_API_WORKERS`).
- **Required vs optional**: Required vars raise a clear `ValueError` with the var name; optional vars have defaults in code and can be omitted from the example scripts.
- **Types**: Parse strings to `int`, `bool`, or `list[str]` inside `get_settings()` and pass typed values into `Settings`; keep the model typed, not stringly-typed.
- **Docs**: If the var is user-facing or non-obvious, add a brief comment in the example `envs/example.*.sh` script.
