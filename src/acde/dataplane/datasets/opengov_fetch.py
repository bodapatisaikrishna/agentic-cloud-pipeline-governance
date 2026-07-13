"""Open-gov CSV source: seeded synthetic by default, real NYC 311 fetch opt-in.

Default is a deterministic synthetic CSV shaped like the NYC 311 Service Requests dataset
(the "named open-gov" source), so tests and CI stay offline and reproducible. Setting
``USE_REAL_OPENGOV=1`` fetches a bounded slice of the real dataset instead (DEVIATIONS D-012).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

from acde.config import get_settings
from acde.logging import get_logger

log = get_logger("dataplane.datasets.opengov")

# Shaped after NYC 311 Service Requests.
COLUMNS = ["unique_key", "created_date", "complaint_type", "borough", "descriptor"]
_COMPLAINTS = ["Noise", "Illegal Parking", "Heat/Hot Water", "Street Condition", "Rodent"]
_BOROUGHS = ["MANHATTAN", "BROOKLYN", "QUEENS", "BRONX", "STATEN ISLAND"]
_DATE_START = dt.date(2026, 1, 1)
_REAL_URL = "https://data.cityofnewyork.us/resource/erm2-nwe9.csv"


def generate(seed: int | None = None, n_rows: int | None = None) -> pd.DataFrame:
    """Deterministic synthetic 311-shaped frame."""
    settings = get_settings()
    seed = settings.default_seed if seed is None else seed
    n_rows = settings.opengov_rows if n_rows is None else n_rows
    rng = np.random.default_rng(seed + 1)  # offset so it doesn't mirror tpcds
    key = np.arange(1, n_rows + 1, dtype=np.int64)
    day_offsets = rng.integers(0, 30, size=n_rows)
    created = [(_DATE_START + dt.timedelta(days=int(d))).isoformat() for d in day_offsets]
    return pd.DataFrame(
        {
            "unique_key": key,
            "created_date": created,
            "complaint_type": rng.choice(_COMPLAINTS, size=n_rows),
            "borough": rng.choice(_BOROUGHS, size=n_rows),
            "descriptor": rng.choice(["Loud Music", "Blocked", "No Heat", "Pothole"], size=n_rows),
        },
        columns=COLUMNS,
    )


def _fetch_real(n_rows: int) -> pd.DataFrame:  # pragma: no cover - network, opt-in
    import httpx

    resp = httpx.get(_REAL_URL, params={"$limit": n_rows}, timeout=60)
    resp.raise_for_status()
    from io import StringIO

    return pd.read_csv(StringIO(resp.text))


def write(out_dir: str | Path | None = None, seed: int | None = None) -> Path:
    """Generate/fetch and write ``opengov.csv`` to ``DATA_DIR/opengov/``."""
    settings = get_settings()
    base = Path(out_dir) if out_dir else Path(settings.data_dir) / "opengov"
    base.mkdir(parents=True, exist_ok=True)
    if settings.use_real_opengov:
        frame = _fetch_real(settings.opengov_rows)
        source = "real"
    else:
        frame = generate(seed=seed)
        source = "synthetic"
    path = base / "opengov.csv"
    frame.to_csv(path, index=False)
    log.info("opengov_written", extra={"source": source, "rows": len(frame), "path": str(path)})
    return path


if __name__ == "__main__":  # pragma: no cover
    write()
