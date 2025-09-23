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
        pass

from .envs.issuer_env import get_settings


def main() -> None:
    settings = get_settings()

    print(f"Starting {settings.app_name} Issuer v{settings.app_version}")
    print(f"Database: {settings.database_url}")
    print(
        f"Issuer API will be available at: http://{settings.api_host}:{settings.api_port}"
    )
    print(f"Docs: http://{settings.api_host}:{settings.api_port}/docs")

    uvicorn.run(
        "nanomoni.api.issuer_api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_debug,
        log_level="info",
    )


if __name__ == "__main__":
    main()
