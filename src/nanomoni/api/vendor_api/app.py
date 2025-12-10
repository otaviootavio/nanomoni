"""FastAPI application configuration (Vendor API)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import base64
from cryptography.hazmat.primitives import serialization

from ...envs.vendor_env import get_settings, register_vendor_with_issuer
from ...application.vendor.dtos import VendorPublicKeyDTO
from .routers import users, tasks, payments

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await register_vendor_with_issuer(settings)
    yield


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

        public_key = serialization.load_pem_public_key(
            settings.vendor_public_key_pem.encode()
        )
        der_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        public_key_der_b64 = base64.b64encode(der_bytes).decode()

        return VendorPublicKeyDTO(public_key_der_b64=public_key_der_b64)

    return app


app = create_app()
