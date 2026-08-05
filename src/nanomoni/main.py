from __future__ import annotations

import asyncio
import os
import signal
import sys
from multiprocessing import get_context
from multiprocessing.connection import wait
from types import FrameType

import uvicorn

# Install uvloop for better async performance (Linux/macOS only)
if sys.platform != "win32":
    try:
        import uvloop

        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass  # uvloop not available, continue with default event loop

from .envs.vendor_env import get_settings

# Uvicorn defaults this to 5s. Benchmark clients drive many virtual clients from
# a single event loop and stall it for seconds while precomputing crypto; idle
# pooled connections closed during such a stall make the client's next request
# fail while writing its body. Hold idle connections past any plausible stall.
KEEP_ALIVE_TIMEOUT_SEC = 120


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


def _serve(host: str, port: int, *, reload: bool) -> None:
    uvicorn.run(
        "nanomoni.api.vendor_api.app:app",
        host=host,
        port=port,
        reload=reload,
        workers=1,
        log_level="info",
        timeout_keep_alive=KEEP_ALIVE_TIMEOUT_SEC,
    )


def _serve_one_worker_per_port(host: str, base_port: int, count: int) -> int:
    """Run ``count`` single-worker servers on consecutive ports.

    Uvicorn's own multi-worker mode has every worker accept from one shared
    listening socket, and the kernel wakes whichever worker is quickest -- which
    measurably piles connections onto a few workers and leaves others idle, so
    the busy ones saturate their single core while the machine looks half used.
    Giving each worker its own listening socket makes the port a client dials the
    worker it reaches, which is what lets the load be spread deliberately.

    Returns the exit status: a worker dying takes the whole set down, because a
    surviving container missing one port would silently drop the traffic aimed
    at it.
    """
    ctx = get_context("fork")
    procs = [
        ctx.Process(
            target=_serve,
            args=(host, base_port + index),
            kwargs={"reload": False},
            name=f"vendor-worker-{index}",
        )
        for index in range(count)
    ]
    for proc in procs:
        proc.start()

    shutdown_requested = False

    def shutdown(signum: int, frame: FrameType | None) -> None:
        nonlocal shutdown_requested
        shutdown_requested = True
        for proc in procs:
            if proc.is_alive():
                proc.terminate()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    wait([proc.sentinel for proc in procs])
    # A worker exiting without shutdown() having been asked for is a dropped
    # port, even if that worker's own exit code was 0 -- the whole set must
    # still report failure so a container orchestrator doesn't read this as a
    # clean stop.
    status = 0 if shutdown_requested else 1
    for proc in procs:
        if proc.is_alive():
            proc.terminate()

    for proc in procs:
        proc.join()
        # terminate() shows up as -SIGTERM; that is this function doing its job.
        if proc.exitcode not in (0, -signal.SIGTERM):
            print(f"{proc.name} exited with {proc.exitcode}", flush=True)
            status = 1
    return status


def main() -> None:
    """Main entry point for the vendor application."""

    settings = get_settings()

    print(f"Starting {settings.app_name} v{settings.app_version}")
    print(f"Database: {settings.database_url}")
    print(f"API will be available at: http://{settings.api_host}:{settings.api_port}")
    print(f"API Documentation: http://{settings.api_host}:{settings.api_port}/docs")

    # If debug/reload is enabled, force a single worker (Uvicorn doesn't support
    # multi-worker with reload). Otherwise, use the configured number of workers
    # so the app can utilize multiple CPU cores.
    reload = settings.api_debug
    workers = 1 if reload else settings.api_workers

    _setup_prometheus_multiproc_dir()

    if workers == 1:
        _serve(settings.api_host, settings.api_port, reload=reload)
        return

    ports = f"{settings.api_port}-{settings.api_port + workers - 1}"
    print(f"Serving {workers} workers on ports {ports} (one listening socket each)")
    sys.exit(_serve_one_worker_per_port(settings.api_host, settings.api_port, workers))


if __name__ == "__main__":
    main()
