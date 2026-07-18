"""Non-agent baselines: static+human, rule-based automation, and autoscaling (Phase A, D-058).

The paper compares agentic control only against a *static + human* baseline. A reviewer would ask
whether agents beat cheaper, non-LLM automation too. So we add two stronger baselines drawn from the
paper's own related work (§II.B autoscaling, §II.C rule-based automation):

* ``rule_based`` — threshold → predefined remediation. Resolves faults it has a canned rule for at a
  fixed remediation latency; anything outside its ruleset (e.g. schema drift, which needs reasoning)
  escalates to the human. Fast but brittle.
* ``autoscale`` — reactive infrastructure autoscaling. Handles resource-pressure faults only
  (contention, ingress bursts); it is *data-blind* (§II.B) so schema and upstream-data faults still
  fall to the human.

Both use the baseline's fixed monitor (stamp ``detected_ts``) and hand uncovered faults to
:func:`resolve_via_human`. This yields the expected ordering MTTR: human > rule/autoscale > agents.
"""

from __future__ import annotations

import datetime as dt

from acde import db
from acde.config import get_settings
from acde.experiments.baseline import resolve_via_human
from acde.logging import get_logger

log = get_logger("experiments.baselines")

# Non-agent responder configs (the runner drives these directly, not via the control loop).
NON_AGENT_CONFIGS = frozenset({"baseline", "rule_based", "autoscale"})

# Fault types each automaton can remediate without a human. Uncovered types escalate.
RULE_COVERAGE = frozenset({"upstream_delay", "resource_contention", "ingress_burst"})
AUTOSCALE_COVERAGE = frozenset({"resource_contention", "ingress_burst"})


def _resolve_covered(
    experiment_run: str, seed: int, covered: frozenset[str], latency_s: float, label: str
) -> int:
    """Auto-resolve covered faults at a fixed latency; escalate the rest to the human.

    Returns the number of faults auto-resolved (not counting human-resolved ones).
    """
    # Fixed monitor: stamp detection for anything not yet detected (like the human baseline).
    db.execute(
        "UPDATE telemetry.failure_events SET detected_ts = COALESCE(detected_ts, injected_ts) "
        "WHERE experiment_run = %s AND resolved_ts IS NULL",
        (experiment_run,),
    )
    open_faults = db.fetch_all(
        "SELECT event_id, fault_type, detected_ts FROM telemetry.failure_events "
        "WHERE experiment_run = %s AND resolved_ts IS NULL",
        (experiment_run,),
    )
    auto = 0
    for fault in open_faults:
        if fault["fault_type"] not in covered:
            continue
        detected = fault["detected_ts"] or dt.datetime.now(dt.UTC)
        resolved = detected + dt.timedelta(seconds=latency_s)
        db.execute(
            "UPDATE telemetry.failure_events SET resolved_ts = %s, resolution = %s "
            "WHERE event_id = %s",
            (resolved, label, fault["event_id"]),
        )
        auto += 1
    # Everything still open (outside coverage) goes to the human.
    resolve_via_human(experiment_run, seed)
    log.info(
        "baseline_automation_resolved",
        extra={"experiment_run": experiment_run, "strategy": label, "auto_resolved": auto},
    )
    return auto


def resolve_via_rules(experiment_run: str, seed: int) -> int:
    """Rule-based automation baseline: canned remediation for known faults, human for the rest."""
    return _resolve_covered(
        experiment_run, seed, RULE_COVERAGE, get_settings().rule_remediation_s, "rule"
    )


def resolve_via_autoscale(experiment_run: str, seed: int) -> int:
    """Autoscaling baseline: reacts to resource pressure only; data faults go to the human."""
    return _resolve_covered(
        experiment_run, seed, AUTOSCALE_COVERAGE, get_settings().autoscale_reaction_s, "autoscale"
    )
