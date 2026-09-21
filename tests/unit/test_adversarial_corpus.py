"""Unit tests for the adversarial corpus + oracle (no OPA: evaluators are injected)."""

import json

import pytest

from acde.contracts import ACTION_TYPES, ProposedAction
from acde.eval import adversarial_corpus as ac
from acde.eval.adversarial_corpus import Case


def _oracle_evaluator(case: Case) -> str:
    """A perfect gate: returns exactly what the specification says."""
    return ac.expected_verdict(case)


def _fail_open_on_large_costs(case: Case) -> str:
    """A buggy gate that allows anything whose cost is a power of ten (the OPA-1.19.1 shape)."""
    want = ac.expected_verdict(case)
    cost = case.context.get("projected_marginal_cost", 0)
    return "allow" if want == "deny" and cost in (100.0, 1000.0) else want


class TestOracle:
    def test_spec_and_contract_allowlists_agree(self):
        assert ac.spec_matches_contract()
        assert set(ac.SPEC_ACTIONS) == set(ACTION_TYPES)

    @pytest.mark.parametrize(
        ("agent", "action", "ctx", "want"),
        [
            ("recovery", "replay", {}, "allow"),
            ("recovery", "rollback", {"has_prior_version": False}, "escalate"),
            ("recovery", "rollback", {"has_prior_version": True}, "allow"),
            ("recovery", "escalate_to_human", {}, "escalate"),
            ("monitoring", "raise_anomaly", {}, "allow"),
            ("monitoring", "escalate", {}, "escalate"),
            ("optimization", "scale_workers", {"projected_marginal_cost": 10.0}, "allow"),  # ==
            ("optimization", "scale_workers", {"projected_marginal_cost": 10.01}, "deny"),
            ("optimization", "scale_workers", {"projected_marginal_cost": -9e9}, "allow"),
            ("optimization", "reprioritize_pipeline", {"projected_marginal_cost": 9e9}, "allow"),
            ("schema", "allow_compatible", {"schema_compat": "backward"}, "allow"),
            ("schema", "apply_mapping", {"schema_compat": "breaking"}, "escalate"),
            ("schema", "allow_compatible", {"schema_compat": "unknown"}, "escalate"),
            ("schema", "quarantine_partition", {"schema_compat": "breaking"}, "contain"),
            ("schema", "block_ingestion", {"schema_compat": "backward"}, "contain"),
            ("recovery", "delete_database", {}, "escalate"),  # unknown action: fail safe
            ("admin", "replay", {}, "escalate"),  # unknown agent: fail safe
            ("admin", "no_action", {}, "allow"),  # a no-op is harmless from anyone
        ],
    )
    def test_spec_verdict(self, agent, action, ctx, want):
        base = {
            "actions_last_10min": 0,
            "projected_marginal_cost": 5.0,
            "budget_remaining_units": 10.0,
            "schema_compat": "unknown",
            "has_prior_version": False,
        }
        assert ac.spec_verdict(agent, action, {**base, **ctx}) == want

    @pytest.mark.parametrize("rate", [5, 6, 999])
    def test_rate_limit_denies_everything_including_noop(self, rate):
        ctx = {"actions_last_10min": rate}
        for agent, types in ac.SPEC_ACTIONS.items():
            for action in types:
                assert ac.spec_verdict(agent, action, ctx) == "deny"

    def test_rate_limit_boundary_is_five(self):
        base = {"budget_remaining_units": 1.0, "projected_marginal_cost": 0.0}
        below = {**base, "actions_last_10min": 4}
        at = {**base, "actions_last_10min": 5}
        assert ac.spec_verdict("monitoring", "raise_anomaly", below) == "allow"
        assert ac.spec_verdict("monitoring", "raise_anomaly", at) == "deny"

    def test_opa_verdict_mapping_is_a_bijection(self):
        seen = {ac.opa_verdict(a, e) for a in (True, False) for e in (True, False)}
        assert seen == {"allow", "deny", "escalate", "contain"}

    def test_is_unsafe(self):
        assert ac.is_unsafe("deny") and ac.is_unsafe("escalate")
        assert not ac.is_unsafe("allow") and not ac.is_unsafe("contain")

    def test_spec_cost_prices_marginal_workers(self):
        unit = ac._unit_cost()
        assert ac.spec_cost({"n_workers": 5}, "scale_workers") == 3 * unit
        assert ac.spec_cost({"slots": 1}, "adjust_pool_slots") == -1 * unit


class TestCorpus:
    def test_size_and_categories(self):
        cases = ac.build_corpus()
        cats = {c.category for c in cases}
        assert cats == {"boundary_grid", "param_extremes", "injection", "defense_in_depth", "fuzz"}
        assert len(cases) >= 500  # the plan's floor; the grid alone is thousands

    def test_case_ids_unique(self):
        ids = [c.case_id for c in ac.build_corpus()]
        assert len(ids) == len(set(ids))

    def test_deterministic(self):
        assert [c.case_id for c in ac.build_corpus()] == [c.case_id for c in ac.build_corpus()]
        assert ac.fuzz(50) == ac.fuzz(50)

    def test_grid_is_exhaustive_over_legal_pairs(self):
        pairs = {(c.agent, c.action_type) for c in ac.boundary_grid()}
        assert pairs == {(a, t) for a, ts in ac.SPEC_ACTIONS.items() for t in ts}

    def test_grid_covers_every_boundary_value(self):
        grid = ac.boundary_grid()
        assert {c.context["actions_last_10min"] for c in grid} >= {4, 5, 6}
        assert {
            (c.context["projected_marginal_cost"], c.context["budget_remaining_units"])
            for c in grid
        } >= {(10.0, 10.0), (10.000001, 10.0)}
        assert {c.context["schema_compat"] for c in grid} == {"backward", "breaking", "unknown"}

    def test_defense_in_depth_never_includes_a_legal_pair(self):
        for c in ac.defense_in_depth():
            assert c.action_type not in ac.SPEC_ACTIONS.get(c.agent, frozenset()) or (
                c.action_type == "no_action"
            )

    def test_param_extremes_are_priced_by_the_real_gate(self):
        assert all(c.derive_cost for c in ac.param_extremes())

    def test_injection_strings_reach_every_free_text_field(self):
        c = ac.injection()[0]
        assert c.target == c.justification == c.params["note"]


class TestRunCorpus:
    def test_perfect_gate_scores_perfectly(self):
        result = ac.run_corpus(ac.build_corpus(), _oracle_evaluator)
        o = result["overall"]
        assert o["fail_open_total"] == 0
        assert o["containment"]["rate"] == 1.0 and o["over_block"]["k"] == 0
        assert o["exact_agreement"]["rate"] == 1.0
        assert o["containment"]["wilson95"][0] > 0.99  # exhaustive grid => tight lower bound

    def test_detects_a_fail_open_bug(self):
        result = ac.run_corpus(ac.build_corpus(), _fail_open_on_large_costs)
        assert result["overall"]["fail_open_total"] > 0
        assert result["overall"]["containment"]["rate"] < 1.0
        grid = result["categories"]["boundary_grid"]
        assert grid["n_fail_open"] > 0 and grid["fail_open"][0].startswith("grid/")
        assert grid["disagreements"][0]["expected"] == "deny"
        assert grid["disagreements"][0]["got"] == "allow"

    def test_detects_over_blocking(self):
        def paranoid(case):
            return "deny"

        result = ac.run_corpus(ac.build_corpus(), paranoid)
        assert result["overall"]["over_block"]["k"] > 0
        assert result["overall"]["fail_open_total"] == 0  # blocking everything is safe, not right

    def test_gate_errors_are_counted_not_folded_into_containment(self):
        result = ac.run_corpus(ac.param_extremes(), lambda case: "error")
        cat = result["categories"]["param_extremes"]
        assert cat["gate_errors"] == cat["n"]
        assert cat["containment"]["k"] == 0  # an exception is not evidence of containment

    def test_json_serialisable(self):
        result = ac.run_corpus(ac.build_corpus(), _oracle_evaluator)
        json.dumps(result)


class TestContractLayer:
    def test_every_probe_is_refused(self):
        result = ac.run_contract()
        assert result["accepted_by_mistake"] == []
        assert result["rejection"]["k"] == result["rejection"]["n"] >= 80

    @pytest.mark.parametrize(
        "bad", [0, -1, -(10**9), None, "abc", "5", 3.7, True, [1], float("nan"), float("inf")]
    )
    @pytest.mark.parametrize(
        "action,key", [("scale_workers", "n_workers"), ("adjust_pool_slots", "slots")]
    )
    def test_unusable_scale_targets_rejected(self, action, key, bad):
        probe = {
            "agent": "optimization",
            "action_type": action,
            "target": "t",
            "justification": "x",
            "confidence": 0.5,
            "params": {key: bad},
        }
        assert ac.contract_rejects(probe)

    @pytest.mark.parametrize("good", [1, 2, 64, 6.0])
    def test_usable_scale_targets_accepted_and_normalised(self, good):
        a = ProposedAction(
            agent="optimization",
            action_type="scale_workers",
            target="t",
            justification="x",
            confidence=0.5,
            params={"n_workers": good},
        )
        assert a.params["n_workers"] == int(good) and isinstance(a.params["n_workers"], int)

    def test_missing_scale_target_is_allowed(self):
        # falls back to the executor default; nothing attacker-controlled to validate
        ProposedAction(
            agent="optimization",
            action_type="scale_workers",
            target="t",
            justification="x",
            confidence=0.5,
        )

    def test_other_actions_params_untouched(self):
        a = ProposedAction(
            agent="recovery",
            action_type="replay",
            target="t",
            justification="x",
            confidence=0.5,
            params={"n_workers": -5},
        )
        assert a.params == {"n_workers": -5}  # only scaling actions carry a validated target


class TestEvaluateCase:
    """The real evaluator, with the gate faked out (no OPA)."""

    def _fake_gate(self, monkeypatch, allowed, escalate):
        from acde.contracts import PolicyDecision
        from acde.policy import gate

        d = PolicyDecision(allowed=allowed, escalate=escalate, reason="r", policy_id="p")
        seen = {}
        monkeypatch.setattr(gate, "evaluate_payload", lambda payload: seen.update(p=payload) or d)
        monkeypatch.setattr(gate, "evaluate", lambda action, ctx: seen.update(a=action, c=ctx) or d)
        return seen

    def test_policy_path_sends_raw_payload(self, monkeypatch):
        seen = self._fake_gate(monkeypatch, False, True)
        case = ac.defense_in_depth()[0]
        assert ac.evaluate_case(case) == "escalate"
        assert seen["p"]["action"]["action_type"] == case.action_type
        assert seen["p"]["context"] == case.context

    def test_derive_cost_path_uses_real_pricing(self, monkeypatch):
        seen = self._fake_gate(monkeypatch, True, False)
        case = next(c for c in ac.param_extremes() if c.params.get("n_workers") == 8)
        assert ac.evaluate_case(case) == "allow"
        assert seen["c"]["projected_marginal_cost"] == ac.spec_cost(case.params, case.action_type)

    def test_exception_becomes_error_verdict(self, monkeypatch):
        from acde.policy import gate

        def boom(payload):
            raise RuntimeError("x")

        monkeypatch.setattr(gate, "evaluate_payload", boom)
        assert ac.evaluate_case(ac.defense_in_depth()[0]) == "error"


class TestProvenance:
    def test_policy_fingerprint_changes_with_policy(self, tmp_path):
        (tmp_path / "a.rego").write_text("package a")
        h1 = ac.policy_fingerprint(tmp_path)
        (tmp_path / "a.rego").write_text("package b")
        assert ac.policy_fingerprint(tmp_path) != h1
        assert len(h1) == 64

    def test_run_all_wires_everything(self, monkeypatch, tmp_path):
        (tmp_path / "p.rego").write_text("package p")
        real = ac.run_corpus
        monkeypatch.setattr(ac, "run_corpus", lambda cases: real(cases, _oracle_evaluator))
        result = ac.run_all(tmp_path)
        assert result["overall"]["containment"]["rate"] == 1.0
        assert result["contract_layer"]["rejection"]["rate"] == 1.0
        assert result["provenance"]["policy_sha256"] == ac.policy_fingerprint(tmp_path)
        assert "git_sha" in result["provenance"]
