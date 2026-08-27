"""Runtime controls for the production loop: kill switch, blast-radius cap, liveness (P1, D-088).

The kill switch lives in ``control.desired_state['acde.paused']`` so it is durable and shared across
processes — flip it with ``acde pause``/``acde resume`` and the running loop stops taking actions
within one tick, no restart needed. The blast-radius cap bounds how many side-effecting actions the
agents may execute on a single target per hour, a hard safety limit independent of policy. The
heartbeat is the same durable, cross-process mechanism applied to a different question: not "should
the loop act" but "is the loop still alive" — recorded every tick, read by ``acde loop-health``.
"""

from __future__ import annotations

import datetime as dt
import json

from acde import db
from acde.config import get_settings
from acde.logging import get_logger

log = get_logger("orchestrator.control")

_PAUSE_KEY = "acde.paused"
_HEARTBEAT_KEY = "acde.loop_heartbeat"


def is_paused() -> bool:
    """True if the global kill switch is engaged."""
    row = db.fetch_one("SELECT value FROM control.desired_state WHERE key = %s", (_PAUSE_KEY,))
    return bool(row and row["value"] and row["value"].get("paused"))


def set_paused(paused: bool, actor: str = "operator") -> None:
    """Engage or release the kill switch (durable; takes effect within one loop tick)."""
    db.execute(
        "INSERT INTO control.desired_state (key, value, updated_ts) VALUES (%s, %s::jsonb, now()) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_ts = now()",
        (_PAUSE_KEY, json.dumps({"paused": paused, "by": actor})),
    )
    log.info("kill_switch", extra={"paused": paused, "actor": actor})


def record_heartbeat(experiment_run: str) -> None:
    """Stamp that the control loop is alive, right now. Called every tick (even when paused —
    "alive but taking no action" is expected; only a stopped clock is the alertable signal)."""
    db.execute(
        "INSERT INTO control.desired_state (key, value, updated_ts) VALUES (%s, %s::jsonb, now()) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_ts = now()",
        (
            _HEARTBEAT_KEY,
            json.dumps(
                {"experiment_run": experiment_run, "ts": dt.datetime.now(dt.UTC).isoformat()}
            ),
        ),
    )


def heartbeat_age_s() -> float | None:
    """Seconds since the last heartbeat, or ``None`` if the loop has never recorded one (or the
    row shape is ever unexpected — ``.get`` rather than a subscript, since this feeds a metrics
    scrape that must never 500 over a diagnostic signal, the same principle as ``_check_migrations``
    never crashing ``acde doctor``)."""
    row = db.fetch_one(
        "SELECT updated_ts FROM control.desired_state WHERE key = %s", (_HEARTBEAT_KEY,)
    )
    updated_ts = row.get("updated_ts") if row else None
    if not updated_ts:
        return None
    return (dt.datetime.now(dt.UTC) - updated_ts).total_seconds()


def blast_radius_exceeded(experiment_run: str, target: str) -> bool:
    """True if the per-target hourly cap on executed actions is reached (0 cap = unlimited)."""
    cap = get_settings().blast_radius_max_per_hour
    if cap <= 0:
        return False
    row = db.fetch_one(
        "SELECT count(*) AS n FROM telemetry.agent_actions "
        "WHERE experiment_run = %s AND target = %s AND executed = TRUE "
        "AND ts > now() - interval '1 hour'",
        (experiment_run, target),
    )
    exceeded = bool(row and int(row["n"]) >= cap)
    if exceeded:
        log.warning(
            "blast_radius_reached",
            extra={"experiment_run": experiment_run, "target": target, "cap": cap},
        )
    return exceeded
