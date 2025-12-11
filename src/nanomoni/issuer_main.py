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
        pass

from .envs.issuer_env import get_settings


def _setup_prometheus_multiproc_dir() -> None:
    """Prepare the Prometheus multiprocess directory before Uvicorn forks workers."""
    prom_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if not prom_dir:
        return

    os.makedirs(prom_dir, exist_ok=True)
    for filename in os.listdir(prom_dir):
        file_path = os.path.join(prom_dir, filename)
        if os.path.isfile(file_path):
            os.remove(file_path)


def main() -> None:
    settings = get_settings()

    print(f"Starting {settings.app_name} Issuer v{settings.app_version}")
    print(f"Database: {settings.database_url}")
    print(
        f"Issuer API will be available at: http://{settings.api_host}:{settings.api_port}"
    )
    print(f"Docs: http://{settings.api_host}:{settings.api_port}/docs")

    # Keep single worker by default, but still prepare multiprocess dir so that
    # metrics remain correct if multiple workers are configured externally.
    _setup_prometheus_multiproc_dir()

    uvicorn.run(
        "nanomoni.api.issuer_api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_debug,
        log_level="info",
    )


if __name__ == "__main__":
    main()
