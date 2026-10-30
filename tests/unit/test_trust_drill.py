"""Unit tests for the trust-core drill's pure summary and environment override."""

import os

from acde.config import get_settings
from acde.eval import trust_drill


def _trial(stop, executed=0, resume=0.4):
    return {
        "stop_latency_s": stop,
        "actions_after_pause": 1,
        "executed_after_pause": executed,
        "resume_latency_s": resume,
        "tick_s": 0.5,
    }


def test_summary_reports_worst_case_and_violations():
    s = trust_drill.summarize([_trial(0.2), _trial(0.6, executed=1), _trial(0.4, resume=None)])
    assert s["trials"] == 3
    assert s["stop_latency_median_s"] == 0.4 and s["stop_latency_max_s"] == 0.6
    assert s["executed_after_pause_total"] == 1
    assert s["resumed_trials"] == 2 and s["resume_latency_median_s"] == 0.4


def test_empty_summary():
    s = trust_drill.summarize([])
    assert s["trials"] == 0 and s["stop_latency_max_s"] is None


def test_env_override_is_undone():
    before = get_settings().acde_mode
    with trust_drill._env(ACDE_MODE="approval"):
        assert get_settings().acde_mode == "approval"
    assert get_settings().acde_mode == before
    assert os.environ.get("ACDE_MODE") in (None, before)


def test_drills_and_analysis_do_not_count_as_experiment_code():
    from acde.experiments.provenance import CODE_PATHS

    assert ":(exclude)src/acde/eval" in CODE_PATHS
    assert ":(exclude)src/acde/analysis" in CODE_PATHS
    assert "src" in CODE_PATHS and "infra" in CODE_PATHS
