---
name: add-entity
description: Add a new persistent entity and its repository in NanoMoni. Use when adding a new database entity, a new domain model with storage, or when the user asks how to add an entity to the database.
---

# Adding a New Entity to the Database

NanoMoni persists entities via **domain entities** (Pydantic), **repository interfaces** (domain), and **repository implementations** (infrastructure) using a **KeyValueStore** (Redis). There are no SQL schemas or migrations; storage is key-value with optional sorted-set indexes.

Use this skill when introducing a new entity that must be stored and retrieved.

---

## 1. Choose the bounded context

| Context | Entities file | Repository interface location | Implementation directory |
|--------|----------------|--------------------------------|---------------------------|
| **Vendor** | `src/nanomoni/domain/vendor/entities.py` | `domain/vendor/<name>_repository.py` (new file) | `infrastructure/vendor/<name>_repository_impl.py` |
| **Issuer** | `src/nanomoni/domain/issuer/entities.py` | `domain/issuer/repositories.py` (add to existing) or new file | `infrastructure/issuer/<name>_repository_impl.py` |

---

## 2. Add the domain entity

In the correct `entities.py`:

- Subclass `BaseModel` and use `CommonSerializersMixin` from `..shared.serializers` (or `...shared.serializers` from issuer) for consistent `id` and `created_at` serialization.
- Use `Field(default_factory=uuid4)` for `id`, `Field(default_factory=lambda: datetime.now(timezone.utc))` for `created_at`.
- For optional `datetime` fields (e.g. `updated_at`, `closed_at`), add a `@field_serializer` that returns `value.isoformat() if value else None`.
- Use `EmailStr` for email fields; use `UUID` for foreign keys.

Example (Vendor):

```python
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field, field_serializer

from ..shared.serializers import CommonSerializersMixin

class MyEntity(CommonSerializersMixin, BaseModel):
    """Short description."""

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., min_length=1, max_length=200)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    @field_serializer("updated_at")
    def serialize_updated_at(self, value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value else None
```

---

## 3. Define the repository interface

**Vendor:** create `src/nanomoni/domain/vendor/<entity>_repository.py` with an abstract class (e.g. `MyEntityRepository`) extending `ABC`, and `@abstractmethod` async methods such as `create`, `get_by_id`, `update`, `delete`, and any list/lookup methods (e.g. `get_all`, `get_by_xyz`).

**Issuer:** add a new `ABC` class in `domain/issuer/repositories.py` (or a new file if it keeps the file small), with the same style of abstract async methods.

Import the entity from the same domain (e.g. `from .entities import MyEntity`). Use `Optional[T]` for get-by-id/get-by-key, `List[T]` for list methods, and document return values (e.g. “Returns number of deleted keys”) where relevant.

Example:

```python
"""MyEntity domain repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID

from .entities import MyEntity

class MyEntityRepository(ABC):
    @abstractmethod
    async def create(self, entity: MyEntity) -> MyEntity:
        pass

    @abstractmethod
    async def get_by_id(self, entity_id: UUID) -> Optional[MyEntity]:
        pass

    @abstractmethod
    async def get_all(self, skip: int = 0, limit: int = 100) -> List[MyEntity]:
        pass

    @abstractmethod
    async def update(self, entity: MyEntity) -> MyEntity:
        pass

    @abstractmethod
    async def delete(self, entity_id: UUID) -> bool:
        pass
```

---

## 4. Implement the repository (KeyValueStore)

Create the impl in the correct infrastructure folder (e.g. `src/nanomoni/infrastructure/vendor/my_entity_repository_impl.py` or `issuer/...`).

- Constructor: `def __init__(self, store: KeyValueStore):` and `self.store = store`.
- **Key layout:** store the entity as JSON at a primary key, e.g. `entity:{id}`. Document the layout in a short docstring.
- **Write:** `await self.store.set(key, entity.model_dump_json())`.
- **Read:** `data = await self.store.get(key)`; if data, `return MyEntity.model_validate_json(data)`; else `return None`.
- **Indexes (optional):** for “list all” or “list by X”, use sorted sets: `zadd("entities:all", {str(entity.id): entity.created_at.timestamp()})` and `zrevrange("entities:all", skip, skip + limit - 1)` to get IDs, then `get` each. Add secondary indexes like `entities:by_user:{user_id}` if needed.
- **Update:** read existing (if you need to adjust indexes, e.g. by status), then `set` the updated entity; if you have indexes that change (e.g. status), `zrem` old index key and `zadd` new one.
- **Delete:** `delete` the primary key and `zrem` from every index set the entity was in (you may need to read the entity first to know secondary key values).

Available store methods: `get`, `set`, `delete`, `zadd`, `zrevrange`, `zrem`, and optionally `mget`, `hmget`, `hset`, `eval`/scripts for more complex operations.

Example skeleton:

```python
"""MyEntity repository using KeyValueStore."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from ...domain.vendor.entities import MyEntity
from ...domain.vendor.my_entity_repository import MyEntityRepository
from ..storage import KeyValueStore

class MyEntityRepositoryImpl(MyEntityRepository):
    def __init__(self, store: KeyValueStore):
        self.store = store

    async def create(self, entity: MyEntity) -> MyEntity:
        await self.store.set(f"my_entity:{entity.id}", entity.model_dump_json())
        await self.store.zadd("my_entities:all", {str(entity.id): entity.created_at.timestamp()})
        return entity

    async def get_by_id(self, entity_id: UUID) -> Optional[MyEntity]:
        data = await self.store.get(f"my_entity:{entity_id}")
        return MyEntity.model_validate_json(data) if data else None

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[MyEntity]:
        ids = await self.store.zrevrange("my_entities:all", skip, skip + limit - 1)
        out = []
        for eid in ids:
            data = await self.store.get(f"my_entity:{eid}")
            if data:
                out.append(MyEntity.model_validate_json(data))
        return out

    async def update(self, entity: MyEntity) -> MyEntity:
        await self.store.set(f"my_entity:{entity.id}", entity.model_dump_json())
        return entity

    async def delete(self, entity_id: UUID) -> bool:
        data = await self.store.get(f"my_entity:{entity_id}")
        if not data:
            return False
        await self.store.delete(f"my_entity:{entity_id}")
        await self.store.zrem("my_entities:all", str(entity_id))
        return True
```

---

## 5. Expose the repository to the API (if needed)

If the entity is used from the Vendor or Issuer API:

- **Vendor:** In `src/nanomoni/api/vendor_api/dependencies.py`, add a `get_<name>_repository()` that returns the interface type and builds the impl with `get_key_value_store_dependency()`. Use the same pattern as `get_task_repository()` / `get_user_repository()`.
- **Issuer:** In `src/nanomoni/api/issuer_api/dependencies.py`, add a `get_<name>_repository()` that uses `get_store_dependency()` and returns the impl (same pattern as `get_account_repository()`).

Then inject the repository (or a use-case service that uses it) in routes via `Depends(get_<name>_repository)`. For new use cases and routes, follow the application-layer patterns and the **add-route** skill.

---

## Checklist

- [ ] Entity added in the correct `domain/vendor/entities.py` or `domain/issuer/entities.py` with `CommonSerializersMixin`, `id`, `created_at`, and any `field_serializer`s.
- [ ] Repository interface added in domain (new file for vendor or in `repositories.py` for issuer) with abstract async methods.
- [ ] Repository implementation in `infrastructure/vendor/` or `infrastructure/issuer/` using `KeyValueStore`; key layout documented; indexes updated on create/update/delete.
- [ ] If the API needs it: `get_*_repository` in the correct `api/*/dependencies.py` and use in routes or use cases.
