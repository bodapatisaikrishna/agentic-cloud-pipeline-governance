"""Seeded synthetic TPC-DS-shaped data generator (batch source).

The official ``dsdgen`` toolchain is a heavy, hard-to-containerize C build whose output
is awkward to make deterministic, so we generate schema-faithful, downscaled data with a
seeded NumPy generator instead (see DEVIATIONS D-009). Same seed ⇒ byte-identical CSVs.

Produces a ``store_sales`` fact and an ``item`` dimension, the minimum needed by the
``tpcds_ingest`` batch DAG (validate → transform daily revenue → materialize partition).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

from acde.config import get_settings
from acde.logging import get_logger

log = get_logger("dataplane.datasets.tpcds")

# Schema-faithful column sets (subset of the TPC-DS spec).
STORE_SALES_COLUMNS = [
    "ss_sold_date",
    "ss_item_sk",
    "ss_customer_sk",
    "ss_quantity",
    "ss_sales_price",
    "ss_net_paid",
]
ITEM_COLUMNS = ["i_item_sk", "i_category", "i_current_price"]

_CATEGORIES = ["Electronics", "Home", "Books", "Sports", "Grocery"]
_DATE_START = dt.date(2026, 1, 1)
_DATE_DAYS = 14  # partition window: two weeks of sales


def generate_item(n_items: int, seed: int) -> pd.DataFrame:
    """Deterministic item dimension."""
    rng = np.random.default_rng(seed)
    item_sk = np.arange(1, n_items + 1, dtype=np.int64)
    category = rng.choice(_CATEGORIES, size=n_items)
    price = np.round(rng.uniform(1.0, 500.0, size=n_items), 2)
    return pd.DataFrame(
        {"i_item_sk": item_sk, "i_category": category, "i_current_price": price},
        columns=ITEM_COLUMNS,
    )


def generate_store_sales(n_rows: int, n_items: int, seed: int) -> pd.DataFrame:
    """Deterministic store_sales fact over a fixed 14-day window."""
    rng = np.random.default_rng(seed)
    day_offsets = rng.integers(0, _DATE_DAYS, size=n_rows)
    sold_date = [(_DATE_START + dt.timedelta(days=int(d))).isoformat() for d in day_offsets]
    item_sk = rng.integers(1, n_items + 1, size=n_rows, dtype=np.int64)
    customer_sk = rng.integers(1, max(2, n_rows // 4), size=n_rows, dtype=np.int64)
    quantity = rng.integers(1, 11, size=n_rows, dtype=np.int64)
    sales_price = np.round(rng.uniform(1.0, 500.0, size=n_rows), 2)
    net_paid = np.round(sales_price * quantity * rng.uniform(0.8, 1.0, size=n_rows), 2)
    return pd.DataFrame(
        {
            "ss_sold_date": sold_date,
            "ss_item_sk": item_sk,
            "ss_customer_sk": customer_sk,
            "ss_quantity": quantity,
            "ss_sales_price": sales_price,
            "ss_net_paid": net_paid,
        },
        columns=STORE_SALES_COLUMNS,
    )


def generate(seed: int | None = None, n_rows: int | None = None) -> dict[str, pd.DataFrame]:
    """Generate the TPC-DS tables in-memory (no I/O)."""
    settings = get_settings()
    seed = settings.default_seed if seed is None else seed
    n_rows = settings.tpcds_scale_rows if n_rows is None else n_rows
    n_items = max(10, n_rows // 20)
    return {
        "item": generate_item(n_items, seed),
        "store_sales": generate_store_sales(n_rows, n_items, seed),
    }


def write(out_dir: str | Path | None = None, seed: int | None = None) -> dict[str, Path]:
    """Generate and write CSVs to ``DATA_DIR/tpcds/``; returns table→path."""
    settings = get_settings()
    base = Path(out_dir) if out_dir else Path(settings.data_dir) / "tpcds"
    base.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, frame in generate(seed=seed).items():
        path = base / f"{name}.csv"
        frame.to_csv(path, index=False)
        paths[name] = path
        log.info("tpcds_written", extra={"table": name, "rows": len(frame), "path": str(path)})
    return paths


if __name__ == "__main__":  # pragma: no cover
    write()
