"""Before/after benchmark for the D-086 hot-path indexes.

Seeds synthetic rows tagged with a throwaway ``experiment_run`` on top of whatever real data
already exists, times the 3 actual hot queries at increasing row counts, and deletes every row it
added when done. Never touches real rows — everything it writes is scoped to
``BENCH_EXPERIMENT_RUN`` and removed in a ``finally`` block.

Usage: ``uv run python -m acde.analysis.bench_hot_paths`` (needs the stack up; MOCK_LLM irrelevant,
no LLM calls). Run once before applying migration 004 and once after to see the real difference —
this script does not know or care whether the indexes exist, it only measures.
"""

from __future__ import annotations

import random
import time
import uuid
from dataclasses import dataclass

from acde import db
from acde.logging import get_logger

log = get_logger("analysis.bench_hot_paths")

BENCH_EXPERIMENT_RUN = "__bench_hot_paths__"
CHECKPOINTS = (1_000, 10_000, 100_000)  # see DEVIATIONS D-086: 10^6 judged impractical here


@dataclass
class Timing:
    checkpoint: int
    query: str
    ms: float


def _cleanup() -> None:  # pragma: no cover - live DB
    db.execute(
        "DELETE FROM telemetry.agent_actions WHERE experiment_run = %s", (BENCH_EXPERIMENT_RUN,)
    )
    db.execute(
        "DELETE FROM telemetry.failure_events WHERE experiment_run = %s", (BENCH_EXPERIMENT_RUN,)
    )


def _seed_agent_actions(n: int) -> None:  # pragma: no cover - live DB
    rng = random.Random(42)
    targets = [f"target-{i}" for i in range(20)]
    # Weighted to match real observed selectivity (198 real rows: 183 allowed, 11 escalated,
    # 4 denied; 168 executed) rather than an even split -- an even split hides exactly the
    # planner behavior (seq scan beats index scan above ~10-15% selectivity) this benchmark
    # exists to show.
    policy_decisions = rng.choices(["allowed", "escalated", "denied"], weights=[92, 6, 2], k=n)
    rows = [
        (
            str(uuid.uuid4()),
            BENCH_EXPERIMENT_RUN,
            "optimization",
            "scale_workers",
            rng.choice(targets),
            "{}",
            "bench",
            0.5,
            policy_decisions[i],
            "bench",
            rng.random() < 0.85,
            "bench outcome",
            "mock",
            10,
            5,
            "executed",
            "default",
            "default",
        )
        for i in range(n)
    ]
    db.execute_many(
        "INSERT INTO telemetry.agent_actions "
        "(action_id, experiment_run, agent, action_type, target, params, justification, "
        " confidence, policy_decision, policy_reason, executed, outcome, llm_model, "
        " llm_tokens_in, llm_tokens_out, status, tenant_id, environment) "
        "VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        rows,
    )


def _seed_failure_events(n: int) -> None:  # pragma: no cover - live DB
    rng = random.Random(7)
    rows = [
        (
            str(uuid.uuid4()),
            BENCH_EXPERIMENT_RUN,
            "bench_scenario",
            "upstream_delay",
            None if rng.random() < 0.05 else "2026-01-01T00:00:00Z",  # ~95% resolved, like reality
        )
        for _ in range(n)
    ]
    db.execute_many(
        "INSERT INTO telemetry.failure_events "
        "(event_id, experiment_run, scenario, fault_type, resolved_ts) VALUES (%s, %s, %s, %s, %s)",
        rows,
    )


def _time_query(sql: str, params: tuple | None = None) -> float:  # pragma: no cover - live DB
    t0 = time.perf_counter()
    db.fetch_all(sql, params)
    return (time.perf_counter() - t0) * 1000


def run() -> list[Timing]:  # pragma: no cover - live DB
    results: list[Timing] = []
    running_actions = 0
    running_faults = 0
    try:
        for checkpoint in CHECKPOINTS:
            _seed_agent_actions(checkpoint - running_actions)
            _seed_failure_events(checkpoint - running_faults)
            running_actions = running_faults = checkpoint

            results.append(
                Timing(
                    checkpoint,
                    "blast_radius_exceeded",
                    _time_query(
                        "SELECT count(*) AS n FROM telemetry.agent_actions "
                        "WHERE experiment_run = %s AND target = %s AND executed = TRUE "
                        "AND ts > now() - interval '1 hour'",
                        (BENCH_EXPERIMENT_RUN, "target-0"),
                    ),
                )
            )
            results.append(
                Timing(
                    checkpoint,
                    "_open_faults",
                    _time_query(
                        "SELECT count(*) AS n FROM telemetry.failure_events "
                        "WHERE experiment_run = %s AND resolved_ts IS NULL",
                        (BENCH_EXPERIMENT_RUN,),
                    ),
                )
            )
            results.append(
                Timing(
                    checkpoint,
                    "metrics_executed_count",
                    _time_query(
                        "SELECT count(*) FROM telemetry.agent_actions WHERE executed = TRUE"
                    ),
                )
            )
            results.append(
                Timing(
                    checkpoint,
                    "metrics_escalated_count",
                    _time_query(
                        "SELECT count(*) FROM telemetry.agent_actions "
                        "WHERE policy_decision = 'escalated'"
                    ),
                )
            )
            results.append(
                Timing(
                    checkpoint,
                    "metrics_proposals_total (unfiltered)",
                    _time_query("SELECT count(*) FROM telemetry.agent_actions"),
                )
            )
            log.info("checkpoint_done", extra={"rows": checkpoint})
    finally:
        _cleanup()
    return results


def main() -> None:  # pragma: no cover - CLI
    results = run()
    print(f"{'checkpoint':>12} {'query':<38} {'ms':>10}")
    for t in results:
        print(f"{t.checkpoint:>12} {t.query:<38} {t.ms:>10.2f}")


if __name__ == "__main__":  # pragma: no cover
    main()
