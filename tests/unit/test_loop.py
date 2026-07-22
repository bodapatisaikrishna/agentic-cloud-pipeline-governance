"""Unit tests for the control loop's scheduling + lock decisions (agents mocked, no stack)."""

import asyncio
import datetime as dt
from contextlib import contextmanager
from unittest.mock import MagicMock

from acde.agents.base import CycleResult
from acde.contracts import ProposedAction, TelemetrySnapshot
from acde.llm.client import LLMResult
from acde.orchestrator import loop as loop_mod
from acde.orchestrator.loop import ControlLoop

NOW = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.UTC)
SNAP = TelemetrySnapshot(experiment_run="t", window_start=NOW, window_end=NOW)
RESULT = LLMResult(action_json={}, tokens_in=1, tokens_out=1, model="mock")


def _action(action_type, target="tgt", agent="optimization"):
    return ProposedAction(
        agent=agent,
        action_type=action_type,
        target=target,
        justification="x",
        confidence=0.8,
    )


def _lock(acquired: bool):
    @contextmanager
    def _cm(target):
        yield acquired

    return _cm


class TestRunAgent:
    def _agent_returning(self, action):
        agent = MagicMock()
        agent.observe.return_value = SNAP
        agent.reason.return_value = (action, RESULT)
        agent.act.return_value = CycleResult(action, True, "did it", "p")
        return agent

    def test_no_action_never_locks_or_acts(self, monkeypatch):
        cl = ControlLoop("t", "full")
        agent = self._agent_returning(_action("no_action"))
        cl.agents["monitoring"] = agent
        assert cl._run_agent("monitoring") == "no_action"
        agent.act.assert_not_called()

    def test_real_action_locks_then_acts(self, monkeypatch):
        monkeypatch.setattr(loop_mod, "target_advisory_lock", _lock(True))
        monkeypatch.setattr(loop_mod.control, "blast_radius_exceeded", lambda run, target: False)
        cl = ControlLoop("t", "full")
        agent = self._agent_returning(_action("scale_workers", "streaming"))
        cl.agents["optimization"] = agent
        out = cl._run_agent("optimization")
        agent.act.assert_called_once()
        assert out == "did it"

    def test_locked_target_is_skipped(self, monkeypatch):
        monkeypatch.setattr(loop_mod, "target_advisory_lock", _lock(False))
        cl = ControlLoop("t", "full")
        agent = self._agent_returning(_action("scale_workers", "streaming"))
        cl.agents["optimization"] = agent
        out = cl._run_agent("optimization")
        agent.act.assert_not_called()
        assert "locked" in out

    def test_blast_radius_exceeded_skips_action(self, monkeypatch):
        monkeypatch.setattr(loop_mod, "target_advisory_lock", _lock(True))
        monkeypatch.setattr(loop_mod.control, "blast_radius_exceeded", lambda run, target: True)
        cl = ControlLoop("t", "full")
        agent = self._agent_returning(_action("scale_workers", "streaming"))
        cl.agents["optimization"] = agent
        out = cl._run_agent("optimization")
        agent.act.assert_not_called()
        assert "blast-radius" in out


class TestTick:
    def _loop_recording(self, monkeypatch, open_faults, config="full", paused=False):
        cl = ControlLoop("t", config)
        calls: list[str] = []
        monkeypatch.setattr(cl, "_run_agent", lambda name: calls.append(name) or "x")
        monkeypatch.setattr(cl, "_open_faults", lambda: open_faults)
        monkeypatch.setattr(loop_mod.control, "is_paused", lambda: paused)
        return cl, calls

    def test_no_faults_only_monitoring(self, monkeypatch):
        cl, calls = self._loop_recording(monkeypatch, open_faults=0)
        asyncio.run(cl._tick())
        assert calls == ["monitoring"]

    def test_faults_trigger_reactive_in_order(self, monkeypatch):
        cl, calls = self._loop_recording(monkeypatch, open_faults=2)
        asyncio.run(cl._tick())
        # monitoring first, then reactive in schema, recovery, optimization order
        assert calls == ["monitoring", "schema", "recovery", "optimization"]

    def test_ablation_only_enabled_agents_run(self, monkeypatch):
        cl, calls = self._loop_recording(monkeypatch, open_faults=2, config="recovery_only")
        asyncio.run(cl._tick())
        assert calls == ["monitoring", "recovery"]  # no schema/optimization

    def test_baseline_runs_nothing(self, monkeypatch):
        cl, calls = self._loop_recording(monkeypatch, open_faults=2, config="baseline")
        asyncio.run(cl._tick())
        assert calls == []

    def test_paused_runs_nothing(self, monkeypatch):
        # kill switch: even with open faults on a fully-enabled config, a paused loop takes no
        # actions at all (checked before monitoring even runs).
        cl, calls = self._loop_recording(monkeypatch, open_faults=2, paused=True)
        asyncio.run(cl._tick())
        assert calls == []
