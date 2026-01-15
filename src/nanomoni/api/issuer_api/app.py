from __future__ import annotations

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
from .routers import registration, payment_channel, payword_channels


settings = get_settings()


def create_issuer_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.app_name} Issuer",
        version=settings.app_version,
        description="NanoMoni Issuer API",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
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
