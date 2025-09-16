"""FastAPI application configuration (Vendor API)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ...middleware.ecdsa import ECDSASignatureMiddleware

from ...envs.vendor_env import get_settings
from ...infrastructure.database import get_database_client
from .routers import auth, users, tasks

settings = get_settings()


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="NanoMoni Vendor CRUD API",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Database client for caching issuer public key
    db_client = get_database_client(settings)

    # Add ECDSA signature verification middleware, skipping registration endpoints
    skip_paths = [
        "/",
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/v1/issuer/",
        "/api/v1/vendor/register/start",
        "/api/v1/vendor/register/complete",
    ]
    app.add_middleware(
        ECDSASignatureMiddleware,
        issuer_base_url=settings.issuer_base_url,
        db_client=db_client,
        skip_paths=skip_paths,
    )

    # Include routers
    app.include_router(users.router, prefix="/api/v1")
    app.include_router(tasks.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")

    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "message": f"Welcome to {settings.app_name} Vendor API",
            "version": settings.app_version,
            "docs": "/docs",
        }

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "service": f"{settings.app_name} Vendor",
            "version": settings.app_version,
        }

    return app


app = create_app()
