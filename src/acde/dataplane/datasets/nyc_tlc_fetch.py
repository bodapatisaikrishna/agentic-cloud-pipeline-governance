"""NYC TLC trip-data downloader (real, opt-in) for the streaming replay producer.

Downloads a specific month of Yellow Taxi trip parquet from the official TLC CloudFront
host. This is opt-in (``USE_REAL_TLC=1``); the default streaming source is the seeded
synthetic bursty producer, so tests stay offline (DEVIATIONS D-012).
"""

from __future__ import annotations

from pathlib import Path

from acde.config import get_settings
from acde.logging import get_logger

log = get_logger("dataplane.datasets.tlc")

_BASE_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data"
DEFAULT_MONTH = "2024-01"  # a stable, known-good file


def tlc_url(month: str = DEFAULT_MONTH) -> str:
    """URL of the Yellow Taxi parquet for ``YYYY-MM``."""
    return f"{_BASE_URL}/yellow_tripdata_{month}.parquet"


def download(
    month: str = DEFAULT_MONTH, out_dir: str | Path | None = None
) -> Path:  # pragma: no cover - network, opt-in
    """Download the TLC parquet for ``month`` into ``DATA_DIR/tlc/`` (idempotent)."""
    import httpx

    settings = get_settings()
    base = Path(out_dir) if out_dir else Path(settings.data_dir) / "tlc"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"yellow_tripdata_{month}.parquet"
    if path.exists():
        log.info("tlc_cached", extra={"path": str(path)})
        return path
    with httpx.stream("GET", tlc_url(month), timeout=120, follow_redirects=True) as resp:
        resp.raise_for_status()
        with path.open("wb") as fh:
            for chunk in resp.iter_bytes():
                fh.write(chunk)
    log.info("tlc_downloaded", extra={"month": month, "path": str(path)})
    return path


if __name__ == "__main__":  # pragma: no cover
    download()
