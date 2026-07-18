"""Unit tests for the rule-based and autoscaling baselines (mocked db + human)."""

from unittest.mock import MagicMock

import pytest

from acde.experiments import baselines


@pytest.fixture
def fake_db(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(baselines, "db", fake)
    return fake


@pytest.fixture
def no_human(monkeypatch):
    called = {}
    monkeypatch.setattr(
        baselines, "resolve_via_human", lambda run, seed: called.setdefault("run", run)
    )
    return called


def test_rules_auto_resolve_covered_and_escalate_uncovered(fake_db, no_human):
    # one covered fault (upstream_delay) + one uncovered (schema_drift, needs reasoning)
    fake_db.fetch_all.return_value = [
        {"event_id": "e1", "fault_type": "upstream_delay", "detected_ts": None},
        {"event_id": "e2", "fault_type": "schema_drift", "detected_ts": None},
    ]
    auto = baselines.resolve_via_rules("run-1", seed=42)
    assert auto == 1  # only upstream_delay auto-resolved
    # the covered fault got a resolved_ts with resolution='rule'
    sqls = [c.args for c in fake_db.execute.call_args_list]
    assert any("resolved_ts = %s" in a[0] and a[1][1] == "rule" for a in sqls)
    assert no_human["run"] == "run-1"  # remaining faults escalated to the human


def test_autoscale_only_covers_resource_faults(fake_db, no_human):
    fake_db.fetch_all.return_value = [
        {"event_id": "e1", "fault_type": "resource_contention", "detected_ts": None},
        {"event_id": "e2", "fault_type": "upstream_delay", "detected_ts": None},  # data-blind
    ]
    auto = baselines.resolve_via_autoscale("run-2", seed=7)
    assert auto == 1  # resource_contention resolved; upstream_delay escalated
    assert "schema_drift" not in baselines.AUTOSCALE_COVERAGE


def test_coverage_sets_are_sane():
    assert "schema_drift" not in baselines.RULE_COVERAGE  # rules can't reconcile schema
    assert baselines.AUTOSCALE_COVERAGE < baselines.RULE_COVERAGE  # autoscale is strictly weaker
    assert "baseline" in baselines.NON_AGENT_CONFIGS
