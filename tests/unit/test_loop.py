"""Unit tests for the control loop's scheduling + lock decisions (agents mocked, no stack)."""

import asyncio
import datetime as dt
from contextlib import contextmanager
from unittest.mock import MagicMock

from acde.agents.base import CycleResult
from acde.contracts import ProposedAction, TelemetrySnapshot
from acde.llm.client import LLMResult
from acde.orchestrator import loop as loop_mod
from acde.orchestrator.loop import ControlLoop, Proposal

NOW = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.UTC)
SNAP = TelemetrySnapshot(experiment_run="t", window_start=NOW, window_end=NOW)
RESULT = LLMResult(action_json={}, tokens_in=1, tokens_out=1, model="mock")


def _action(action_type, target="tgt", agent="optimization", confidence=0.8):
    return ProposedAction(
        agent=agent,
        action_type=action_type,
        target=target,
        justification="x",
        confidence=confidence,
    )


_DEFAULT_ACTION_TYPE = {
    "monitoring": "raise_anomaly",
    "optimization": "scale_workers",
    "schema": "apply_mapping",
    "recovery": "replay",
}


def _proposal(agent, action_type=None, target="tgt", confidence=0.8):
    return Proposal(
        agent,
        _action(action_type or _DEFAULT_ACTION_TYPE[agent], target, agent, confidence),
        RESULT,
        SNAP,
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
    """Scheduling: which agents get proposed-for/acted-on under which config/fault/pause state.

    Each reactive agent proposes on its OWN distinct target (target=name) here, so nothing
    contends and every proposal wins trivially -- these tests are about enablement/gating, not
    negotiation (that's TestResolveConflicts). ``proposed``/``acted`` both record into a shared
    list per call so ordering assertions read the same way the old single-list version did.
    """

    def _loop_recording(self, monkeypatch, open_faults, config="full", paused=False):
        cl = ControlLoop("t", config)
        calls: list[str] = []
        monkeypatch.setattr(cl, "_run_agent", lambda name: calls.append(name) or "x")
        monkeypatch.setattr(
            cl, "_propose", lambda name: calls.append(name) or _proposal(name, target=name)
        )
        monkeypatch.setattr(
            cl, "_act_on", lambda name, action, result, snapshot: calls.append(f"act:{name}") or "x"
        )
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
        # monitoring first, then proposals in schema/recovery/optimization order, then each
        # (uncontested, since each proposes on its own target) gets acted on in that same order.
        assert calls == [
            "monitoring",
            "schema",
            "recovery",
            "optimization",
            "act:schema",
            "act:recovery",
            "act:optimization",
        ]

    def test_ablation_only_enabled_agents_run(self, monkeypatch):
        cl, calls = self._loop_recording(monkeypatch, open_faults=2, config="recovery_only")
        asyncio.run(cl._tick())
        assert calls == ["monitoring", "recovery", "act:recovery"]  # no schema/optimization

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


class TestResolveConflicts:
    """Direct proof of the D-038 correction: the bid decides winners, not act order + a lock
    that never actually overlaps within one process's tick (see loop.py's module docstring)."""

    def _cl(self):
        return ControlLoop("t", "full")

    def test_distinct_targets_all_win_no_contention(self):
        winners, losers = self._cl()._resolve_conflicts(
            [_proposal("schema", target="a"), _proposal("recovery", target="b")]
        )
        assert {w.agent for w in winners} == {"schema", "recovery"}
        assert losers == {}

    def test_recovery_beats_optimization_on_shared_target(self):
        # This is exactly the scenario D-038 claimed was handled "emergent from the locking
        # primitive" -- it wasn't (both ran sequentially, lock released between them, both would
        # have executed). This proves the bid actually decides it now.
        winners, losers = self._cl()._resolve_conflicts(
            [_proposal("optimization", target="shared"), _proposal("recovery", target="shared")]
        )
        assert [w.agent for w in winners] == ["recovery"]
        assert losers == {"optimization": "outbid by recovery on shared"}

    def test_schema_beats_optimization_on_shared_target(self):
        winners, losers = self._cl()._resolve_conflicts(
            [_proposal("optimization", target="shared"), _proposal("schema", target="shared")]
        )
        assert [w.agent for w in winners] == ["schema"]
        assert losers == {"optimization": "outbid by schema on shared"}

    def test_recovery_beats_schema_on_shared_target(self):
        winners, losers = self._cl()._resolve_conflicts(
            [_proposal("schema", target="shared"), _proposal("recovery", target="shared")]
        )
        assert [w.agent for w in winners] == ["recovery"]
        assert losers == {"schema": "outbid by recovery on shared"}

    def test_outbid_reason_distinguishable_from_lock_and_blast_radius(self):
        _winners, losers = self._cl()._resolve_conflicts(
            [_proposal("optimization", target="shared"), _proposal("recovery", target="shared")]
        )
        reason = losers["optimization"]
        assert "locked" not in reason
        assert "blast-radius" not in reason
        assert "outbid" in reason
