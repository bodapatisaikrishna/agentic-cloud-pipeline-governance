"""Unit tests for the cross-model study harness (injected probe, no network)."""

from acde.eval import cross_model


def _stub_probe(model, scenario):
    # model "good" always picks a correct mitigation; model "bad" picks the wrong one.
    correct = {
        "schema_drift": "quarantine_partition",
        "upstream_delay": "replay",
        "ingress_burst": "scale_workers",
        "resource_contention": "scale_workers",
    }[scenario]
    action = correct if model == "good" else "no_action"
    return action, 42, 1.5


def test_probe_scores_correctness():
    r = cross_model.probe_model("good", "schema_drift", probe=_stub_probe)
    assert r.action_type == "quarantine_partition" and r.correct
    r2 = cross_model.probe_model("bad", "schema_drift", probe=_stub_probe)
    assert not r2.correct


def test_run_cross_model_aggregates_accuracy():
    out = cross_model.run_cross_model(
        ["good", "bad"], ["schema_drift", "upstream_delay"], probe=_stub_probe
    )
    assert out["per_model"]["good"]["accuracy"] == 1.0
    assert out["per_model"]["bad"]["accuracy"] == 0.0
    assert out["per_model"]["good"]["mean_tokens_out"] == 42.0


def test_probe_failure_is_captured():
    def _boom(model, scenario):
        raise RuntimeError("model unavailable")

    r = cross_model.probe_model("x", "schema_drift", probe=_boom)
    assert r.error and not r.correct
    # a failed model contributes no rows to its accuracy denominator
    out = cross_model.run_cross_model(["x"], ["schema_drift"], probe=_boom)
    assert out["per_model"]["x"]["n"] == 0.0
