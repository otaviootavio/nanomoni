from __future__ import annotations

import asyncio
import os
import sys
import uvicorn

# Install uvloop for better async performance (Linux/macOS only)
if sys.platform != "win32":
    try:
        import uvloop

        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass  # uvloop not available, continue with default event loop

from .envs.vendor_env import get_settings


def _setup_prometheus_multiproc_dir() -> None:
    """Prepare the Prometheus multiprocess directory before Uvicorn forks workers.

    This ensures each process writes to a clean directory so metrics can be
    correctly aggregated by the multiprocess collector.
    """
    prom_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if not prom_dir:
        return

    os.makedirs(prom_dir, exist_ok=True)
    for filename in os.listdir(prom_dir):
        file_path = os.path.join(prom_dir, filename)
        if os.path.isfile(file_path):
            os.remove(file_path)


def main() -> None:
    """Main entry point for the vendor application."""

    settings = get_settings()

    print(f"Starting {settings.app_name} v{settings.app_version}")
    print(f"Database: {settings.database_url}")
    print(f"API will be available at: http://{settings.api_host}:{settings.api_port}")
    print(f"API Documentation: http://{settings.api_host}:{settings.api_port}/docs")

    # Run the FastAPI application.
    # If debug/reload is enabled, force a single worker (Uvicorn doesn't support
    # multi-worker with reload). Otherwise, use the configured number of workers
    # so the app can utilize multiple CPU cores.
    reload = settings.api_debug
    workers = 1 if reload else settings.api_workers

    _setup_prometheus_multiproc_dir()

    uvicorn.run(
        "nanomoni.api.vendor_api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=reload,
        workers=workers,
        log_level="info",
    )


if __name__ == "__main__":
    main()
