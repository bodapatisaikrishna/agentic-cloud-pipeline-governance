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
    @pytest.fixture(autouse=True)
    def _default_provider(self, monkeypatch):
        # pin the anthropic default so these don't depend on the developer's local .env
        monkeypatch.setattr(
            client_mod, "get_settings", lambda: Settings(_env_file=None, llm_provider="anthropic")
        )

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

    def test_openai_compatible_uses_oai_models(self, monkeypatch):
        monkeypatch.setattr(
            client_mod,
            "get_settings",
            lambda: Settings(_env_file=None, llm_provider="openai_compatible"),
        )
        client = LLMClient()
        assert client.model_for("monitoring") == "nvidia/nemotron-3-super-120b-a12b"
        assert client.model_for("schema") == "z-ai/glm-5.2"

    def test_live_call_dispatches_to_openai_compatible(self, monkeypatch):
        monkeypatch.setattr(
            client_mod,
            "get_settings",
            lambda: Settings(_env_file=None, llm_provider="openai_compatible"),
        )
        called = {}
        sentinel = LLMResult({"action_type": "no_action"}, 5, 6, "z-ai/glm-5.2")

        def _fake_oai_once(self, snapshot, system_prompt, model):
            called["provider"] = "openai_compatible"
            return (lambda: sentinel), (lambda exc: False)

        monkeypatch.setattr(LLMClient, "_openai_compatible_once", _fake_oai_once)
        out = LLMClient()._live_call("schema", _snap(), "sys", "z-ai/glm-5.2")
        assert called["provider"] == "openai_compatible"
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


class TestWallClockDeadline:
    """A call that never returns must not hold the caller (the 18-minute pilot hang)."""

    def test_returns_value_within_deadline(self):
        assert client_mod.call_with_deadline(lambda: 42, 1.0) == 42

    def test_reraises_the_callees_exception(self):
        def boom():
            raise ValueError("provider said no")

        with pytest.raises(ValueError, match="provider said no"):
            client_mod.call_with_deadline(boom, 1.0)

    def test_stalled_call_times_out_instead_of_blocking(self):
        import threading
        import time

        release = threading.Event()
        started = time.monotonic()
        with pytest.raises(TimeoutError, match="deadline"):
            client_mod.call_with_deadline(lambda: release.wait(30), 0.2)
        assert time.monotonic() - started < 2.0  # bounded by the deadline, not the 30 s stall
        release.set()

    def test_stalled_provider_degrades_after_retries(self, monkeypatch):
        import threading

        monkeypatch.setattr(
            client_mod,
            "get_settings",
            lambda: Settings(_env_file=None, llm_request_timeout_s=0.05),
        )
        monkeypatch.setattr("tenacity.nap.time.sleep", lambda s: None)  # skip backoff waits
        release = threading.Event()
        client = LLMClient()
        out = client._run_with_degrade(
            "schema", _snap(), "m", lambda: release.wait(30) or None, lambda exc: False
        )
        release.set()
        assert out.action_json["action_type"] == "no_action"
        assert client.stats.degraded_unavailable == 1


class TestRequestTimeout:
    def test_default_is_bounded_well_under_a_control_loop(self):
        s = Settings(_env_file=None)
        # tenacity makes 3 attempts; the worst case must not consume a 300 s loop
        assert s.llm_request_timeout_s > 0 and 3 * s.llm_request_timeout_s < 300


class TestLLMStats:
    """D-104: the counters that make LLM accounting billing-accurate, not row-level."""

    def test_cache_hits_are_not_counted_as_api_tokens(self):
        client = LLMClient(budget=BudgetTracker(max_calls=10, max_tokens=1_000_000))
        first = client.propose("schema", _snap(), "sys")
        for _ in range(3):
            client.propose("schema", _snap(), "sys")
        assert client.stats.real_calls == 1
        assert client.stats.cache_hits == 3
        billed = client.stats.tokens_in + client.stats.tokens_out
        assert billed == first.tokens_in + first.tokens_out

    def test_budget_degrade_counted(self):
        client = LLMClient(budget=BudgetTracker(max_calls=0, max_tokens=1_000_000))
        client.propose("schema", _snap(), "sys")
        assert client.stats.degraded_budget == 1
        assert client.stats.real_calls == 0
        assert client.stats.as_metrics()["llm_degraded"] == 1.0

    def test_unavailable_is_cached_and_replay_is_visible(self, monkeypatch):
        """A transient failure is cached per snapshot key; later replays must be counted."""
        client = LLMClient(budget=BudgetTracker(max_calls=10, max_tokens=1_000_000))
        monkeypatch.setattr(
            client_mod, "get_settings", lambda: Settings(_env_file=None, mock_llm=False)
        )

        def fake_live(agent, snapshot, system_prompt, model):
            client.stats.degraded_unavailable += 1  # what _run_with_degrade does on final failure
            return LLMResult({"action_type": "no_action"}, 0, 0, model)

        monkeypatch.setattr(client, "_live_call", fake_live)
        client.propose("schema", _snap(), "sys")
        client.propose("schema", _snap(), "sys")
        client.propose("schema", _snap(), "sys")
        assert client.stats.real_calls == 0  # failures aren't real calls
        assert client.stats.degraded_unavailable == 1
        assert client.stats.degraded_replays == 2  # poisoned-cache replays are surfaced
        assert client.stats.as_metrics()["llm_degraded"] == 3.0

    def test_final_failure_increments_unavailable(self):
        def _boom() -> LLMResult:
            raise RuntimeError("provider exploded")

        client = LLMClient()
        client._run_with_degrade("schema", _snap(), "m", _boom, lambda exc: False)
        assert client.stats.degraded_unavailable == 1

    def test_as_metrics_empty_is_all_zero(self):
        from acde.llm.client import LLMStats

        assert set(LLMStats().as_metrics().values()) == {0.0}

    def test_latency_is_median_of_real_calls(self):
        from acde.llm.client import LLMStats

        stats = LLMStats(latencies_s=[1.0, 9.0, 2.0])
        assert stats.as_metrics()["llm_latency_s"] == 2.0

    def test_invalid_output_counted_by_agent(self, monkeypatch):
        from acde.agents.schema import SchemaAgent

        client = LLMClient()
        agent = SchemaAgent(experiment_run="t", llm=client)
        bad = LLMResult({"action_type": "definitely_not_valid"}, 1, 1, "m")
        monkeypatch.setattr(client, "propose", lambda *a, **k: bad)
        action, _ = agent.reason(_snap())
        assert action.action_type == "no_action"
        assert client.stats.invalid_outputs == 1
