from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ...envs.issuer_env import get_settings
from .routers import registration


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

    @app.get("/")
    async def root():
        return {
            "message": f"Welcome to {settings.app_name} Issuer API",
            "docs": "/docs",
        }

    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "service": f"{settings.app_name} Issuer"}

    return app


app = create_issuer_app()
