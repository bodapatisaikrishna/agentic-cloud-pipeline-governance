"""Per-run metric harvest (§5.4): the numbers one finished run contributes to the dataset.

Reads the run's telemetry tables after the response and settle phases and returns one flat
``{metric: value}`` dict, which the runner writes as one CSV row per metric.
"""

from __future__ import annotations

import statistics

from acde import db
from acde.experiments.decision_quality import is_correct
from acde.llm.client import LLMStats

FRESHNESS_FAULTS = frozenset({"upstream_delay", "ingress_burst"})


def harvest_metrics(
    experiment_run: str,
    wall_s: float,
    scenario: str = "",
    config: str = "",
    llm_stats: LLMStats | None = None,
) -> dict[str, float]:
    """Compute the §5.4 metrics for a completed run from the telemetry tables.

    ``llm_stats`` (D-104) adds the billing-accurate LLM accounting the agent_actions rows cannot
    give (they replay cached tokens); a run with no LLM (baselines) reports all zeros for those
    columns so every run shares one metric set.
    """
    from acde.telemetry.cost import STORAGE_COMPONENT, provisioning_cost

    events = db.fetch_all(
        "SELECT EXTRACT(EPOCH FROM (resolved_ts - detected_ts)) AS mttr, "
        "EXTRACT(EPOCH FROM (resolved_ts - injected_ts)) AS stall, "
        "EXTRACT(EPOCH FROM (detected_ts - injected_ts)) AS detect, fault_type "
        "FROM telemetry.failure_events "
        "WHERE experiment_run = %s AND detected_ts IS NOT NULL AND resolved_ts IS NOT NULL",
        (experiment_run,),
    )
    mttrs = [float(e["mttr"]) for e in events if e["mttr"] is not None]
    # D-105: recovery measured from injection for every config. mttr_s starts the clock at
    # detection, which non-agent configs stamp at injection but agents only when the monitor flags
    # the fault -- so it silently omits the agents' detection delay.
    from_injection = [float(e["stall"]) for e in events if e["stall"] is not None]
    detect_delays = [float(e["detect"]) for e in events if e.get("detect") is not None]
    cost = db.fetch_one(
        "SELECT COALESCE(SUM(cost_units), 0) AS c, "
        "COALESCE(SUM(cost_units) FILTER (WHERE component = %s), 0) AS storage "
        "FROM telemetry.cost_ledger WHERE experiment_run = %s",
        (STORAGE_COMPONENT, experiment_run),
    )
    interventions = db.fetch_one(
        "SELECT count(*) AS n FROM telemetry.manual_interventions WHERE experiment_run = %s",
        (experiment_run,),
    )
    # D-105: incidents a human had to handle, counted once each. manual_interventions counts
    # escalation requests: baseline files one per fault, but an agent re-proposing on every tick of
    # an open fault files one per tick. D-106: each request belongs to exactly one fault, the most
    # recently injected one open when it was filed, so overlapping faults (schema drift raises a
    # second schema_breaking event) cannot count one request twice.
    escalated = db.fetch_one(
        "SELECT count(DISTINCT (SELECT f.event_id FROM telemetry.failure_events f "
        "WHERE f.experiment_run = m.experiment_run AND f.injected_ts <= m.requested_ts "
        "AND (f.resolved_ts IS NULL OR m.requested_ts <= f.resolved_ts) "
        "ORDER BY f.injected_ts DESC, f.event_id DESC LIMIT 1)) AS n "
        "FROM telemetry.manual_interventions m WHERE m.experiment_run = %s",
        (experiment_run,),
    )
    tokens = db.fetch_one(
        "SELECT COALESCE(SUM(llm_tokens_in + llm_tokens_out), 0) AS t "
        "FROM telemetry.agent_actions WHERE experiment_run = %s",
        (experiment_run,),
    )
    # Freshness (A3, D-060): for streaming (ingestion-stall) faults, data-freshness lag equals how
    # long ingestion was stalled = the fault's open duration (resolved - injected). Batch faults
    # don't degrade streaming freshness → 0. Derived from independently-measured resolution timing.
    stalls = [
        float(e["stall"])
        for e in events
        if e["stall"] is not None and e["fault_type"] in FRESHNESS_FAULTS
    ]
    freshness_s = statistics.median(stalls) if stalls else 0.0
    executed = db.fetch_all(
        "SELECT action_type FROM telemetry.agent_actions "
        "WHERE experiment_run = %s AND executed = TRUE",
        (experiment_run,),
    )
    decision_correct = is_correct(scenario, [r["action_type"] for r in executed])
    metered = float(cost["c"]) if cost else 0.0
    storage = float(cost.get("storage") or 0.0) if cost else 0.0
    provisioning = provisioning_cost(config)
    return {
        "mttr_s": statistics.median(mttrs) if mttrs else 0.0,
        "mttr_injection_s": statistics.median(from_injection) if from_injection else 0.0,
        "detection_delay_s": statistics.median(detect_delays) if detect_delays else 0.0,
        # cost v2: measured compute/storage + the held-allocation (provisioning) cost (D-061).
        "cost_units": metered + provisioning,
        # D-105: the same total split into its three terms, so the metered part can be read alone.
        "cost_compute_units": metered - storage,
        "cost_storage_units": storage,
        "cost_provisioning_units": provisioning,
        "manual_interventions": float(interventions["n"]) if interventions else 0.0,
        "escalated_incidents": float(escalated["n"]) if escalated else 0.0,
        "llm_tokens": float(tokens["t"]) if tokens else 0.0,
        "freshness_s": freshness_s,
        "decision_correct": 1.0 if decision_correct else 0.0,
        "wall_clock_s": wall_s,
        **(llm_stats or LLMStats()).as_metrics(),
    }
