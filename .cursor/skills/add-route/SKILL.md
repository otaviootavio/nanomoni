---
name: add-route
description: Add HTTP routes to NanoMoni Vendor or Issuer APIs (FastAPI). Use when adding a new endpoint, a new resource, or a new API route; or when the user asks how to add a route.
---

# Adding a New Route

NanoMoni has two FastAPI apps: **Vendor API** and **Issuer API**. Routes live in router modules under each app. Use this skill when adding a new endpoint or a new router.

## Where routes live

| API    | App module                    | Routers directory                          | URL prefix          |
|--------|-------------------------------|--------------------------------------------|---------------------|
| Vendor | `src/nanomoni/api/vendor_api/`  | `vendor_api/routers/*.py`                   | `/api/v1/vendor`    |
| Issuer | `src/nanomoni/api/issuer_api/`  | `issuer_api/routers/*.py`                   | `/api/v1/issuer`    |

The app is built in `app.py`; it imports router modules from `.routers` and mounts them with `app.include_router(..., prefix="/api/v1/vendor")` or `.../issuer`.

---

## Option A: Add an endpoint to an existing router

Use when the new route belongs to an existing resource (e.g. another endpoint under `/users` or under a channel).

1. **Open the right router**  
   - Vendor: `src/nanomoni/api/vendor_api/routers/<resource>.py`  
   - Issuer: `src/nanomoni/api/issuer_api/routers/<resource>.py`

2. **Add the route**  
   - Use the existing `router` and `@router.<method>(path, ...)`.  
   - Path is relative to the router’s `prefix` (and app prefix).  
   - Use DTOs from the application layer (e.g. `....application.vendor.dtos` or issuer equivalent).  
   - Inject services/repos with `Depends(get_<service>)` from the same API’s `dependencies` module.

3. **No change in `app.py`**  
   - The router is already included; the new endpoint is registered automatically.

**Example (Vendor):** Adding `GET /users/{user_id}/stats` in `routers/users.py`:

- Add something like:
  - `@router.get("/{user_id}/stats", response_model=UserStatsDTO)`
  - Handler with `user_id: UUID`, `user_service: UserService = Depends(get_user_service)`.
- Implement or reuse a use case and DTO as needed.

---

## Option B: Add a new router (new resource or prefix)

Use when introducing a new resource group or path prefix (e.g. a new `/reports` or `/channels/xyz`).

### 1. Create the router module

- **Vendor:** `src/nanomoni/api/vendor_api/routers/<name>.py`  
- **Issuer:** `src/nanomoni/api/issuer_api/routers/<name>.py`

In that file:

- Docstring: e.g. `"""<Resource> API routes (Vendor)."""` or `(Issuer).`
- Create router: `router = APIRouter(prefix="/<path>", tags=["<tag>"])`  
  - `prefix` is the path segment under the app prefix (e.g. `"/users"`, `"/channels/paytree"`).  
  - `tags` are for OpenAPI grouping.
- Define endpoints with `@router.get(...)`, `@router.post(...)`, etc.
- Use DTOs from `....application.vendor.dtos` or issuer equivalent.
- Use `Depends(get_...)` from the same API’s `..dependencies` for services/repos.

Example skeleton:

```python
"""<Resource> API routes (Vendor)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ....application.vendor.dtos import SomeRequestDTO, SomeResponseDTO
from ....application.vendor.use_cases.some_service import SomeService
from ..dependencies import get_some_service

router = APIRouter(prefix="/resources", tags=["resources"])


@router.get("/", response_model=list[SomeResponseDTO])
async def list_resources(
    some_service: SomeService = Depends(get_some_service),
):
    ...
```

If the use case or dependency does not exist, add it in the application and `dependencies` layer first, then use it in the router.

### 2. Register the router in the app

In the corresponding `app.py`:

- **Vendor:** `src/nanomoni/api/vendor_api/app.py`  
- **Issuer:** `src/nanomoni/api/issuer_api/app.py`

Do both:

1. **Import** the new router module in the existing `from .routers import ...` block (e.g. add `new_router`).
2. **Mount it:** add `app.include_router(new_router.router, prefix="/api/v1/vendor")` or `prefix="/api/v1/issuer"` with the other `include_router` lines.

Example (Vendor) after adding `reports.py`:

```python
from .routers import (
    payments,
    paytree_payments,
    payword_payments,
    reports,   # new
    tasks,
    users,
)
# ...
app.include_router(reports.router, prefix="/api/v1/vendor")
```

You do **not** need to change `routers/__init__.py`; `app.py` imports router modules by name from `.routers`.

### 3. Add dependencies if needed

If the new routes need a service or repository not yet exposed:

- Implement or reuse the use case/repository in the application and infrastructure layers.
- In the same API’s `dependencies.py`, add a `get_<name>` that builds the service/repo (and any DB/store deps).
- Use `Depends(get_<name>)` in the new router.

---

## Checklist

- [ ] Chose correct API (Vendor vs Issuer) and existing router or new file.
- [ ] Router path: `prefix` on router + path on decorator; app adds `/api/v1/vendor` or `/api/v1/issuer`.
- [ ] DTOs and use cases from application layer; no domain entities as request/response.
- [ ] Dependencies from the same API’s `dependencies` module via `Depends()`.
- [ ] If new router: new file in `routers/`, import and `include_router` in `app.py`.
