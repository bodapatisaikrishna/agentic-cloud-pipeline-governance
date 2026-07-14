"""CPU stressor for the resource_contention scenario.

Default is a host multiprocessing busy-loop (self-contained, deterministic count/duration,
DEVIATIONS D-026); a stress-ng container is opt-in. Contends for the host CPU that the Docker
VM shares, degrading the co-located pipeline containers during the fault window.
"""

from __future__ import annotations

import multiprocessing as mp
import subprocess
import time

from acde.config import get_settings
from acde.logging import get_logger

log = get_logger("chaos.stressor")


def _burn(deadline: float) -> None:  # pragma: no cover - child process busy loop
    while time.monotonic() < deadline:
        _ = sum(i * i for i in range(1000))  # intentional busy work


def _host_cpu_stress(n_workers: int, duration_s: float) -> None:  # pragma: no cover - process pool
    deadline = time.monotonic() + duration_s
    procs = [mp.Process(target=_burn, args=(deadline,)) for _ in range(n_workers)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()


def _container_cpu_stress(n_workers: int, duration_s: float) -> None:  # pragma: no cover - docker
    image = get_settings().stress_image
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            image,
            "--cpu",
            str(n_workers),
            "--timeout",
            f"{int(duration_s)}s",
        ],
        check=False,
        timeout=duration_s + 30,
    )


def cpu_stress(n_workers: int, duration_s: float) -> None:
    """Apply CPU contention for ``duration_s`` using ``n_workers`` (host procs or container)."""
    settings = get_settings()
    log.info(
        "cpu_stress_start",
        extra={
            "workers": n_workers,
            "duration_s": duration_s,
            "mode": "container" if settings.stress_use_container else "host",
        },
    )
    if settings.stress_use_container:
        _container_cpu_stress(n_workers, duration_s)
    else:
        _host_cpu_stress(n_workers, duration_s)
    log.info("cpu_stress_done", extra={"workers": n_workers})
