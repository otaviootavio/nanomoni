"""FastAPI application configuration (Vendor API)."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import aiohttp
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_client import (
    CollectorRegistry,
    CONTENT_TYPE_LATEST,
    generate_latest,
    multiprocess,
    REGISTRY,
)

from ...application.vendor.dtos import VendorPublicKeyDTO
from ...cpu_affinity import pin_to_own_core
from ...envs.vendor_env import get_settings, register_vendor_with_issuer
from ...infrastructure.scripts import VENDOR_SCRIPTS
from .dependencies import get_key_value_store_dependency
from .routers import (
    payments,
    paytree_child_pair_payments,
    paytree_first_opt_payments,
    paytree_std_payments,
    payword_payments,
    tasks,
    users,
)

settings = get_settings()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Runs once per Uvicorn worker process, which is the only place a worker can
    # claim a core for itself: the parent process forks before any of this.
    if settings.pin_workers_to_cores:
        pin_to_own_core(label="vendor worker")

    # Shared issuer HTTP session (reused across requests; closed on shutdown).
    app.state.issuer_session = aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=10.0)
    )
    try:
        # Register Lua scripts for EVALSHA optimization
        store = get_key_value_store_dependency()
        for name, script in VENDOR_SCRIPTS.items():
            try:
                await store.register_script(name, script)
            except Exception:
                logger.exception("Failed to register Redis Lua script '%s'", name)
                # Re-raise to prevent startup with unregistered scripts
                raise
        await register_vendor_with_issuer(settings, session=app.state.issuer_session)
        yield
    finally:
        await app.state.issuer_session.close()


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="NanoMoni Vendor CRUD API",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Include routers
    app.include_router(users.router, prefix="/api/v1/vendor")
    app.include_router(tasks.router, prefix="/api/v1/vendor")
    app.include_router(payments.router, prefix="/api/v1/vendor")
    app.include_router(payword_payments.router, prefix="/api/v1/vendor")
    app.include_router(paytree_std_payments.router, prefix="/api/v1/vendor")
    app.include_router(paytree_first_opt_payments.router, prefix="/api/v1/vendor")
    app.include_router(paytree_child_pair_payments.router, prefix="/api/v1/vendor")

    @app.get("/")
    async def root() -> dict[str, str]:
        """Root endpoint."""
        return {
            "message": f"Welcome to {settings.app_name} Vendor API",
            "version": settings.app_version,
            "docs": "/docs",
        }

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {
            "status": "healthy",
            "service": f"{settings.app_name} Vendor",
            "version": settings.app_version,
        }

    @app.get(
        "/api/v1/vendor/keys/public",
        response_model=VendorPublicKeyDTO,
    )
    async def get_vendor_public_key() -> VendorPublicKeyDTO:
        """Return the vendor public key configured via environment settings."""
        return VendorPublicKeyDTO(public_key_der_b64=settings.vendor_public_key_der_b64)

    @app.get("/metrics")
    async def metrics() -> Response:
        """Expose Prometheus metrics (aggregated across all workers if multiprocess is enabled)."""
        if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
            registry = CollectorRegistry()
            multiprocess.MultiProcessCollector(registry)
            data = generate_latest(registry)
        else:
            data = generate_latest(REGISTRY)
        return Response(data, media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
