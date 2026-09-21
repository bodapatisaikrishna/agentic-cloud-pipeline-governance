# Paper campaign runbook (D-104)

The journal-paper evidence is produced by `acde.experiments.campaign`, which drives the paper matrix
to completion unattended. **It spends real API money and ~2 days of wall time; nothing here runs by
accident** (`--max-tokens` is mandatory for live arms).

## Arms

| Arm | Results dir | Configs | LLM | Runs |
|---|---|---|---|---|
| A `live-agents` | `results/paper-live` | `full` ×20/scenario, 4 ablations ×10/scenario | live | 240 |
| B `baselines` | `results/paper-baselines` | `baseline`, `rule_based`, `autoscale` ×20/scenario | none | 240 |
| C `mock-full` | `results/paper-mock` | `full` ×20/scenario | mock | 80 |

Baselines never call a model, so arm B is identical live-vs-mock and is run under `MOCK_LLM=1`.
Arm C is the mock twin of arm A's `full`, for the live-vs-mock comparison. Each run is
≈433 s (120 s warm-up + 300 s loop + 5 s settle + harvest); **do not run arms in parallel** — host load
is part of the resource-contention scenario.

## Before you start

1. `make up && make seed` — stack healthy (Docker Desktop has crashed mid-run before; the supervisor
   waits for recovery but cannot restart Docker).
2. Provider key set in `.env` (`LLM_PROVIDER`, plus `OAI_API_KEY`/`GEMINI_API_KEY`/`ANTHROPIC_API_KEY`).
   Keys are never written to results or manifests — provenance records model ids only.
3. Experiment code committed (`git status -- src infra pyproject.toml uv.lock` clean). The supervisor
   refuses a dirty tree and aborts if that code changes mid-campaign. Manuscript and
   `src/acde/analysis` edits are allowed.
4. Keep the Mac awake and plugged in (the Makefile targets wrap `caffeinate -i`).

## Pilot, then decide

```bash
make campaign-pilot MAX_TOKENS=2000000     # 8 live runs at paper timings, ~1-2 h
cat results/pilot/manifest.jsonl | head    # wall time, provenance
```

Read the pilot's `raw.csv` (`api_tokens`, `llm_calls`, `llm_degraded`, `llm_invalid`, `llm_latency_s`,
`wall_clock_s`), extrapolate to 240 live runs, and choose `MAX_TOKENS` for the real campaign. If
`llm_degraded` is high, the budget caps (`LLM_MAX_CALLS_PER_RUN`) or the provider's rate limit are
starving the loop and the results would measure that, not the model — fix before launching.

## Run / monitor / stop

```bash
make campaign MAX_TOKENS=<ceiling from pilot>    # resumable; safe to re-run after any interruption
make campaign-status                             # heartbeat: state, per-arm done/total, tokens used
make campaign-stop                               # graceful stop after the current run
```

Terminal states: `complete`, `stopped_by_request`, `stopped_token_ceiling`, `aborted_stack_unhealthy`,
`aborted_repeated_failures`, `aborted_llm_degraded`, `aborted_code_changed`. Every abort is resumable —
completed runs are recorded in each arm's `manifest.jsonl` and skipped.

## After

```bash
uv run python -m acde.eval.adversarial_corpus --out results/adversarial.json   # needs pinned OPA
uv run python -m acde.analysis.paper_artifacts --root results --out paper/generated \
    --adversarial results/adversarial.json
```

Analysis refuses to merge arms whose provenance differs (code version, timings, human/cost model,
budgets, LLM mode) — see `paper_stats.provenance_problems`.
