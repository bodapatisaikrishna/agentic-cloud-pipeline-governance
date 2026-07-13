"""Unit tests for the OPA policy gate (mocked httpx + acde.db)."""

from unittest.mock import MagicMock

import httpx

from acde.contracts import ProposedAction
from acde.policy import gate


def _action(**kw) -> ProposedAction:
    base = {
        "agent": "optimization",
        "action_type": "scale_workers",
        "target": "streaming",
        "justification": "raise throughput",
        "confidence": 0.7,
        "params": {"n_workers": 6},
    }
    base.update(kw)
    return ProposedAction(**base)


class TestProjectedMarginalCost:
    def test_scale_up_is_positive(self):
        cost = gate.projected_marginal_cost(_action(params={"n_workers": 6}), current_workers=2)
        assert cost > 0

    def test_scale_down_is_non_positive(self):
        cost = gate.projected_marginal_cost(_action(params={"n_workers": 1}), current_workers=4)
        assert cost < 0

    def test_non_scaling_is_zero(self):
        a = _action(agent="recovery", action_type="replay", params={})
        assert gate.projected_marginal_cost(a, current_workers=2) == 0.0

    def test_adjust_pool_slots_scale_up_positive(self):
        a = _action(agent="optimization", action_type="adjust_pool_slots", params={"slots": 8})
        assert gate.projected_marginal_cost(a, current_workers=2) > 0


class TestHasPriorVersion:
    def test_true_when_older_version_below_active(self, monkeypatch):
        mgr = gate.PartitionVersionManager
        inst = mgr()
        monkeypatch.setattr(inst, "list_versions", lambda d, p: [{"version": 1}, {"version": 2}])
        monkeypatch.setattr(inst, "get_active", lambda d, p: {"version": 2})
        monkeypatch.setattr(gate, "PartitionVersionManager", lambda *a, **k: inst)
        a = _action(agent="recovery", action_type="rollback", params={"dataset": "d"})
        assert gate._has_prior_version(a) is True

    def test_false_for_non_rollback(self):
        a = _action(agent="recovery", action_type="replay", params={})
        assert gate._has_prior_version(a) is False


class TestBuildContext:
    def test_assembles_expected_keys(self, monkeypatch):
        monkeypatch.setattr(gate, "_actions_last_10min", lambda *a: 3)
        monkeypatch.setattr(gate, "_has_prior_version", lambda a: False)
        ctx = gate.build_context(_action(), experiment_run="run-1", current_workers=2)
        assert ctx["actions_last_10min"] == 3
        assert ctx["projected_marginal_cost"] > 0
        assert ctx["budget_remaining_units"] == 100.0
        assert set(ctx) >= {"schema_compat", "has_prior_version", "pipeline_criticality", "mode"}


class TestEvaluate:
    def test_maps_opa_result_to_decision(self, monkeypatch):
        monkeypatch.setattr(
            gate,
            "_query_opa",
            lambda payload: {"allowed": True, "escalate": False, "reason": "ok", "policy_id": "p"},
        )
        decision = gate.evaluate(_action(), {"actions_last_10min": 0})
        assert decision.allowed and not decision.escalate
        assert decision.policy_id == "p"

    def test_opa_error_fails_safe_escalate(self, monkeypatch):
        def boom(payload):
            raise httpx.ConnectError("down")

        monkeypatch.setattr(gate, "_query_opa", boom)
        decision = gate.evaluate(_action(), {})
        assert not decision.allowed
        assert decision.escalate
        assert decision.policy_id == "gate_failsafe"

    def test_empty_result_fails_safe(self, monkeypatch):
        monkeypatch.setattr(gate, "_query_opa", lambda payload: {})
        decision = gate.evaluate(_action(), {})
        assert decision.escalate

    def test_actions_last_10min_queries_db(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_one.return_value = {"n": 7}
        monkeypatch.setattr(gate, "db", fake)
        assert gate._actions_last_10min("optimization", "run-1") == 7
