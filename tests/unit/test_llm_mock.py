"""Unit tests: the mock LLM covers every agent x scenario with valid ProposedActions."""

import datetime as dt

import pytest

from acde.contracts import ProposedAction, TelemetrySnapshot
from acde.llm import mock

NOW = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.UTC)
AGENTS = ["monitoring", "recovery", "optimization", "schema"]


def _snapshot(fault: str | None, schema_compat: str = "unknown", freshness: float = 0.0):
    return TelemetrySnapshot(
        experiment_run="t",
        window_start=NOW,
        window_end=NOW,
        open_anomalies=[{"fault_type": fault, "scenario": fault}] if fault else [],
        schema_compat=schema_compat,
        pipeline_metrics={"freshness_s": freshness},
    )


# (scenario, schema_compat, freshness, expected action per agent)
SCENARIOS = {
    "schema_drift": (
        "breaking",
        0.0,
        {
            "monitoring": "raise_anomaly",
            "schema": "quarantine_partition",
            "optimization": "no_action",
            "recovery": "no_action",
        },
    ),
    "upstream_delay": (
        "unknown",
        0.0,
        {
            "monitoring": "raise_anomaly",
            "recovery": "replay",
            "schema": "no_action",
            "optimization": "no_action",
        },
    ),
    "ingress_burst": (
        "unknown",
        120.0,
        {
            "monitoring": "raise_anomaly",
            "optimization": "scale_workers",
            "schema": "no_action",
            "recovery": "no_action",
        },
    ),
    "resource_contention": (
        "unknown",
        0.0,
        {
            "monitoring": "raise_anomaly",
            "optimization": "adjust_pool_slots",
            "schema": "no_action",
            "recovery": "no_action",
        },
    ),
}


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_scenario_produces_expected_actions(scenario):
    schema_compat, freshness, expected = SCENARIOS[scenario]
    snap = _snapshot(scenario, schema_compat, freshness)
    for agent, action_type in expected.items():
        result = mock.mock_propose(agent, snap)
        assert result.action_json["action_type"] == action_type
        # every mock response validates as a ProposedAction
        ProposedAction.model_validate({**result.action_json, "action_id": str(_uuid())})
        assert result.tokens_in > 0 and result.model == "mock"


def test_deterministic():
    snap = _snapshot("ingress_burst", freshness=120.0)
    a = mock.mock_propose("optimization", snap)
    b = mock.mock_propose("optimization", snap)
    assert a == b


def test_nominal_snapshot_is_no_action_for_all():
    snap = _snapshot(None)
    for agent in AGENTS:
        assert mock.mock_propose(agent, snap).action_json["action_type"] == "no_action"


def _uuid():
    from uuid import uuid4

    return uuid4()
