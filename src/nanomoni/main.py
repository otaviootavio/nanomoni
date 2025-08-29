from __future__ import annotations

import asyncio
import sys
import uvicorn

# Install uvloop for better async performance (Linux/macOS only)
if sys.platform != "win32":
    try:
        import uvloop

        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass  # uvloop not available, continue with default event loop

from .env import get_settings
from .api.app import create_app


def main() -> None:
    """Main entry point for the application."""

    settings = get_settings()
    app = create_app()

    print(f"Starting {settings.app_name} v{settings.app_version}")
    print(f"Database: {settings.database_url}")
    print(f"API will be available at: http://{settings.api_host}:{settings.api_port}")
    print(f"API Documentation: http://{settings.api_host}:{settings.api_port}/docs")

    # Run the FastAPI application
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_debug,
        log_level="info" if not settings.api_debug else "debug",
    )


if __name__ == "__main__":
    main()
