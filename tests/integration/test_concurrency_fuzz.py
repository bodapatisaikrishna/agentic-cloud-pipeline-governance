"""Concurrency fuzz test for PartitionVersionManager (requires `make up`).

D-074 was a real race: create_version read MAX(version) then ran DROP/CREATE/insert/register as
separate, unlocked statements, so two concurrent writers to the same (dataset, partition_key) could
collide. It was found and fixed by hand with a disposable repro script. This test makes that
reproduction permanent: fire many real threads at create_version across a small pool of shared
targets and assert the invariants a race would violate.

Unlike the benchmark's experiment determinism, only *which target each worker hits* is seeded here
-- real OS thread interleaving is left alone, since genuine non-deterministic scheduling is what a
concurrency fuzzer needs to actually exercise the race window.
"""

from __future__ import annotations

import random
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from acde import db
from acde.dataplane.partitions import PartitionVersionManager, table_name

pytestmark = pytest.mark.integration

_DATASET = "concurrency_fuzz_test"
_TARGETS = ["a", "b", "c", "d"]
_WORKERS = 20
_SEED = 20260826


def _reset() -> None:
    db.execute("DELETE FROM warehouse.partition_versions WHERE dataset = %s", (_DATASET,))
    for target in _TARGETS:
        for version in range(1, _WORKERS + 1):
            db.execute(f"DROP TABLE IF EXISTS warehouse.{table_name(_DATASET, target, version)}")


def _create_one(partition_key: str, worker_id: int) -> int:
    mgr = PartitionVersionManager(experiment_run=f"fuzz-{worker_id}")
    return mgr.create_version(
        _DATASET,
        partition_key,
        "n int",
        rows=[(worker_id,)],
        insert_columns="n",
        activate=False,
    )


def test_concurrent_creates_never_collide():
    _reset()
    rng = random.Random(_SEED)
    assignments = [rng.choice(_TARGETS) for _ in range(_WORKERS)]

    results: dict[int, tuple[str, int]] = {}
    errors: list[BaseException] = []
    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        futures = {
            pool.submit(_create_one, target, i): (i, target) for i, target in enumerate(assignments)
        }
        for future in as_completed(futures):
            worker_id, target = futures[future]
            try:
                version = future.result()
            except BaseException as exc:  # collect, don't fail mid-loop
                errors.append(exc)
            else:
                results[worker_id] = (target, version)

    assert not errors, f"{len(errors)} worker(s) raised: {errors}"

    by_target: dict[str, list[int]] = {t: [] for t in _TARGETS}
    for target, version in results.values():
        by_target[target].append(version)

    for target in _TARGETS:
        expected_n = assignments.count(target)
        versions = sorted(by_target[target])
        assert versions == list(range(1, expected_n + 1)), (
            f"target {target!r}: expected versions 1..{expected_n}, got {versions} "
            "(duplicate or missing version -> a concurrent-write race regressed)"
        )

        rows = db.fetch_all(
            "SELECT version, table_name FROM warehouse.partition_versions "
            "WHERE dataset = %s AND partition_key = %s ORDER BY version",
            (_DATASET, target),
        )
        assert len(rows) == expected_n, (
            f"target {target!r}: {len(rows)} partition_versions rows, expected {expected_n}"
        )
        for row in rows:
            count = db.fetch_one(f"SELECT count(*) AS n FROM warehouse.{row['table_name']}")
            assert count is not None and count["n"] == 1, (
                f"physical table {row['table_name']} missing or has unexpected row count"
            )
