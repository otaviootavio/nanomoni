---
name: modify-issuer-client-vendor
description: Modify the Issuer, Vendor, or Client side of NanoMoni. Use when changing behavior of the issuer API, vendor API, or the payment-channel client; adding or changing use cases, DTOs, repositories, or env config for any of these.
---

# Modifying Issuer, Client, or Vendor

NanoMoni has three main sides: **Issuer** (mints and manages payment channels), **Vendor** (accepts payments from clients), and **Client** (spends via payment channels). Use this skill when modifying any of them.

---

## Where code lives

| Side   | API / entry      | Application (use cases, DTOs)     | Domain (entities, repos)      | Infrastructure (impls, HTTP clients) | Env / config      |
|--------|------------------|-----------------------------------|-------------------------------|--------------------------------------|-------------------|
| Issuer | `api/issuer_api/`| `application/issuer/`             | `domain/issuer/`              | `infrastructure/issuer/`              | `envs/issuer_env.py` |
| Vendor | `api/vendor_api/`| `application/vendor/`             | `domain/vendor/`              | `infrastructure/vendor/`             | `envs/vendor_env.py` |
| Client | —                | — (client is thin, calls APIs)    | `domain/shared/` (protocols)  | —                                     | `envs/client_env.py` |

**Client** code lives under `src/nanomoni/client/` (e.g. `paytree.py`, `payword.py`, `common.py`, `signature.py`) and optionally `client_pay_chan.py` at package root. The client uses `client_env` for issuer/vendor URLs and keys.

---

## Issuer

- **Routes**: `src/nanomoni/api/issuer_api/routers/*.py`; register new routers in `issuer_api/app.py`. See **add-route** for adding endpoints.
- **Use cases / DTOs**: `application/issuer/use_cases/*.py`, `application/issuer/dtos.py`, `paytree_dtos.py`, `payword_dtos.py`.
- **Domain**: `domain/issuer/entities.py`, `domain/issuer/repositories.py` (or new repo interface files).
- **Infrastructure**: `infrastructure/issuer/*.py` (repository impls, `issuer_client.py`). Expose new repos via `api/issuer_api/dependencies.py` with `get_*_dependency` and `Depends()` in routes.
- **Config**: `envs/issuer_env.py`; add new settings there if the issuer needs new env vars.

When adding new persisted data on the issuer side, use **add-entity** for entity + repository; then wire the repository in `issuer_api/dependencies.py` and use it in use cases and routers.

---

## Vendor

- **Routes**: `src/nanomoni/api/vendor_api/routers/*.py`; register new routers in `vendor_api/app.py`. See **add-route** for adding endpoints.
- **Use cases / DTOs**: `application/vendor/use_cases/*.py`, `application/vendor/dtos.py`, `paytree_dtos.py`, `payword_dtos.py`.
- **Domain**: `domain/vendor/entities.py`, `domain/vendor/*_repository.py` (one file per repo interface).
- **Infrastructure**: `infrastructure/vendor/*.py` (repository impls, `vendor_client.py`, `vendor_client_async.py`). Expose new repos via `api/vendor_api/dependencies.py`.
- **Config**: `envs/vendor_env.py`; add new settings there if the vendor needs new env vars.

When adding new persisted data on the vendor side, use **add-entity** for entity + repository; then wire the repository in `vendor_api/dependencies.py` and use it in use cases and routers.

---

## Client

- **Entry / scripts**: `src/nanomoni/client_pay_chan.py` (if present), or scripts that import from `nanomoni.client`.
- **Libraries**: `src/nanomoni/client/paytree.py`, `payword.py`, `common.py`, `signature.py`. These call Issuer and Vendor HTTP APIs; keep them aligned with the API contracts (routes and DTOs).
- **Protocols / shared types**: `domain/shared/` (e.g. `issuer_client_protocol.py`) when client and server share an interface or type.
- **Config**: `envs/client_env.py` for issuer URL, vendor URL, keys, etc.

When changing an API that the client calls, update both the API (issuer or vendor) and the client code (and any shared types in `domain/shared/`).

---

## Checklist when modifying

- [ ] Identify which side(s) are affected: Issuer, Vendor, Client.
- [ ] For API changes: update the correct `api/<issuer_api|vendor_api>/` (routes, dependencies, app registration).
- [ ] For new or changed behavior: add or edit use cases and DTOs in `application/<issuer|vendor>/`.
- [ ] For new or changed persistence: follow **add-entity**; implement repo in `infrastructure/<issuer|vendor>/` and expose in the API’s `dependencies.py`.
- [ ] For new env or config: update `envs/<issuer_env|vendor_env|client_env>.py`.
- [ ] If the client calls the changed API: update `client/` (and `client_env` if URLs or keys change).
- [ ] Run project linter and tests (see **nanomoni-dev-workflow** skill).
