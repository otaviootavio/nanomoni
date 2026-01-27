from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_client import (
    CollectorRegistry,
    CONTENT_TYPE_LATEST,
    generate_latest,
    multiprocess,
)

from ...envs.issuer_env import get_settings
from ...infrastructure.scripts import ISSUER_SCRIPTS
from .dependencies import get_store_dependency
from .routers import registration, payment_channel, payword_channels, paytree_channels


settings = get_settings()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Register Lua scripts for EVALSHA optimization
    store = get_store_dependency()
    for name, script in ISSUER_SCRIPTS.items():
        try:
            await store.register_script(name, script)
        except Exception:
            logger.exception("Failed to register Redis Lua script '%s'", name)
            # Re-raise to prevent startup with unregistered scripts
            raise
    yield


def create_issuer_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.app_name} Issuer",
        version=settings.app_version,
        description="NanoMoni Issuer API",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(registration.router, prefix="/api/v1/issuer")
    app.include_router(payment_channel.router, prefix="/api/v1/issuer")
    app.include_router(payword_channels.router, prefix="/api/v1/issuer")
    app.include_router(paytree_channels.router, prefix="/api/v1/issuer")

    @app.get("/")
    async def root() -> dict[str, str]:
        return {
            "message": f"Welcome to {settings.app_name} Issuer API",
            "docs": "/docs",
        }

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "healthy", "service": f"{settings.app_name} Issuer"}

    @app.get("/metrics")
    async def metrics() -> Response:
        """Expose Prometheus metrics (aggregated across all workers if multiprocess is enabled)."""
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        data = generate_latest(registry)
        return Response(data, media_type=CONTENT_TYPE_LATEST)

    return app


app = create_issuer_app()
