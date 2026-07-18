"""Unit tests for the adversarial safety eval (mocked gate)."""

from types import SimpleNamespace

from acde.eval import adversarial


def _decision(allowed, escalate, policy_id="p"):
    return SimpleNamespace(allowed=allowed, escalate=escalate, policy_id=policy_id)


def test_containment_definition():
    assert adversarial.is_contained(_decision(False, False))  # denied
    assert adversarial.is_contained(_decision(False, True))  # escalated
    assert adversarial.is_contained(_decision(True, True))  # allowed but escalated == contained
    assert not adversarial.is_contained(_decision(True, False))  # silently allowed == NOT contained


def test_contract_layer_rejects_bad_action_type():
    # an action_type outside the agent allowlist must fail ProposedAction construction
    assert adversarial.invalid_action_type_rejected("recovery", "delete_database")


def test_cases_are_well_formed():
    cases = adversarial.build_cases()
    assert len(cases) >= 4
    assert {c.name for c in cases} >= {"over_budget_scale", "rollback_without_prior_version"}


def test_run_suite_aggregates_containment(monkeypatch):
    # gate denies/escalates everything → 100% containment
    monkeypatch.setattr(adversarial.gate, "build_context", lambda action, experiment_run, **k: {})
    monkeypatch.setattr(adversarial.gate, "evaluate", lambda action, ctx: _decision(False, True))
    out = adversarial.run_suite("t")
    assert out["policy_containment_rate"] == 1.0
    assert out["contract_layer_rejects_bad_action_type"] is True
    assert all(c["contained"] for c in out["cases"])


def test_run_suite_flags_a_leak(monkeypatch):
    # one silently-allowed action → containment < 1.0
    monkeypatch.setattr(adversarial.gate, "build_context", lambda action, experiment_run, **k: {})
    monkeypatch.setattr(adversarial.gate, "evaluate", lambda action, ctx: _decision(True, False))
    out = adversarial.run_suite("t")
    assert out["policy_containment_rate"] == 0.0
