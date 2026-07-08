"""Unit tests for the §5.2 agent I/O contracts."""

import datetime as dt
from uuid import uuid4

import pytest
from pydantic import ValidationError

from acde.contracts import (
    ACTION_TYPES,
    FailureEvent,
    PolicyDecision,
    ProposedAction,
    TelemetrySnapshot,
)


def _action(**overrides) -> ProposedAction:
    base = {
        "agent": "recovery",
        "action_type": "retry_with_backoff",
        "target": "tpcds_ingest",
        "justification": "Task failed twice with transient network error.",
        "confidence": 0.8,
    }
    base.update(overrides)
    return ProposedAction(**base)


class TestProposedAction:
    @pytest.mark.parametrize(
        ("agent", "action_type"),
        [(agent, at) for agent, types in ACTION_TYPES.items() for at in sorted(types)],
    )
    def test_every_allowed_action_type_validates(self, agent, action_type):
        action = _action(agent=agent, action_type=action_type)
        assert action.agent == agent
        assert action.action_type == action_type

    @pytest.mark.parametrize(
        ("agent", "foreign_action"),
        [
            ("monitoring", "rollback"),
            ("optimization", "quarantine_partition"),
            ("schema", "scale_workers"),
            ("recovery", "raise_anomaly"),
        ],
    )
    def test_cross_agent_action_type_rejected(self, agent, foreign_action):
        with pytest.raises(ValidationError, match="not allowed for agent"):
            _action(agent=agent, action_type=foreign_action)

    def test_unknown_agent_rejected(self):
        with pytest.raises(ValidationError):
            _action(agent="chaos")

    @pytest.mark.parametrize("confidence", [-0.1, 1.1])
    def test_confidence_out_of_bounds_rejected(self, confidence):
        with pytest.raises(ValidationError):
            _action(confidence=confidence)

    def test_justification_over_1200_chars_rejected(self):
        with pytest.raises(ValidationError):
            _action(justification="x" * 1201)

    def test_params_default_to_empty_dict_and_ids_generated(self):
        action = _action()
        assert action.params == {}
        assert action.action_id is not None

    def test_json_round_trip(self):
        original = _action(
            action_id=uuid4(),
            agent="optimization",
            action_type="scale_workers",
            params={"n_workers": 4},
        )
        restored = ProposedAction.model_validate_json(original.model_dump_json())
        assert restored == original


class TestPolicyDecision:
    def test_shape(self):
        decision = PolicyDecision(
            allowed=False, escalate=True, reason="budget exceeded", policy_id="cost_budget"
        )
        assert not decision.allowed
        assert decision.escalate

    def test_missing_fields_rejected(self):
        with pytest.raises(ValidationError):
            PolicyDecision(allowed=True)  # type: ignore[call-arg]


class TestTelemetryContracts:
    def _snapshot(self) -> TelemetrySnapshot:
        t0 = dt.datetime(2026, 7, 8, 12, 0, tzinfo=dt.UTC)
        return TelemetrySnapshot(
            experiment_run="run-1",
            window_start=t0,
            window_end=t0 + dt.timedelta(seconds=60),
            pipeline_metrics={"freshness_s": 12.5},
        )

    def test_cache_key_excludes_window_bounds(self):
        a = self._snapshot()
        b = self._snapshot()
        b.window_start += dt.timedelta(minutes=5)
        b.window_end += dt.timedelta(minutes=5)
        assert a.cache_key_material() == b.cache_key_material()

    def test_cache_key_differs_on_state_change(self):
        a = self._snapshot()
        b = self._snapshot()
        b.pipeline_metrics["freshness_s"] = 99.0
        assert a.cache_key_material() != b.cache_key_material()

    def test_failure_event_lifecycle_fields(self):
        event = FailureEvent(
            experiment_run="run-1",
            scenario="schema_drift",
            fault_type="schema_drift",
            injected_ts=dt.datetime.now(dt.UTC),
        )
        assert event.detected_ts is None
        assert event.resolved_ts is None

    def test_invalid_fault_type_rejected(self):
        with pytest.raises(ValidationError):
            FailureEvent(
                experiment_run="run-1",
                scenario="x",
                fault_type="meteor_strike",
                injected_ts=dt.datetime.now(dt.UTC),
            )
