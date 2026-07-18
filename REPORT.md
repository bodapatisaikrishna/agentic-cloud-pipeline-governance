# ACDE — Replication & Extension Report

An honest account of what reproduces from arXiv:2512.23737, what doesn't, and what we add. The
authoritative numbers are regenerated into `results/results.md` by `make report`; this report is the
narrative and the "what reproduces / what doesn't" summary.

## TL;DR

ACDE is a rigorous, seeded, open reproduction of the paper's policy-bounded agentic pipeline
governance, **plus** a set of experiments the paper never ran. Two of the paper's three headline
claims reproduce directly; the third (cost) only reproduces under a disclosed cost model that credits
avoided over-provisioning. Beyond replication we contribute credible baselines, a decision-quality
metric, a cross-LLM study, and an adversarial safety evaluation.

## What reproduces / what doesn't

| Paper claim | Result | Verdict |
|---|---|---|
| MTTR ↓~45% | full vs baseline ↓~99.98% (significant; Cliff's δ=1.0) | ✅ direction reproduces, magnitude larger |
| Manual interventions ↓>70% | ↓~100% (significant) | ✅ reproduces and exceeds |
| Data freshness maintained | maintained (streaming-stall model, D-060) | ✅ |
| Operational cost ↓~25% | compute-only model: cost **rises** (agents add compute) | ⚠️ does **not** reproduce as-is |
| Operational cost ↓~25% | provisioning-aware model v2 (D-061): cost **falls** | ✅ reproduces under disclosed model |

**Why MTTR/interventions come out larger than the paper.** Our baseline resolves via a simulated
human (lognormal median ≈360 s) while the mock agent resolves near-instantly. The paper's real agents
still took real time. This is why we added **credible baselines** — see below.

**Why cost needed two models.** The paper never defines its cost model. Our first model (D-006) is
compute-only, so running agents only *adds* cost — it cannot book the savings the paper's optimization
agent gets from right-sizing. Model v2 (D-061) adds the provisioning dimension the paper implies; the
cost reduction then appears, but its magnitude depends on the over-provisioning gap assumption
(disclosed, not tuned to the paper's 25%).

## Extensions beyond the paper (verified this session)

- **Credible baselines (D-058).** `rule_based` and `autoscale` (from the paper's own §II related work).
  Verified ordering on the live stack: agents (~0.02 s) ≪ rule/autoscale on covered faults (20–30 s) ≪
  human on uncovered faults (~300–1100 s). This neutralizes the "agents only beat a slow human"
  critique.
- **Decision quality (D-059).** `decision_correct` = did the agent pick a correct mitigation? On the
  live stack it is 1 only for agent configs that choose a scenario-appropriate action (e.g. schema →
  `quarantine_partition`); non-agent baselines score 0 by construction.
- **Adversarial safety (D-062).** Live against the real OPA gate: **containment rate = 1.0** — every
  unsafe proposal (over-budget scale, unapproved rollback, rate-limit flood, breaking-schema allow)
  was denied or escalated, and the contract layer rejects out-of-allowlist action types. This is the
  first stress-test of the paper's central safety thesis.
- **Cross-LLM study (D-063).** Harness to test the paper's unproven model-agnostic claim across
  providers/models; earlier live smokes already showed that model choice changes the *chosen action*
  (GLM/Nemotron picked `quarantine_partition`, gpt-oss picked `apply_mapping` — both gate-valid) and
  latency (Nemotron 9 s/cycle vs GLM-5.2 7 min), while the gate bounded all of them — early evidence
  the "not system behavior" claim holds under bounding.
- **Bounded adaptation (D-064).** A concrete, clamped mechanism for the paper's §V adaptation claim,
  off by default to preserve determinism.

## Threats to validity

- **Baseline realism.** The human latency model is a lognormal; real on-call latency varies. Mitigated
  by adding rule-based/autoscale baselines.
- **Mock vs live reasoning.** The reproducible benchmark uses a deterministic mock policy, not live
  LLM reasoning (needed for statistical determinism). The cross-LLM study covers the live dimension
  separately; the two are never conflated.
- **Single-node.** Not a real multi-cloud deployment; results characterize control-plane behavior, not
  cloud-scale performance.
- **Cost/freshness modeling.** Both depend on disclosed models (D-060/D-061); we report the model, not
  just the number.

## Reproduce it

```bash
uv sync && cp .env.example .env
make up && make seed
make experiment-quick   # 96-run matrix (8 configs × 4 scenarios × N=3), deterministic
make report             # → results/results.md + results/figures/*.png
DOCKER_CONTEXT=... python -m acde.eval.adversarial          # safety containment
python -m acde.eval.cross_model --models <ids>              # cross-LLM (live, opt-in)
```

See `docs/PAPER_MAPPING.md` for the section-by-section mapping and `DEVIATIONS.md` for every modeling
decision.
