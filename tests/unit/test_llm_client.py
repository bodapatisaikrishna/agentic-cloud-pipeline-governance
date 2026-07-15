"""Unit tests for LLMClient: routing, budget guard, in-run cache (MOCK_LLM, no API)."""

import datetime as dt

import pytest

from acde.config import Settings
from acde.contracts import TelemetrySnapshot
from acde.llm import client as client_mod
from acde.llm.client import BudgetTracker, LLMClient, LLMResult

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


class TestProviderRouting:
    def test_gemini_provider_uses_gemini_models(self, monkeypatch):
        monkeypatch.setattr(
            client_mod, "get_settings", lambda: Settings(_env_file=None, llm_provider="gemini")
        )
        client = LLMClient()
        assert client.model_for("monitoring") == "gemini-2.5-flash"
        assert client.model_for("schema") == "gemini-2.5-pro"

    def test_live_call_dispatches_to_configured_provider(self, monkeypatch):
        monkeypatch.setattr(
            client_mod, "get_settings", lambda: Settings(_env_file=None, llm_provider="gemini")
        )
        called = {}
        sentinel = LLMResult({"action_type": "no_action"}, 3, 4, "gemini-2.5-pro")

        def _fake_gemini_once(self, snapshot, system_prompt, model):
            called["provider"] = "gemini"
            return (lambda: sentinel), (lambda exc: False)

        def _fake_anthropic_once(self, snapshot, system_prompt, model):
            called["provider"] = "anthropic"
            return (lambda: sentinel), (lambda exc: False)

        monkeypatch.setattr(LLMClient, "_gemini_once", _fake_gemini_once)
        monkeypatch.setattr(LLMClient, "_anthropic_once", _fake_anthropic_once)
        out = LLMClient()._live_call("schema", _snap(), "sys", "gemini-2.5-pro")
        assert called["provider"] == "gemini"
        assert out is sentinel

    def test_unknown_provider_raises(self, monkeypatch):
        monkeypatch.setattr(
            client_mod, "get_settings", lambda: Settings(_env_file=None, llm_provider="bogus")
        )
        with pytest.raises(ValueError, match="unknown llm_provider"):
            LLMClient()._live_call("schema", _snap(), "sys", "m")

    def test_degrade_on_final_failure(self):
        def _boom() -> LLMResult:
            raise RuntimeError("provider exploded")

        out = LLMClient()._run_with_degrade("schema", _snap(), "m", _boom, lambda exc: False)
        assert out.action_json["action_type"] == "no_action"
        assert out.tokens_in == 0

    def test_mock_path_is_provider_independent(self, monkeypatch):
        # MOCK_LLM stays deterministic regardless of the selected live provider
        monkeypatch.setattr(
            client_mod,
            "get_settings",
            lambda: Settings(_env_file=None, llm_provider="gemini", mock_llm=True),
        )
        out = LLMClient(budget=BudgetTracker(max_calls=10, max_tokens=1_000_000)).propose(
            "schema", _snap(), "sys"
        )
        assert out.action_json["action_type"] == "quarantine_partition"


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
