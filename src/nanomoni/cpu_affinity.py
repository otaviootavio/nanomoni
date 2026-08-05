"""Pin one process to one core.

Docker's ``cpuset`` constrains a container to a set of cores but leaves the
kernel free to migrate its processes among them, so a vendor worker can move
between cores mid-run and pay an L3 miss on arrival. Owning a core for the
process's whole life removes that variance, and it can only be expressed from
inside the container, per process.
"""

from __future__ import annotations

import fcntl
import os
from typing import IO

LOCK_DIR = "/tmp/nanomoni-cpu-pins"  # noqa: S108 -- container-local by design, see module docstring

# The kernel releases an flock when the holder exits, which is exactly the
# lifetime we want -- but only for as long as the fd stays open, so the handles
# are parked here instead of being closed when pin_to_own_core returns.
_held_locks: list[IO[bytes]] = []


def pin_to_own_core(*, label: str, lock_dir: str = LOCK_DIR) -> int | None:
    """Claim one core out of this process's allowed set and pin the process to it.

    Each core is claimed through an exclusive lock file, so sibling processes of
    the same container never pick the same core and a restarted process reclaims
    whichever core its predecessor released. Returns the claimed core, or
    ``None`` when there are more processes than allowed cores (or the platform
    has no affinity calls), leaving the inherited affinity untouched.

    Reports through ``print`` rather than ``logging`` because both callers are
    process bootstrap paths where the root logger has no handler yet: Uvicorn
    configures only its own loggers, and the client configures none.
    """
    if not hasattr(os, "sched_setaffinity"):
        print(f"{label}: not pinned, platform has no CPU affinity support", flush=True)
        return None

    allowed = sorted(os.sched_getaffinity(0))
    os.makedirs(lock_dir, exist_ok=True)

    for core in allowed:
        handle = open(os.path.join(lock_dir, f"core-{core}.lock"), "wb")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            continue
        _held_locks.append(handle)
        os.sched_setaffinity(0, {core})
        print(f"{label} (pid {os.getpid()}): pinned to core {core}", flush=True)
        return core

    print(
        f"{label} (pid {os.getpid()}): not pinned, all {len(allowed)} allowed "
        "core(s) are already claimed",
        flush=True,
    )
    return None
