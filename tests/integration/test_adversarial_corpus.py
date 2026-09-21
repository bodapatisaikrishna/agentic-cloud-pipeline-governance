"""Live adversarial corpus against the pinned OPA (requires OPA up: `make up-core`).

This is the regression guard for D-104's headline safety claim. It also catches the class of
failure the corpus first found on an unpinned OPA (1.19.1: float comparisons like 1000.0 vs 10.0
evaluated "within budget"): if the OPA image is ever bumped and the semantics move, this fails.
"""

from __future__ import annotations

import pytest

from acde.eval import adversarial_corpus as ac

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def result():
    return ac.run_all()


def test_no_unsafe_proposal_is_silently_allowed(result):
    assert result["overall"]["fail_open_total"] == 0, result["categories"]


def test_policy_matches_the_independent_specification_exactly(result):
    for name, cat in result["categories"].items():
        assert cat["n_disagreements"] == 0, (name, cat["disagreements"])


def test_gate_never_raises_on_corpus(result):
    assert result["overall"]["gate_errors_total"] == 0


def test_contract_layer_refuses_every_probe(result):
    assert result["contract_layer"]["accepted_by_mistake"] == []
