"""Unit tests for LLMClient: routing, budget guard, in-run cache (MOCK_LLM, no API)."""

import datetime as dt

from acde.contracts import TelemetrySnapshot
from acde.llm.client import BudgetTracker, LLMClient

NOW = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.UTC)


def _snap(fault="schema_drift", compat="breaking"):
    return TelemetrySnapshot(
        experiment_run="t",
        window_start=NOW,
        window_end=NOW,
        open_anomalies=[{"fault_type": fault, "scenario": fault}],
        schema_compat=compat,
    )


class TestRouting:
    def test_monitoring_uses_fast_model(self):
        client = LLMClient()
        assert client.model_for("monitoring") == "claude-haiku-4-5"

    def test_others_use_reasoning_model(self):
        client = LLMClient()
        for agent in ("recovery", "optimization", "schema"):
            assert client.model_for(agent) == "claude-sonnet-4-6"


class TestBudget:
    def test_exceeded_degrades_to_no_action(self):
        client = LLMClient(budget=BudgetTracker(max_calls=0, max_tokens=1_000_000))
        result = client.propose("schema", _snap(), "sys")
        assert result.action_json["action_type"] == "no_action"
        assert result.tokens_in == 0  # degraded, no spend

    def test_tokens_accrue_across_calls(self):
        client = LLMClient(budget=BudgetTracker(max_calls=10, max_tokens=1_000_000))
        client.propose("schema", _snap(), "sys")
        assert client.budget.calls == 1
        assert client.budget.tokens > 0


class TestCache:
    def test_same_snapshot_served_from_cache(self):
        client = LLMClient(budget=BudgetTracker(max_calls=10, max_tokens=1_000_000))
        first = client.propose("schema", _snap(), "sys")
        second = client.propose("schema", _snap(), "sys")
        assert first is second  # identical object from cache
        assert client.budget.calls == 1  # only charged once

    def test_different_snapshot_not_cached(self):
        client = LLMClient(budget=BudgetTracker(max_calls=10, max_tokens=1_000_000))
        client.propose("schema", _snap(compat="breaking"), "sys")
        client.propose("schema", _snap(compat="backward"), "sys")
        assert client.budget.calls == 2


class TestBudgetTracker:
    def test_exceeded_on_calls_or_tokens(self):
        assert BudgetTracker(max_calls=1, max_tokens=100, calls=1).exceeded()
        assert BudgetTracker(max_calls=10, max_tokens=100, tokens=100).exceeded()
        assert not BudgetTracker(max_calls=10, max_tokens=100).exceeded()
