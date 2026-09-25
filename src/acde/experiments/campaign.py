"""Campaign supervisor: drives the multi-day paper matrix to completion unattended (D-104).

The paper campaign is ~49 h of wall time and real API spend, so "run the runner and hope" is not
acceptable. The supervisor executes the matrix **one run per child process** and, between runs:

* health-gates on Postgres / OPA / Airflow (Docker Desktop has died mid-session before) and waits
  for recovery rather than burning runs against a dead stack,
* enforces a **token ceiling** across the live arm(s) so spend cannot run away,
* detects a degraded-LLM streak (429 storms / budget starvation) and backs off, then aborts --
  a run whose LLM silently fell back to ``no_action`` would otherwise masquerade as model quality,
* refuses to start on a dirty tree and aborts if experiment code changes mid-campaign (a mixed-code
  dataset is unpublishable),
* writes an atomic heartbeat file and honours a stop file for a graceful, resumable halt.

One run per child means a crash costs at most that run; the runner's per-run row replacement makes
the retry idempotent (no duplicated rows). Arms are separate results dirs so a merged dataset can
never silently mix live and mock conditions.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from acde import db
from acde.config import Settings, get_settings
from acde.contracts import ProposedAction, TelemetrySnapshot
from acde.experiments.configs import (
    ALL_CONFIGS,
    BASELINE_CONFIGS,
    SINGLE_ABLATIONS,
    profile_runs,
)
from acde.experiments.runner import CODE_PATHS, _git_state, remaining_runs, run_id_for
from acde.experiments.scenarios import TIMINGS
from acde.llm.client import LLMClient, call_with_deadline
from acde.logging import get_logger

log = get_logger("experiments.campaign")

# Terminal states (the value written to the heartbeat and returned by run_campaign).
COMPLETE = "complete"
STOPPED = "stopped_by_request"
TOKEN_CEILING = "stopped_token_ceiling"
UNHEALTHY_ABORT = "aborted_stack_unhealthy"
FAILURE_ABORT = "aborted_repeated_failures"
DEGRADED_ABORT = "aborted_llm_degraded"
CODE_CHANGED = "aborted_code_changed"


@dataclass(frozen=True)
class Arm:
    """One independently-resumable slice of the matrix, with its own results dir and LLM mode."""

    name: str
    results_dir: Path
    configs: frozenset[str]
    live: bool  # True -> child runs with MOCK_LLM=0
    profile: str = "paper"


def arms_for(profile: str, root: Path) -> list[Arm]:
    """The campaign's arms (D-104): A live agents, B LLM-free baselines, C mock ``full``.

    ``pilot`` is a single live arm over its own tiny matrix. Baselines never call a model, so arm B
    is identical live-vs-mock and runs under ``MOCK_LLM=1`` at no API cost; arm C is the mock
    counterpart of arm A's ``full`` cell for the paired live-vs-mock comparison.
    """
    if profile in ("pilot", "pilot2"):
        return [Arm(profile, root / profile, frozenset(ALL_CONFIGS), True, profile)]
    if profile == "smoke":  # mock, seconds per run: exercises the supervisor end to end for free
        return [Arm("smoke", root / "smoke", frozenset(ALL_CONFIGS), False, "smoke")]
    return [
        Arm("live-agents", root / "paper-live", frozenset({"full", *SINGLE_ABLATIONS}), True),
        Arm("baselines", root / "paper-baselines", frozenset(BASELINE_CONFIGS), False),
        Arm("mock-full", root / "paper-mock", frozenset({"full"}), False),
    ]


@dataclass
class CampaignConfig:
    """Supervisor policy knobs (all overridable from the CLI)."""

    arms: list[Arm]
    status_path: Path
    stop_path: Path
    max_tokens: float | None = None
    max_consecutive_failures: int = 5
    failure_backoff_s: float = 60.0
    health_retry_s: float = 60.0
    health_max_wait_s: float = 3600.0
    degraded_threshold: float = 10.0  # llm_degraded events in one run that count as "degraded"
    degraded_pause_after: int = 3  # consecutive degraded runs before pausing
    degraded_abort_after: int = 6  # ... before aborting
    degraded_pause_s: float = 600.0


# --- primitives (each isolated so tests can drive the loop without a stack) -----------------------


def write_status(path: Path, status: dict[str, Any]) -> None:
    """Atomically write the heartbeat file (readers never see a torn file)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as fh:
        json.dump(status, fh, indent=2, sort_keys=True, default=str)
    os.replace(tmp, path)


def _http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return bool(200 <= resp.status < 300)
    except Exception:
        return False


# psycopg_pool's checkout has no reliably-short bound when the server is refusing connections (a
# real incident: ``db.fetch_one`` blocked for 2+ hours while Postgres was down, silently freezing
# the whole health-check loop -- not just this one check). Give it a hard wall-clock deadline like
# every LLM call already has, so a dead database can never again stall the supervisor itself.
_HEALTH_DB_TIMEOUT_S = 10.0


def check_health(settings: Settings | None = None) -> list[str]:
    """Names of unhealthy dependencies (empty list == healthy)."""
    s = settings or get_settings()
    problems: list[str] = []
    try:
        call_with_deadline(lambda: db.fetch_one("SELECT 1 AS ok"), _HEALTH_DB_TIMEOUT_S)
    except Exception:
        problems.append("postgres")
    if not _http_ok(f"{s.opa_url.rstrip('/')}/health"):
        problems.append("opa")
    airflow_root = s.airflow_url.split("/api/", 1)[0].rstrip("/")
    if not _http_ok(f"{airflow_root}/health"):
        problems.append("airflow")
    return problems


def missing_credentials(settings: Settings) -> str | None:
    """Why a live run cannot work (a provider key is unset), or None. Never reveals a key."""
    provider = settings.llm_provider
    if provider == "gemini" and not settings.gemini_api_key.get_secret_value():
        return "GEMINI_API_KEY is not set"
    if provider == "openai_compatible" and not settings.oai_api_key.get_secret_value():
        return "OAI_API_KEY is not set"
    if provider == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"):
        return "ANTHROPIC_API_KEY is not set"
    return None


def preflight_live_models(client_factory: Callable[[], LLMClient] = LLMClient) -> list[str]:
    """One real call per model role; reasons any is unusable (empty == both roles work).

    A model can be listed by a provider yet retired, unentitled, or hanging (the pilot met all
    three). Monitoring routes to the fast model and every other agent to the reasoning model, so
    probing one agent of each role covers both. An unavailable model would degrade to ``no_action``
    for the whole campaign and the numbers would measure the outage, not the system.
    """
    from acde.agents.base import load_prompt

    now = dt.datetime.now(dt.UTC)
    snapshot = TelemetrySnapshot(
        experiment_run="preflight",
        window_start=now,
        window_end=now,
        open_anomalies=[
            {"event_id": "preflight", "scenario": "schema_drift", "fault_type": "schema_drift"}
        ],
        schema_compat="breaking",
    )
    problems: list[str] = []
    for agent in ("monitoring", "recovery"):
        client = client_factory()
        model = client.model_for(agent)
        result = client.propose(agent, snapshot, load_prompt(agent))
        if client.stats.degraded_unavailable:
            problems.append(f"{agent}: model {model} is unavailable")
            continue
        try:
            ProposedAction.model_validate({**result.action_json, "agent": agent})
        except ValidationError as exc:
            problems.append(f"{agent}: model {model} returned invalid output ({exc.error_count()})")
    return problems


def code_changed_since(sha: str) -> bool:
    """True if experiment code (tracked, incl. uncommitted edits) differs from ``sha``."""
    try:
        rc = subprocess.run(
            ["git", "diff", "--quiet", sha, "--", *CODE_PATHS], timeout=30, check=False
        ).returncode
    except (OSError, subprocess.SubprocessError):
        return False  # can't tell; don't abort a multi-day run over a transient git error
    return rc == 1


def total_tokens(arms: list[Arm]) -> float:
    """Billing-accurate API tokens spent so far across the live arms (from ``api_tokens``)."""
    total = 0.0
    for arm in arms:
        raw = arm.results_dir / "raw.csv"
        if not arm.live or not raw.exists():
            continue
        with raw.open(newline="") as fh:
            for row in csv.DictReader(fh):
                if row["metric"] == "api_tokens":
                    total += float(row["value"])
    return total


def run_metric(results_dir: Path, run_id: str, metric: str) -> float | None:
    """One metric of one run from raw.csv, or None if absent."""
    raw = results_dir / "raw.csv"
    if not raw.exists():
        return None
    with raw.open(newline="") as fh:
        for row in csv.DictReader(fh):
            if row["run_id"] == run_id and row["metric"] == metric:
                return float(row["value"])
    return None


def spawn_runner(arm: Arm, timeout_s: float, log_path: Path) -> int:
    """Run exactly one pending cell of ``arm`` in a child process; returns its exit code.

    A child that outlives ``timeout_s`` is killed and reported as 124 (the GNU ``timeout`` code).
    """
    cmd = [
        sys.executable,
        "-m",
        "acde.experiments.runner",
        "--profile",
        arm.profile,
        "--results-dir",
        str(arm.results_dir),
        "--configs",
        ",".join(sorted(arm.configs)),
        "--max-runs",
        "1",
    ]
    env = {**os.environ, "MOCK_LLM": "0" if arm.live else "1"}
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as fh:
        try:
            return subprocess.run(
                cmd, env=env, stdout=fh, stderr=subprocess.STDOUT, timeout=timeout_s, check=False
            ).returncode
        except subprocess.TimeoutExpired:
            return 124


# --- the supervisor loop ------------------------------------------------------------------------


class _Progress:
    """Heartbeat bookkeeping shared by the loop's helpers."""

    def __init__(self, cfg: CampaignConfig, now: Callable[[], float]) -> None:
        self.cfg = cfg
        self.now = now
        self.started = dt.datetime.now(dt.UTC).isoformat()
        self.extra: dict[str, Any] = {}

    def emit(self, state: str, message: str = "", **fields: Any) -> None:
        self.extra.update(fields)
        arms = {}
        for arm in self.cfg.arms:
            total = len([r for r in profile_runs(arm.profile) if r.config in arm.configs])
            left = len(remaining_runs(arm.profile, arm.results_dir, arm.configs))
            arms[arm.name] = {"done": total - left, "total": total}
        write_status(
            self.cfg.status_path,
            {
                "state": state,
                "message": message,
                "started": self.started,
                "updated": dt.datetime.now(dt.UTC).isoformat(),
                "arms": arms,
                "tokens_used": total_tokens(self.cfg.arms),
                "max_tokens": self.cfg.max_tokens,
                **self.extra,
            },
        )
        log.info("campaign_status", extra={"state": state, "detail": message, **fields})


def _wait_healthy(
    cfg: CampaignConfig,
    prog: _Progress,
    health: Callable[[], list[str]],
    sleep: Callable[[float], None],
) -> bool:
    """Block until the stack is healthy; False if it stays down past ``health_max_wait_s``."""
    waited = 0.0
    while True:
        problems = health()
        if not problems:
            return True
        if waited >= cfg.health_max_wait_s:
            prog.emit(UNHEALTHY_ABORT, f"still unhealthy after {waited:.0f}s: {problems}")
            return False
        prog.emit("waiting_for_health", f"unhealthy: {problems}")
        sleep(cfg.health_retry_s)
        waited += cfg.health_retry_s


def run_campaign(
    cfg: CampaignConfig,
    *,
    start_sha: str,
    invoke: Callable[[Arm], int],
    health: Callable[[], list[str]],
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
    code_changed: Callable[[str], bool] = code_changed_since,
) -> str:
    """Run every arm to completion (or a guarded stop). Returns the terminal state."""
    prog = _Progress(cfg, now)
    failures = 0
    degraded_streak = 0

    for arm in cfg.arms:
        while True:
            pending = remaining_runs(arm.profile, arm.results_dir, arm.configs)
            if not pending:
                break
            run_id = run_id_for(pending[0])

            if cfg.stop_path.exists():
                prog.emit(STOPPED, f"stop file {cfg.stop_path} present", next_run=run_id)
                return STOPPED
            if code_changed(start_sha):
                prog.emit(CODE_CHANGED, f"experiment code differs from {start_sha[:10]}")
                return CODE_CHANGED
            if cfg.max_tokens is not None and arm.live and total_tokens(cfg.arms) >= cfg.max_tokens:
                prog.emit(TOKEN_CEILING, f"token ceiling {cfg.max_tokens:.0f} reached")
                return TOKEN_CEILING
            if not _wait_healthy(cfg, prog, health, sleep):
                return UNHEALTHY_ABORT

            prog.emit("running", f"{arm.name}: {run_id}", arm=arm.name, current_run=run_id)
            rc = invoke(arm)
            after = remaining_runs(arm.profile, arm.results_dir, arm.configs)
            if rc != 0 or len(after) >= len(pending):
                # Non-zero exit, or a "successful" child that recorded nothing: either way retry.
                failures += 1
                prog.emit(
                    "run_failed",
                    f"{run_id}: exit {rc} (consecutive failures {failures})",
                    consecutive_failures=failures,
                )
                if failures >= cfg.max_consecutive_failures:
                    prog.emit(FAILURE_ABORT, f"{failures} consecutive failures at {run_id}")
                    return FAILURE_ABORT
                sleep(cfg.failure_backoff_s)
                continue
            failures = 0

            if arm.live:
                degraded = run_metric(arm.results_dir, run_id, "llm_degraded") or 0.0
                degraded_streak = degraded_streak + 1 if degraded >= cfg.degraded_threshold else 0
                if degraded_streak >= cfg.degraded_abort_after:
                    prog.emit(DEGRADED_ABORT, f"{degraded_streak} consecutive degraded-LLM runs")
                    return DEGRADED_ABORT
                if degraded_streak >= cfg.degraded_pause_after:
                    prog.emit(
                        "backing_off",
                        f"{degraded_streak} consecutive degraded-LLM runs; pausing",
                        degraded_streak=degraded_streak,
                    )
                    sleep(cfg.degraded_pause_s)
            prog.emit("run_done", run_id, last_run=run_id, consecutive_failures=0)

    prog.emit(COMPLETE, "all arms complete")
    return COMPLETE


# --- CLI ----------------------------------------------------------------------------------------


def main() -> None:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(description="ACDE paper-campaign supervisor")
    parser.add_argument("--profile", choices=["paper", "pilot", "pilot2", "smoke"], default="paper")
    parser.add_argument("--results-root", default=None)
    parser.add_argument("--arms", default=None, help="comma-separated arm names (default: all)")
    parser.add_argument(
        "--max-tokens", type=float, default=None, help="live-arm token ceiling (required if live)"
    )
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    root = Path(args.results_root or settings.results_dir)
    arms = arms_for(args.profile, root)
    if args.arms:
        wanted = {a.strip() for a in args.arms.split(",")}
        arms = [a for a in arms if a.name in wanted]
        if not arms:
            sys.exit(f"no arm matches {sorted(wanted)}")
    if any(a.live for a in arms):
        if args.max_tokens is None:
            sys.exit("--max-tokens is required when a live arm is scheduled (set from pilot)")
        if (why := missing_credentials(settings)) is not None:
            sys.exit(f"live arm cannot run: {why}")
        os.environ["MOCK_LLM"] = "0"  # the preflight must hit the real provider
        get_settings.cache_clear()
        if bad := preflight_live_models():
            sys.exit("live model preflight failed: " + "; ".join(bad))

    state = _git_state()
    if not args.allow_dirty and (state["git_dirty"] or state["git_sha"] == "unknown"):
        sys.exit("experiment code has uncommitted changes (or git is unavailable); commit first")

    timings = TIMINGS[args.profile]
    cfg = CampaignConfig(
        arms=arms,
        status_path=root / "campaign_status.json",
        stop_path=root / "CAMPAIGN_STOP",
        max_tokens=args.max_tokens,
    )
    child_timeout_s = 3 * (timings.warmup_s + timings.loop_s + timings.settle_s) + 600
    log_path = root / "campaign.log"
    final = run_campaign(
        cfg,
        start_sha=str(state["git_sha"]),
        invoke=lambda arm: spawn_runner(arm, child_timeout_s, log_path),
        health=check_health,
    )
    print(f"campaign finished: {final}")
    sys.exit(0 if final == COMPLETE else 1)


if __name__ == "__main__":  # pragma: no cover
    main()
