"""Streaming producer: seeded bursty synthetic generator (default) + NYC-TLC replay (opt-in).

``generate_events`` is pure and deterministic (unit-tested); the ``run`` CLI sends the
records to Redpanda. Synthetic arrivals are Poisson with random burst segments (a freshness
stressor, matching the ``ingress_burst`` scenario in later phases).
"""

from __future__ import annotations

import argparse
import datetime as dt
from typing import Any

import numpy as np

from acde.config import get_settings
from acde.logging import get_logger

log = get_logger("dataplane.streaming.producer")

_KEYS = ["zone_a", "zone_b", "zone_c", "zone_d"]


def generate_events(
    seed: int,
    n: int,
    start: dt.datetime,
    base_rate: float = 2.0,
    burst_factor: float = 6.0,
    burst_frac: float = 0.2,
) -> list[dict[str, Any]]:
    """Deterministic list of ``n`` records with Poisson inter-arrivals + random bursts.

    Records: ``{"event_ts": iso8601, "key": str, "value": float}``. Same seed ⇒ identical.
    """
    rng = np.random.default_rng(seed)
    is_burst = rng.random(n) < burst_frac
    rates = np.where(is_burst, base_rate * burst_factor, base_rate)
    gaps = rng.exponential(scale=1.0 / rates)
    offsets = np.cumsum(gaps)
    keys = rng.choice(_KEYS, size=n)
    values = np.round(rng.uniform(1.0, 100.0, size=n), 2)
    records: list[dict[str, Any]] = []
    for off, key, value in zip(offsets, keys, values, strict=True):
        ts = start + dt.timedelta(seconds=float(off))
        records.append({"event_ts": ts.isoformat(), "key": str(key), "value": float(value)})
    return records


def _tlc_events(
    path: str, limit: int
) -> list[dict[str, Any]]:  # pragma: no cover - opt-in, needs file
    import pandas as pd

    df = pd.read_parquet(path).head(limit)
    records = []
    for _, row in df.iterrows():
        records.append(
            {
                "event_ts": pd.Timestamp(row["tpep_pickup_datetime"]).isoformat(),
                "key": str(row.get("PULocationID", "unknown")),
                "value": float(row.get("total_amount", 0.0)),
            }
        )
    return records


def rebase_to_end(records: list[dict[str, Any]], end: dt.datetime) -> list[dict[str, Any]]:
    """Shift all event timestamps so the latest lands at ``end`` (events in the recent past).

    Keeps freshness (``materialized_ts - event_ts``) non-negative: events are materialized
    shortly after they occur, never before.
    """
    if not records:
        return records
    times = [dt.datetime.fromisoformat(r["event_ts"]) for r in records]
    shift = max(times) - end
    return [{**r, "event_ts": (t - shift).isoformat()} for r, t in zip(records, times, strict=True)]


def run(events: int = 2000, seed: int | None = None) -> int:  # pragma: no cover - requires a broker
    """Generate and publish records to Redpanda. Returns the number sent."""
    from acde.dataplane.streaming.kafka_io import JsonProducer, ensure_topic

    settings = get_settings()
    seed = settings.default_seed if seed is None else seed
    ensure_topic()
    now = dt.datetime.now(dt.UTC)
    if settings.use_real_tlc:
        from acde.dataplane.datasets.nyc_tlc_fetch import download

        records = _tlc_events(str(download()), events)
    else:
        records = rebase_to_end(generate_events(seed, events, now), now)
    producer = JsonProducer()
    for rec in records:
        producer.send(rec, key=rec["key"])
    producer.flush()
    log.info("producer_sent", extra={"count": len(records)})
    return len(records)


def main() -> None:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(description="ACDE streaming producer")
    parser.add_argument("--events", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()
    run(events=args.events, seed=args.seed)


if __name__ == "__main__":  # pragma: no cover
    main()
