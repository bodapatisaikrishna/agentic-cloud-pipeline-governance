# CONTEXT.md: Project Handoff (read this first)

This file holds everything a new machine or a new Claude Code account needs to continue this project.
It was last updated on 2026-10-09 at commit `2a84bd0`. Read this file first, then `CLAUDE.md`, which
holds the repo rules.

---

## 1. What this project is

**ACDE (Agentic Cloud Data Engineering)** is a research-grade implementation and extension of
arXiv:2512.23737, *"Governing Cloud Data Pipelines with Agentic AI"* (Kirubakaran et al., 2025).

- Four bounded LLM agents (**monitoring, optimization, schema, recovery**) observe pipeline
  telemetry and output only a pydantic-validated `ProposedAction`. They never emit code.
- Every proposal goes through an **OPA/Rego policy gate** before it executes. The gate covers the
  rate limit, cost budget, recovery approval and schema compatibility. If OPA is unreachable, the
  gate escalates to a human.
- Data plane: Airflow batch, Redpanda streaming, PostgreSQL (schemas `telemetry`, `warehouse`,
  `control`).
- Beyond the base paper, the project adds a trust core (shadow/approval/autonomous modes, kill
  switch, blast-radius cap), an operator API and dashboard, RBAC and multi-tenancy, connectors
  (Airflow/Prefect), a Helm chart, an adversarial corpus, and a cross-model harness.
- **GitHub:** https://github.com/bodapatisaikrishna/agentic-cloud-pipeline-governance (branch `main`)
- **Authors (paper order):** B Sai Krishna, Vignes VM, I Mahalakshmi, Sri Harini MP.

## 2. Current status (2026-10-09)

- All software phases are done and verified. These are 0–9, A–F, P1–P5, Tier 1/2, the hardening
  passes, the feature-focus work (D-100–D-103) and the journal-paper infrastructure (D-104). See the
  phase table in `README.md`.
- **Live paper campaign:** completed 2026-09-26, 560/560 runs with zero aborts.
- **Current work:** the IEEE journal manuscript in `paper/`. The software itself is finished.
- **Quality gates:** `make lint` passes (ruff + mypy), and `make test-unit` passes 752 tests at
  about 95% coverage.

## 3. The paper (main active work)

**Title:** *A Policy-Bounded Agentic Framework for Autonomous Governance of Cloud Data Pipelines*

**Central thesis:** the same system run through the same code path produces very different results
under a deterministic **mock** LLM than under a **live** LLM. A mock evaluation therefore cannot
stand in for a live one.

### Layout
- `paper/main.tex`: IEEEtran `[journal]` class. It `\input`s `sections/00_abstract.tex` through
  `08_conclusion.tex` (01 intro, 02 related, 03 problem, 03 system, 04 method, 05 results,
  06 lessons, 07 discussion, 08 conclusion).
- `paper/generated/`: **auto-generated** tables, figures and `numbers.tex` (`\N...` macros). These
  files must never be hand-edited. Every number in the prose is a `\N...` macro, and no number is
  typed by hand.
- `paper/refs.bib`: 30 verified references (14 arXiv-only; the rest are peer-reviewed) (arXiv DOIs use the form
  `10.48550/arXiv.<id>`). IEEE-abbreviated venue names. No `note` fields beyond venue tags.
- `paper/figures/system_architecture.pdf`: Figure 1, a vector, Visio-style drawing produced by
  `scripts/draw_architecture.py`. The old `system_architecture_7layer.png` was rejected by the
  professor as looking AI-generated, and is no longer used.
- `paper/data/`: committed per-run campaign data (`paper-live`, `paper-baselines`, `paper-mock`,
  `adversarial*.json`). The paper is rebuilt from this data.
- `paper/_archive_v1/`: old prose (not built). `paper2/`: research notes, gap analysis, the
  reference-verification trail (`paper2/references.md`) and an older `context.md`.
- Artifact generators: `src/acde/analysis/paper_artifacts.py` (tables and macros; `true_minus()`
  typesets negative numbers with a real minus sign) and `paper_figures.py` (plots).

### Build
```bash
make paper-repro-quick
```
The PDF goes to `paper/build/main.pdf` and is built with **tectonic**. After every edit, check for
broken references:
```bash
pdftotext paper/build/main.pdf - | grep -c "??"
```
The result must be `0`. The PDF is currently 17 pages.

### Headline results (all live unless noted; source: generated macros)
| Item | Value |
|---|---|
| Runs | 560 = 240 live-agent (arm A) + 240 non-agent (arm B) + 80 mock (arm C) |
| Design | 4 fault scenarios (schema_drift, upstream_delay, resource_contention, ingress_burst) × 8 configs (baseline, rule_based, autoscale, monitor_only, recovery_only, optimization_only, schema_only, full) |
| full vs baseline MTTR | 378 s → 235 s (−38%, Cliff's δ −0.56, p_Holm<0.001) |
| full vs baseline cost | 158 → 69.8 units (−56%). **Mostly the assumed provisioning term** (120 vs 45). The metered term is confounded (see D-104s) |
| full manual interventions | 1 → 6 (**+500%**, a negative result) |
| rule_based / autoscale MTTR | 30.0 s (−92%) / 52.4 s (−86%). Both are **idealized**, with fixed modelled latencies of 30 s and 20 s (`experiments/baselines.py`) |
| full decision-correct rate | 0.42 live vs 1.00 mock |
| Mock vs live MTTR | 0.193 s vs 235 s, ratio R = 1219 |
| Mock cost anomaly | mock 833 vs live 69.8. Explained in D-104s: pool/worker state carries over between runs, and the cost windows are unequal |
| Adversarial corpus | 5547 cases; containment 3867/3867 (≥0.9990 Wilson); oracle agreement 5547/5547, after two contract-layer fixes |
| LLM usage | 703 real calls and 975,570 tokens across 240 live runs. Maximum per run: 16,042 tokens and 11 calls (cap: 150k tokens and 60 calls) |
| Live models | reasoning `nvidia/nemotron-3-ultra-550b-a55b`; monitoring `nvidia/nemotron-3-super-120b-a12b`; OpenAI-compatible endpoint, temperature 0 |
| Testbed | Apple M2, 8 cores, 8 GB, macOS 15.7.2; Docker 29.6.1; PG 16.6; Redpanda v24.2.18; Airflow 2.10.5; **OPA 0.68.0 (pinned; a newer OPA mis-evaluated float budgets)** |

### Editorial decisions the user made (respect these)
- Do **not** call the system "ACDE" in the paper prose. Do **not** frame the work as a "replication".
  Do **not** mention `.md` file names, `§`, or author names in citations ("Zhu et al."). Cite with
  `\cite` only.
- Citations print as separate `[2], [3]`, never as ranges `[2–4]`.
- Section titles are ALL CAPS. Subsection titles are Title Case.
- Format follows the user's IEEE TMI reference paper: lettered subsections, an introduction with no
  sub-headings, numbered contributions, abbreviated reference venues.
- Every equation (Eqs. 1–6), figure and table must be cited in the text where it is discussed.
- Avoid long parenthetical asides. Keep captions short (Figure 1 caption: "Seven-layer system
  architecture.").
- Abstract wording about the original study must stay cautious. The required sentence is: "The
  original study does not give enough implementation detail to pin down the exact model-in-the-loop
  evaluation condition." Never imply that the original used a mock.
- The user removed the appendix, the statements sections (data/code availability, contributions,
  COI, funding, ethics, AI disclosure), the running header and the affiliation placeholders. Venues
  usually require the statements and AI disclosure, so the user should be reminded before
  submission.
- Writing style: normal journal prose. The user rejected choppy over-split sentences. The user has
  been using the `human-writing` and `academic-humanizer` skills to lower AI-detector (Turnitin)
  scores. Detector scores are not a reliable target, and the user has been told so.
- Never change a number, citation key or label during rewrites. Diff the `\N` macros, `\cite` keys
  and `\label`s before and after each rewrite.

### Open items
- Author affiliations, ORCIDs, corresponding email and target venue are **unset**.
- Testbed facts are verified (D-104s).
- The cost metric is confounded (D-104s). A clean cost comparison needs a re-run after fixing `_reset_run` and the resource sampling.
- The MTTR equation is `t_r − t_d` (detection → resolution, like the base paper). Non-agent configurations detect at injection, which is disclosed as a threat.
- Conflict-of-interest and funding statements are still missing. The data/code availability statement and AI acknowledgment are in `sections/09_backmatter.tex`. The GitHub repo must be public before submission.
- The cross-model live sweep and the trust-core measurements (mode transitions, kill-switch latency)
  were **not run**. The paper reports them as implemented but not evaluated.

## 4. Repo conventions (from CLAUDE.md, enforced)

1. **Never commit or push unless the user asks.** When the user asks, end the commit message with a
   `Co-Authored-By:` line.
2. Every underspecified decision gets an entry in `DEVIATIONS.md` (latest: **D-104s**), giving the
   decision, the alternatives and the rationale. `CHANGELOG.md` has an `[Unreleased]` section.
3. Code changes are followed by `make lint && make test-unit`. Python 3.11, full type hints,
   pydantic v2, ruff (line length 100), mypy. Files stay at or under about 400 lines.
4. `MOCK_LLM=1` is the default, so tests make zero API calls. Determinism: seeds come from
   `sha256(config:scenario:replicate) % 2**32`, and temperature is 0.
5. Use `uv` for dependencies (`uv add`, never pip). `uv.lock` is committed.
6. Do not commit `cloudagent.zip` (a stray archive) or `graphify-out/` (generated output).

## 5. Setting up on a new laptop

```bash
git clone https://github.com/bodapatisaikrishna/agentic-cloud-pipeline-governance.git cloudagent
cd cloudagent
```
```bash
uv sync
```
```bash
cp .env.example .env
```
- Fill in `.env`. It is git-ignored and contains **no secrets in the repo**. You only need API keys
  for live runs: `LLM_PROVIDER`, `OAI_BASE_URL`, `OAI_API_KEY`, `OAI_MODEL_REASONING` and
  `OAI_MODEL_FAST` for the NVIDIA endpoint, or `ANTHROPIC_API_KEY` or `GEMINI_API_KEY`.
- To build the paper, install **tectonic** (`brew install tectonic`) and `poppler` (for
  `pdftotext`).
- To run the stack, install Docker Desktop, then run `make up`. The integration tests need it.
- Quick check: `make lint && make test-unit`, then `make paper-repro-quick`.

## 6. Key commands

| Area | Commands |
|---|---|
| Stack | `make up`, `make up-core`, `make down`, `make logs`, `make clean` |
| Quality | `make lint`, `make fmt`, `make test-unit`, `make test-integration`, `make opa-test` |
| Data plane | `make seed`, `make migrate`, `make stream`, `make telemetry` |
| Control loop | `make agents`, `make orchestrator`, `make soak` |
| Experiments | `make experiment-smoke`, `make experiment-quick`, `make experiment-paper` |
| Live campaign | `make campaign-pilot`, `make campaign`, `make campaign-status`, `make campaign-stop` |
| Paper | `make adversarial-corpus`, `make analyze`, `make report`, `make paper-repro-quick` |

## 7. Map of important files

- `src/acde/`: the package (contracts, llm, agents, policy, dataplane, telemetry, chaos, human,
  orchestrator, experiments, analysis, api).
- `src/acde/contracts/actions.py`: the `ProposedAction` contract. Scaling targets must be
  integers ≥ 1.
- `infra/opa/policies/`: the Rego policies and their tests. `infra/postgres/init/`: the DDL.
- `docs/`: `OPERATIONS`, `CONNECTING`, `POLICY_AUTHORING`, `SECURITY`, `PAPER_MAPPING`,
  `CAMPAIGN`, and the architecture diagrams (`system_architecture_7layer.*`).
- `README.md`: the phase table and the full documentation index. `REPORT.md`: which paper claims
  reproduce and which do not. `ARTIFACT.md`: the artifact and reproduction metadata.
- `results/`: git-ignored local run outputs. The canonical copy of the campaign data is in
  `paper/data/`.

## 8. What does NOT transfer automatically

- **Claude memory** (`~/.claude/projects/.../memory/`). The facts that mattered are folded into this
  file: the user prefers product/feature work over ops hardening, and the phase gates are strict.
- **Global skills and config**: `human-writing`, `academic-humanizer`, the
  `academic-research-skills` plugin and `graphify` must be installed again on the new account if
  you want them.
- **`.env` / API keys**: these must be re-entered by hand.
- **Uncommitted local files** (as of this writing): modified `docs/system_architecture_7layer.{pdf,png}`
  and `docs/system_architecture_paper.png`, plus the untracked `docs/system_architecture_paper.pdf`
  and `scripts/generate_visio_diagram.py`. Commit them first if they are needed.

## 9. Suggested first prompt on the new machine

> Read CONTEXT.md and CLAUDE.md, then run `make lint && make test-unit && make paper-repro-quick`
> and confirm the PDF has no `??`. Then continue the paper work.

## Cloud deployment (Azure, added 2026-10-17)

- **Live instance:** https://acde-edf7a2.southeastasia.cloudapp.azure.com (dashboard at `/ui`, API
  with header `x-api-key`). Resource group `rg-acde`, VM `acde-vm` (`Standard_B2pls_v2`, Arm64,
  southeastasia), shadow mode, mock LLM, `noop` connector. Billing: about $0.04/h while running.
- **Admin key** (never committed): `az vm run-command invoke -g rg-acde -n acde-vm --command-id
  RunShellScript --scripts 'grep ^API_KEYS= /opt/acde/.env.prod'`. SSH is open only to the IP used
  at deploy time; use `az vm run-command` instead.
- **Stop compute billing:** `az vm deallocate -g rg-acde -n acde-vm` (restart with `az vm start`).
  **Delete everything:** `az group delete -n rg-acde`.
- **Redeploy / update:** `az vm run-command invoke ... --scripts 'cd /opt/acde && git pull -q &&
  docker compose --env-file .env.prod --env-file .env -f deploy/docker-compose.prod.yml -f
  deploy/azure/docker-compose.azure.yml up -d --build'`.
- Azure for Students only allows southeastasia, uaenorth, malaysiawest, eastasia and austriaeast,
  and blocks the Intel B-series in southeastasia (hence Arm). Details: DEVIATIONS D-104t.
