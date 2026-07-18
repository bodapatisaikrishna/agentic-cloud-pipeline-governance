"""Cross-LLM reasoning study (C, D-063): does model choice matter under policy bounds?

The paper claims (§VI.A) the architecture is "model-agnostic" — that model choice affects only
"verbosity and latency, not system behavior" — but presents **no data**. This harness tests the
claim empirically: it runs the same fault scenario through many models and measures, for each,
whether it proposes a *correct* mitigation (`decision_quality`), plus latency and token cost. Since
every proposal still passes the OPA gate, the study also shows whether the gate equalizes outcomes.

This path makes real LLM calls (opt-in, user-run). The aggregation/scoring logic is unit-tested with
an injected probe; the live sweep is driven from the CLI with the user's key.
"""

from __future__ import annotations

import datetime as dt
import time
from collections.abc import Callable
from dataclasses import dataclass

from acde.contracts import TelemetrySnapshot
from acde.experiments.decision_quality import is_correct
from acde.logging import get_logger

log = get_logger("eval.cross_model")


@dataclass
class ModelResult:
    model: str
    scenario: str
    action_type: str
    correct: bool
    latency_s: float
    tokens_out: int
    error: str = ""


def _snapshot(scenario: str) -> TelemetrySnapshot:
    now = dt.datetime.now(dt.UTC)
    return TelemetrySnapshot(
        experiment_run="cross-model",
        window_start=now,
        window_end=now,
        open_anomalies=[{"fault_type": scenario, "scenario": scenario}],
        schema_compat="breaking" if scenario == "schema_drift" else "unknown",
    )


# A real probe: (model, scenario) -> (action_type, tokens_out, latency_s). Behind a seam so the
# harness is unit-testable; the default probe hits the OpenAI-compatible endpoint.
Probe = Callable[[str, str], tuple[str, int, float]]


def _openai_probe(model: str, scenario: str) -> tuple[str, int, float]:  # pragma: no cover - net
    import openai

    from acde.config import get_settings
    from acde.llm.client import _extract_json

    s = get_settings()
    client = openai.OpenAI(
        base_url=s.oai_base_url, api_key=s.oai_api_key, timeout=40, max_retries=0
    )
    system = (
        "You are a data-pipeline recovery agent. Respond with ONLY a JSON object "
        '{"action_type": "...", "target": "...", "confidence": 0..1}. '
        "Valid action_types include quarantine_partition, block_ingestion, apply_mapping, replay, "
        "retry_with_backoff, partial_recompute, scale_workers, adjust_pool_slots, "
        "reprioritize_pipeline, no_action."
    )
    t = time.time()
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        max_tokens=8192,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": _snapshot(scenario).model_dump_json()},
        ],
    )
    dt_s = time.time() - t
    obj = _extract_json(resp.choices[0].message.content or "")
    out = resp.usage.completion_tokens if resp.usage else 0
    return str(obj.get("action_type", "?")), int(out), dt_s


def probe_model(model: str, scenario: str, probe: Probe | None = None) -> ModelResult:
    """Probe one model on one scenario and score decision correctness."""
    probe = probe or _openai_probe
    try:
        action_type, tokens_out, latency = probe(model, scenario)
    except Exception as exc:  # keep the sweep going on per-model failure
        return ModelResult(model, scenario, "-", False, 0.0, 0, error=str(exc)[:80])
    correct = is_correct(scenario, [action_type])
    return ModelResult(model, scenario, action_type, correct, latency, tokens_out)


def run_cross_model(
    models: list[str], scenarios: list[str], probe: Probe | None = None
) -> dict[str, object]:
    """Run every (model, scenario) and summarise correctness / latency / tokens per model."""
    rows = [probe_model(m, s, probe) for m in models for s in scenarios]
    per_model: dict[str, dict[str, float]] = {}
    for m in models:
        mrows = [r for r in rows if r.model == m and not r.error]
        n = len(mrows)
        per_model[m] = {
            "accuracy": (sum(r.correct for r in mrows) / n) if n else 0.0,
            "mean_latency_s": (sum(r.latency_s for r in mrows) / n) if n else 0.0,
            "mean_tokens_out": (sum(r.tokens_out for r in mrows) / n) if n else 0.0,
            "n": float(n),
        }
    return {"rows": [r.__dict__ for r in rows], "per_model": per_model}


def main() -> None:  # pragma: no cover - CLI
    import argparse
    import json

    from acde.experiments.scenarios import SCENARIOS

    parser = argparse.ArgumentParser(description="ACDE cross-model reasoning study (live)")
    parser.add_argument("--models", required=True, help="comma-separated model ids")
    args = parser.parse_args()
    out = run_cross_model(args.models.split(","), list(SCENARIOS))
    print(json.dumps(out["per_model"], indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
