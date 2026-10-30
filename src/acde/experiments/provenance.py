"""Run provenance (D-104): everything needed to say exactly what produced a run's numbers.

Recorded in every manifest line, so a merged dataset can never silently mix code versions, LLM
modes, timings or modelled-environment parameters.
"""

from __future__ import annotations

import hashlib
import subprocess
from typing import Any

from acde.config import Settings, get_settings
from acde.experiments.configs import PAIRED_PROFILES
from acde.experiments.scenarios import RunTimings

# Paths whose contents can change an experiment's outcome. Editing the manuscript -- or the
# post-hoc analysis code, which only reads finished results, or the evaluation drills in
# acde.eval, which no campaign run imports -- while a multi-day campaign runs must not mark (or
# abort) the runs, so "dirty" is judged on these alone (git pathspec syntax).
CODE_PATHS = (
    "src",
    "infra",
    "pyproject.toml",
    "uv.lock",
    ":(exclude)src/acde/analysis",
    ":(exclude)src/acde/eval",
)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True, timeout=10
    ).stdout.strip()


def git_state() -> dict[str, Any]:
    """Commit SHA, a fingerprint of the experiment code, and whether that code was dirty.

    ``code_tree`` hashes the blob ids of every file under CODE_PATHS (D-106). Two arms run at
    different commits that differ only in docs or analysis code share it, so they can be merged;
    ``git_sha`` alone would refuse them.
    """
    try:
        sha = _git("rev-parse", "HEAD")
        code_tree = hashlib.sha256(_git("ls-files", "-s", "--", *CODE_PATHS).encode()).hexdigest()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=no", "--", *CODE_PATHS],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            ).stdout.strip()
        )
    except (OSError, subprocess.SubprocessError):
        return {"git_sha": "unknown", "code_tree": "unknown", "git_dirty": None}
    return {"git_sha": sha, "code_tree": code_tree, "git_dirty": dirty}


def llm_models(settings: Settings) -> dict[str, str]:
    """Model ids only -- never credentials -- for the provenance record."""
    if settings.mock_llm:
        return {}
    if settings.llm_provider == "gemini":
        return {
            "reasoning": settings.gemini_model_reasoning,
            "fast": settings.gemini_model_fast,
        }
    if settings.llm_provider == "openai_compatible":
        return {"reasoning": settings.oai_model_reasoning, "fast": settings.oai_model_fast}
    return {"reasoning": settings.model_reasoning, "fast": settings.model_fast}


def seed_policy(profile: str) -> str:
    """``paired`` for profiles in PAIRED_PROFILES, else the v1 per-config policy (D-105)."""
    return "paired" if profile in PAIRED_PROFILES else "per_config"


def build_provenance(profile: str, timings: RunTimings) -> dict[str, Any]:
    """Everything needed to say *exactly* what produced a run's numbers (D-104).

    Recorded in every manifest line so a merged dataset can never silently mix conditions (the
    D-081 near-miss: a shared manifest made a whole rerun look already done). Contains model ids
    and modelled-environment parameters, never a secret.
    """
    s = get_settings()
    return {
        "profile": profile,
        # D-105: v2 resets run state, meters a fixed window, and records the split metrics. Part
        # of the provenance so a v1 and a v2 dataset can never be merged by accident.
        "measurement_protocol": "v2",
        "seed_policy": seed_policy(profile),
        "pool_baseline_slots": s.airflow_pool_baseline_slots,
        "cost_sample_interval_s": s.cost_sample_interval_s,
        "timings": {
            "warmup_s": timings.warmup_s,
            "loop_s": timings.loop_s,
            "settle_s": timings.settle_s,
        },
        "llm_provider": "mock" if s.mock_llm else s.llm_provider,
        "llm_models": llm_models(s),
        "human_latency": {"median_s": s.human_latency_median_s, "sigma": s.human_latency_sigma},
        "provisioning": {
            "static_units": s.provisioned_units_static,
            "rightsized_units": s.provisioned_units_rightsized,
            "horizon_s": s.provisioning_horizon_s,
        },
        "llm_budget": {
            "max_calls_per_run": s.llm_max_calls_per_run,
            "max_tokens_per_run": s.llm_max_tokens_per_run,
        },
        **git_state(),
    }
