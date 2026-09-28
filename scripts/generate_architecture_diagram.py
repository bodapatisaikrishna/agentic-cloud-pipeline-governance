#!/usr/bin/env python3
"""
Generate publication-quality, Microsoft Visio-style system architecture diagrams
for ACDE (Agentic Cloud Data Engineering) to include in IEEE Transactions papers.

Generates:
- docs/system_architecture.png (300 DPI high-resolution for papers/slides)
- docs/system_architecture.pdf (Vector PDF for LaTeX Overleaf submissions)
- docs/system_architecture.svg (Vector SVG natively editable in MS Visio & Illustrator)
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

def draw_visio_diagram(output_dir="docs"):
    os.makedirs(output_dir, exist_ok=True)
    
    # 18 x 24.5 inches at 300 DPI gives ultra-high resolution and perfect vertical proportion
    fig = plt.figure(figsize=(18, 24.5), dpi=300)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    # Overall Canvas Background (pure clean white)
    ax.add_patch(patches.Rectangle((0, 0), 100, 100, facecolor="#FFFFFF", edgecolor="none"))

    # Color Palette - Professional Enterprise / MS Visio Style
    PALETTE = {
        "title_bg": "#0F172A",
        "title_text": "#FFFFFF",
        "border_outer": "#CBD5E1",
        
        # Layer 7: Enterprise Governance
        "l7_bg": "#F8FAFC", "l7_border": "#64748B", "l7_badge": "#334155",
        "l7_box_bg": "#FFFFFF", "l7_box_border": "#94A3B8", "l7_header": "#1E293B",
        
        # Layer 6: Orchestration & Concurrency
        "l6_bg": "#FAF5FF", "l6_border": "#A855F7", "l6_badge": "#7E22CE",
        "l6_box_bg": "#FFFFFF", "l6_box_border": "#C084FC", "l6_header": "#581C87",
        
        # Layer 5: Execution & Graduated Autonomy
        "l5_bg": "#FFFBEB", "l5_border": "#F59E0B", "l5_badge": "#B45309",
        "l5_box_bg": "#FFFFFF", "l5_box_border": "#FCD34D", "l5_header": "#78350F",
        
        # Layer 4: Declarative Policy Gate (OPA)
        "l4_bg": "#FEF2F2", "l4_border": "#EF4444", "l4_badge": "#B91C1C",
        "l4_box_bg": "#FFFFFF", "l4_box_border": "#FCA5A5", "l4_header": "#7F1D1D",
        
        # Layer 3: Bounded Multi-Agent Tier
        "l3_bg": "#F0FDF4", "l3_border": "#10B981", "l3_badge": "#047857",
        "l3_box_bg": "#FFFFFF", "l3_box_border": "#6EE7B7", "l3_header": "#064E3B",
        
        # Layer 2: Telemetry & Cost Engine
        "l2_bg": "#F0F9FF", "l2_border": "#0EA5E9", "l2_badge": "#0284C7",
        "l2_box_bg": "#FFFFFF", "l2_box_border": "#7DD3FC", "l2_header": "#0C4A6E",
        
        # Layer 1: Data Plane & Connectors
        "l1_bg": "#EEF2FF", "l1_border": "#6366F1", "l1_badge": "#4338CA",
        "l1_box_bg": "#FFFFFF", "l1_box_border": "#A5B4FC", "l1_header": "#312E81",
        
        # Arrows & Flows
        "telemetry_flow": "#0284C7",
        "proposal_flow": "#059669",
        "decision_flow": "#DC2626",
        "exec_flow": "#D97706",
        "human_flow": "#9333EA",
    }

    # Helper: Shadow + Box (Visio card style)
    def draw_card(x, y, w, h, bg, border, title, items, corner=0.7):
        # Drop shadow
        shadow = FancyBboxPatch((x + 0.22, y - 0.22), w, h,
                                boxstyle=f"round,pad=0,rounding_size={corner}",
                                facecolor="#E2E8F0", edgecolor="none", alpha=0.55, zorder=2)
        ax.add_patch(shadow)
        
        # Main box
        box = FancyBboxPatch((x, y), w, h,
                             boxstyle=f"round,pad=0,rounding_size={corner}",
                             facecolor=bg, edgecolor=border, linewidth=1.3, zorder=3)
        ax.add_patch(box)
        
        # Header bar
        header_h = 1.45
        header = FancyBboxPatch((x, y + h - header_h), w, header_h,
                                boxstyle=f"round,pad=0,rounding_size={corner}",
                                facecolor=border, edgecolor="none", zorder=4)
        ax.add_patch(header)
        ax.add_patch(patches.Rectangle((x, y + h - header_h), w, 0.4, facecolor=border, edgecolor="none", zorder=4))
        
        # Header text
        ax.text(x + w/2, y + h - header_h/2, title,
                ha="center", va="center", color="#FFFFFF", fontsize=9.8, fontweight="bold",
                fontfamily="sans-serif", zorder=5)
        
        # Content items
        curr_y = y + h - header_h - 0.65
        line_spacing = (h - header_h - 1.1) / max(len(items), 1)
        line_spacing = min(line_spacing, 0.75)
        for line in items:
            is_bold = line.startswith("•") or line.startswith("[")
            weight = "bold" if is_bold else "normal"
            fsize = 8.2 if is_bold else 7.8
            color = "#1E293B" if is_bold else "#475569"
            ax.text(x + 0.55, curr_y, line, ha="left", va="center",
                    color=color, fontsize=fsize, fontweight=weight, fontfamily="sans-serif", zorder=5)
            curr_y -= line_spacing

    # Helper: Layer Container Box
    def draw_layer_container(y, h, name, subtitle, colors):
        x = 5
        w = 90
        # Background container
        container = FancyBboxPatch((x, y), w, h,
                                   boxstyle="round,pad=0,rounding_size=1.1",
                                   facecolor=colors["bg"], edgecolor=colors["border"],
                                   linewidth=1.6, zorder=1)
        ax.add_patch(container)
        
        # Top-left badge / tab
        tab_w = 34
        tab_h = 1.85
        tab = FancyBboxPatch((x + 1.2, y + h - tab_h + 0.15), tab_w, tab_h,
                             boxstyle="round,pad=0,rounding_size=0.5",
                             facecolor=colors["badge"], edgecolor="none", zorder=2)
        ax.add_patch(tab)
        ax.text(x + 2.0, y + h - tab_h/2 + 0.15, name.upper(),
                ha="left", va="center", color="#FFFFFF", fontsize=9.0, fontweight="bold",
                fontfamily="sans-serif", zorder=3)
        
        # Subtitle on right
        ax.text(x + tab_w + 2.8, y + h - tab_h/2 + 0.15, subtitle,
                ha="left", va="center", color=colors["header"], fontsize=8.5, fontstyle="italic",
                fontfamily="sans-serif", zorder=3)

    # --------------------------------------------------------------------------
    # 0. TOP TITLE BANNER
    # --------------------------------------------------------------------------
    title_box = FancyBboxPatch((5, 95.0), 90, 4.0, boxstyle="round,pad=0,rounding_size=0.8",
                               facecolor=PALETTE["title_bg"], edgecolor="none", zorder=2)
    ax.add_patch(title_box)
    ax.text(50, 97.4, "ACDE: Autonomous Cloud Data Engineering Control Plane Architecture",
            ha="center", va="center", color="#FFFFFF", fontsize=14.5, fontweight="bold", fontfamily="sans-serif", zorder=3)
    ax.text(50, 95.8, "Seven-Layer Policy-Bounded Supervisory Architecture for Resilient Heterogeneous Cloud Data Pipelines",
            ha="center", va="center", color="#94A3B8", fontsize=9.2, fontfamily="sans-serif", zorder=3)

    # --------------------------------------------------------------------------
    # LAYER 7: ENTERPRISE GOVERNANCE & MULTI-TENANCY PLANE
    # --------------------------------------------------------------------------
    l7_y, l7_h = 84.5, 9.2
    draw_layer_container(l7_y, l7_h, "Layer 7: Enterprise Governance & Multi-Tenancy",
                         "FastAPI Operator API · Multi-Actor RBAC · Tenant Registry · Streaming Keyset Audit",
                         {"bg": PALETTE["l7_bg"], "border": PALETTE["l7_border"],
                          "badge": PALETTE["l7_badge"], "header": PALETTE["l7_header"]})

    draw_card(7.2, l7_y + 0.65, 19.5, 6.7, PALETTE["l7_box_bg"], PALETTE["l7_border"],
              "Operator REST API", [
                  "• acde.server.app",
                  "- Constant-time token verification",
                  "  via compare_digest (anti-timing)",
                  "- Pre-auth IP rate limiter",
                  "- Swagger & ReDoc authenticated",
                  "- Shallow /health + full /health/ready"
              ])

    draw_card(28.7, l7_y + 0.65, 19.5, 6.7, PALETTE["l7_box_bg"], PALETTE["l7_border"],
              "RBAC & Multi-Tenancy", [
                  "• acde.tenancy",
                  "- Hierarchical 3-tier RBAC:",
                  "  viewer < approver < admin",
                  "- Scoped tenant_id & environment",
                  "- Registry: control.tenants",
                  "- Suspension halts tenant in-flight"
              ])

    draw_card(50.2, l7_y + 0.65, 19.5, 6.7, PALETTE["l7_box_bg"], PALETTE["l7_border"],
              "Compliance & Audit Export", [
                  "• acde.ops.compliance",
                  "- Streaming CSV export via cursor",
                  "  (ts, action_id) in O(1) memory",
                  "- SOC-2 / ISO compliance evidence",
                  "- Policy verdict distribution",
                  "- MTTR & availability tracking"
              ])

    draw_card(71.7, l7_y + 0.65, 20.8, 6.7, PALETTE["l7_box_bg"], PALETTE["l7_border"],
              "Decision Quality Scoring", [
                  "• acde.ops.decision_quality",
                  "- Empirical decision_correct rate",
                  "- Resolving action evaluation vs",
                  "  known fault type ground truth",
                  "- Live operational scoring",
                  "- Multi-model cross comparison"
              ])

    # --------------------------------------------------------------------------
    # LAYER 6: ORCHESTRATION, CONCURRENCY & CONTROL LOOP
    # --------------------------------------------------------------------------
    l6_y, l6_h = 72.5, 10.5
    draw_layer_container(l6_y, l6_h, "Layer 6: Orchestration, Concurrency & Distributed Control",
                         "Async Scheduler · 2-Tier Bidding Conflict Arbitration · PG Advisory Locks · Durable Kill Switch",
                         {"bg": PALETTE["l6_bg"], "border": PALETTE["l6_border"],
                          "badge": PALETTE["l6_badge"], "header": PALETTE["l6_header"]})

    draw_card(7.2, l6_y + 0.65, 26.5, 7.8, PALETTE["l6_box_bg"], PALETTE["l6_border"],
              "ControlLoop Scheduler", [
                  "• acde.orchestrator.loop.ControlLoop",
                  "- Continuous non-blocking async schedule loop",
                  "- Periodic monitoring tick (every MONITORING_INTERVAL_S)",
                  "- Reactive agents execute conditionally on open faults",
                  "- Durable heartbeat in control.desired_state",
                  "- Pure Postgres state: kill/restart resumes cleanly"
              ])

    draw_card(35.5, l6_y + 0.65, 27.5, 7.8, PALETTE["l6_box_bg"], PALETTE["l6_border"],
              "2-Tier Conflict Arbitration", [
                  "• loop._resolve_conflicts & locks.py",
                  "- Tier 1 (Within-tick multi-agent bidding):",
                  "  Priority: Recovery(3) > Schema(2) > Optimization(1)",
                  "  Tie-broken by ProposedAction.confidence",
                  "- Tier 2 (Cross-process distributed locks):",
                  "  pg_try_advisory_lock(hash(target))",
                  "  Zero lock leakage on worker crash"
              ])

    draw_card(64.8, l6_y + 0.65, 27.7, 7.8, PALETTE["l6_box_bg"], PALETTE["l6_border"],
              "Durable Runtime Safety Controls", [
                  "• acde.orchestrator.control",
                  "- Durable Kill Switch (acde.paused in Postgres)",
                  "  Takes effect across all workers in <= 1 tick",
                  "- Hourly Blast-Radius Rate Limiter:",
                  "  Max executions / target / hour",
                  "- Liveness age evaluation (heartbeat_age_s)",
                  "- Diagnostic probes via acde loop-health"
              ])

    # --------------------------------------------------------------------------
    # LAYER 5: EXECUTION & GRADUATED AUTONOMY ENGINE
    # --------------------------------------------------------------------------
    l5_y, l5_h = 60.5, 10.5
    draw_layer_container(l5_y, l5_h, "Layer 5: Safe Execution & Graduated Autonomy Engine",
                         "Write-Ahead Audit Trail · Tri-Mode Autonomy Ladder · Target Invariant Guard · Bounded Retries",
                         {"bg": PALETTE["l5_bg"], "border": PALETTE["l5_border"],
                          "badge": PALETTE["l5_badge"], "header": PALETTE["l5_header"]})

    draw_card(7.2, l5_y + 0.65, 26.5, 7.8, PALETTE["l5_box_bg"], PALETTE["l5_border"],
              "Write-Ahead Audit Logging", [
                  "• acde.agents.base.BaseAgent.act",
                  "- Write-Ahead Pattern: Row committed to DB",
                  "  with status='executing' BEFORE side-effects",
                  "- Guarantees zero unaudited phantom actions",
                  "- Crashes/OOMs leave clear 'executing' audit",
                  "- Updates to executed/failed/denied on finish",
                  "- Full token counts & model telemetry logged"
              ])

    draw_card(35.5, l5_y + 0.65, 27.5, 7.8, PALETTE["l5_box_bg"], PALETTE["l5_border"],
              "Tri-Mode Graduated Autonomy", [
                  "• acde.policy.executor.execute",
                  "- Shadow Mode: Simulates action, emits",
                  "  shadow_proposal webhook, zero pipeline mutation",
                  "- Approval Mode: Queues in action_approvals;",
                  "  operator approves via CLI/UI -> apply_action",
                  "- Autonomous Mode: Executes directly via connector",
                  "- High-blast actions forced to Approval mode"
              ])

    draw_card(64.8, l5_y + 0.65, 27.7, 7.8, PALETTE["l5_box_bg"], PALETTE["l5_border"],
              "Target Guard & Bounded Retries", [
                  "• acde.policy.executor.apply_action",
                  "- Target Invariant Sanitizer: Rejects proposals",
                  "  where target == experiment_run (LLM hallucination)",
                  "- Bounded Retries: Exponential backoff on",
                  "  Airflow REST (attempts=3, backoff=0.5s)",
                  "- Degrades to manual_interventions ticket",
                  "  upon exhaustion; engine never crashes"
              ])

    # --------------------------------------------------------------------------
    # LAYER 4: DECLARATIVE POLICY GATE & CONTAINMENT PLANE (OPA)
    # --------------------------------------------------------------------------
    l4_y, l4_h = 48.5, 10.5
    draw_layer_container(l4_y, l4_h, "Layer 4: Declarative Policy Gate & Containment Boundary (OPA)",
                         "Open Policy Agent (OPA 0.68) · Formal Invariants · Fail-Safe Escalation · 100% Empirical Containment",
                         {"bg": PALETTE["l4_bg"], "border": PALETTE["l4_border"],
                          "badge": PALETTE["l4_badge"], "header": PALETTE["l4_header"]})

    draw_card(7.2, l4_y + 0.65, 19.5, 7.8, PALETTE["l4_box_bg"], PALETTE["l4_border"],
              "Rate-Limit Runaway Guard", [
                  "• rate_limit.rego",
                  "- Hard safety invariant:",
                  "  Actions last 10m < 5",
                  "- First check for all agents",
                  "- Prevents runaway LLM loops",
                  "- Denies and halts execution",
                  "- policy_id: 'rate_limit'"
              ])

    draw_card(28.7, l4_y + 0.65, 19.5, 7.8, PALETTE["l4_box_bg"], PALETTE["l4_border"],
              "Marginal Cost Budget Gate", [
                  "• cost_budget.rego",
                  "- Projected marginal cost:",
                  "  ΔC = ΔW × window_s × r_comp",
                  "- Scale-downs (ΔC <= 0): Auto-allow",
                  "- Scale-ups: ΔC <= Budget_remaining",
                  "- Denies over-budget scale-ups",
                  "- policy_id: 'cost_budget'"
              ])

    draw_card(50.2, l4_y + 0.65, 19.5, 7.8, PALETTE["l4_box_bg"], PALETTE["l4_border"],
              "Rollback & Schema Safety", [
                  "• recovery.rego & schema.rego",
                  "- Rollback Invariant: Verify prior",
                  "  version exists (v_prior < v_active)",
                  "- Deny rollback without prior version",
                  "- Schema Invariant: Compatible drift",
                  "  allowed only if backward-compat",
                  "- Breaking drift -> Quarantine/Block"
              ])

    draw_card(71.7, l4_y + 0.65, 20.8, 7.8, PALETTE["l4_box_bg"], PALETTE["l4_border"],
              "Fail-Safe Escalation Default", [
                  "• acde.policy.gate (D-023)",
                  "- Network partition or crash handling",
                  "- If OPA unreachable / 5xx / timeout:",
                  "  Gate FAILS SAFE: allowed=False,",
                  "  escalate=True, policy_id='gate_failsafe'",
                  "- Never permits un-evaluated actions",
                  "- Measured containment rate: 1.0"
              ])

    # --------------------------------------------------------------------------
    # LAYER 3: BOUNDED MULTI-AGENT SUPERVISORY TIER
    # --------------------------------------------------------------------------
    l3_y, l3_h = 34.0, 13.0
    draw_layer_container(l3_y, l3_h, "Layer 3: Bounded Multi-Agent Supervisory Tier",
                         "Specialized Closed-Vocabulary Agents · Dual-Tier LLM Gateway · Bayesian Adaptation · Pydantic Contracts",
                         {"bg": PALETTE["l3_bg"], "border": PALETTE["l3_border"],
                          "badge": PALETTE["l3_badge"], "header": PALETTE["l3_header"]})

    # Sub-bar inside Layer 3: Placed nicely below the tab with full breathing room
    sub3_box = FancyBboxPatch((7.2, l3_y + 8.9), 85.3, 1.7, boxstyle="round,pad=0,rounding_size=0.4",
                              facecolor="#DCFCE7", edgecolor="#10B981", linewidth=1.1, zorder=2)
    ax.add_patch(sub3_box)
    ax.text(8.2, l3_y + 9.75, "COGNITIVE INFRASTRUCTURE:",
            ha="left", va="center", color="#065F46", fontsize=8.5, fontweight="bold", fontfamily="sans-serif", zorder=3)
    ax.text(26.5, l3_y + 9.75, "Dual-Tier Model Routing (Fast vs Reasoning)  |  Temp=0  |  Budget Caps (60 calls, 150k tokens)  |  Canonical JSON State Hashing",
            ha="left", va="center", color="#1E293B", fontsize=8.0, fontfamily="sans-serif", zorder=3)

    draw_card(7.2, l3_y + 0.65, 19.5, 7.8, PALETTE["l3_box_bg"], PALETTE["l3_border"],
              "Monitoring Agent", [
                  "• Fast-Tier (Haiku/Flash)",
                  "- Cheap z-score pre-filter",
                  "- Task failure & retry detection",
                  "- Freshness SLA breach check",
                  "- CPU threshold monitoring",
                  "- Emits: raise_anomaly, escalate",
                  "- Stamps failure_events.detected_ts",
                  "- Fixes MTTR origin point"
              ])

    draw_card(28.7, l3_y + 0.65, 19.5, 7.8, PALETTE["l3_box_bg"], PALETTE["l3_border"],
              "Optimization Agent", [
                  "• Reasoning-Tier (Sonnet/Pro)",
                  "- Analyzes contention & bursts",
                  "- Proposes dynamic scaling:",
                  "  scale_workers (streaming 1..8)",
                  "  adjust_pool_slots (Airflow)",
                  "  reprioritize_pipeline",
                  "- Only positive integers allowed",
                  "- Stamps resolved_ts on success"
              ])

    draw_card(50.2, l3_y + 0.65, 19.5, 7.8, PALETTE["l3_box_bg"], PALETTE["l3_border"],
              "Schema Agent", [
                  "• Reasoning-Tier (Sonnet/Pro)",
                  "- Detects schema drift & evolution",
                  "- Proposes safe mitigations:",
                  "  allow_compatible (backward)",
                  "  apply_mapping (renames)",
                  "  quarantine_partition (sink)",
                  "  block_ingestion (corrupt)",
                  "- Stamps resolved_ts on success"
              ])

    draw_card(71.7, l3_y + 0.65, 20.8, 7.8, PALETTE["l3_box_bg"], PALETTE["l3_border"],
              "Recovery Agent", [
                  "• Reasoning-Tier (Sonnet/Pro)",
                  "- Remediates failed DAGs/tasks",
                  "- Proposes surgical actions:",
                  "  retry_with_backoff (transient)",
                  "  replay (dag runs)",
                  "  rollback (pointer flip)",
                  "  partial_recompute (tasks)",
                  "  escalate_to_human",
                  "- Stamps resolved_ts (MTTR end)"
              ])

    # --------------------------------------------------------------------------
    # LAYER 2: TELEMETRY & OBSERVABILITY ENGINE
    # --------------------------------------------------------------------------
    l2_y, l2_h = 20.5, 10.5
    draw_layer_container(l2_y, l2_h, "Layer 2: Telemetry & Observability Subsystem",
                         "Continuous Collector · Exact Freshness Formulations · Disclosed Normalized Hybrid Cost Ledger",
                         {"bg": PALETTE["l2_bg"], "border": PALETTE["l2_border"],
                          "badge": PALETTE["l2_badge"], "header": PALETTE["l2_header"]})

    draw_card(7.2, l2_y + 0.65, 26.5, 7.8, PALETTE["l2_box_bg"], PALETTE["l2_border"],
              "Telemetry Collector Engine", [
                  "• acde.telemetry.collector",
                  "- Airflow REST poller -> telemetry.task_runs",
                  "  Idempotent upsert via unique task_runs_uident",
                  "- Resource usage probe (CPU %, Mem MB, Workers)",
                  "- Pipeline metrics & error trace harvest",
                  "- failure_events lifecycle tracking (inject/detect/resolve)"
              ])

    draw_card(35.5, l2_y + 0.65, 27.5, 7.8, PALETTE["l2_box_bg"], PALETTE["l2_border"],
              "Data Freshness Evaluator", [
                  "• acde.telemetry.freshness",
                  "- Streaming Freshness (exact, SLA-relevant):",
                  "  Δt_fresh = t_materialized - t_event <= 60s SLA",
                  "- Batch Freshness (staleness):",
                  "  Δt_stale = t_now - t_created",
                  "- Real-time violation anomaly triggers"
              ])

    draw_card(64.8, l2_y + 0.65, 27.7, 7.8, PALETTE["l2_box_bg"], PALETTE["l2_border"],
              "Disclosed Normalized Cost Model", [
                  "• acde.telemetry.cost (Cost Model v2)",
                  "- Cost = Compute + Storage + Provisioning Penalty",
                  "  Compute: ∫ W(t) dt × $0.05 / worker-second",
                  "  Storage: Warehouse size × $0.01 / GB-hour",
                  "  Provisioning: Credits dynamic right-sizing over static",
                  "- Disclosed & verified against hand fixtures"
              ])

    # --------------------------------------------------------------------------
    # LAYER 1: DATA PLANE & CONNECTOR BOUNDARY
    # --------------------------------------------------------------------------
    l1_y, l1_h = 6.8, 11.8
    draw_layer_container(l1_y, l1_h, "Layer 1: Pipeline Data Plane & Orchestrator Connector Boundary",
                         "Orchestrator Connector Protocol · Batch DAGs · Distributed Streaming · Transactional Versioned Partitions",
                         {"bg": PALETTE["l1_bg"], "border": PALETTE["l1_border"],
                          "badge": PALETTE["l1_badge"], "header": PALETTE["l1_header"]})

    draw_card(7.2, l1_y + 0.65, 20.0, 8.8, PALETTE["l1_box_bg"], PALETTE["l1_border"],
              "Orchestrator Connectors", [
                  "• acde.connectors.base.Connector",
                  "- Abstract interface isolating engine:",
                  "  probe(), get_task_runs(), trigger(),",
                  "  clear_tasks(), set_pool_slots()",
                  "- AirflowConnector (least-privilege REST)",
                  "- PrefectConnector & NoopConnector",
                  "- is_production safety flag"
              ])

    draw_card(29.0, l1_y + 0.65, 20.0, 8.8, PALETTE["l1_box_bg"], PALETTE["l1_border"],
              "Batch Pipeline (Airflow)", [
                  "• Apache Airflow 2.10",
                  "- tpcds_ingest DAG (TPC-DS benchmarks)",
                  "- Tasks: validate -> transform -> materialize",
                  "- Airflow execution pools & slots",
                  "- Task failure capture & replay",
                  "- Upstream delay & skew recovery"
              ])

    draw_card(50.8, l1_y + 0.65, 20.0, 8.8, PALETTE["l1_box_bg"], PALETTE["l1_border"],
              "Streaming Ingestion", [
                  "• Redpanda / Apache Kafka",
                  "- Bursty streaming events ingestion",
                  "- Tumbling 60s aggregation windows",
                  "- Async worker pool sized live via",
                  "  control.desired_state['streaming.workers']",
                  "- warehouse.stream_aggregates"
              ])

    draw_card(72.6, l1_y + 0.65, 19.9, 8.8, PALETTE["l1_box_bg"], PALETTE["l1_border"],
              "Transactional Partitions", [
                  "• warehouse.partition_versions",
                  "- Physical immutable tables:",
                  "  {dataset}__{key}__v{version}",
                  "- pg_advisory_xact_lock concurrency",
                  "- Zero-copy Rollback: O(1) pointer flip",
                  "- warehouse.quarantine_events sink"
              ])

    # --------------------------------------------------------------------------
    # CONNECTING FLOW ARROWS
    # --------------------------------------------------------------------------
    def draw_flow_arrow(x, y_start, y_end, color, label=""):
        arrow = FancyArrowPatch((x, y_start), (x, y_end),
                                arrowstyle="-|>,head_length=5,head_width=3",
                                connectionstyle="arc3,rad=0",
                                color=color, linewidth=2.2, zorder=6)
        ax.add_patch(arrow)
        if label:
            ax.text(x + 0.8, (y_start + y_end)/2, label,
                    ha="left", va="center", color=color, fontsize=7.2, fontweight="bold",
                    fontfamily="sans-serif", zorder=7,
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="#FFFFFF", edgecolor=color, linewidth=0.8, alpha=0.92))

    # Upward Telemetry Flows
    draw_flow_arrow(18.0, l1_y + l1_h, l2_y, PALETTE["telemetry_flow"], "Raw Task & Metric Stream")
    draw_flow_arrow(22.0, l2_y + l2_h, l3_y, PALETTE["telemetry_flow"], "TelemetrySnapshot (S_t)")
    
    # Reasoning & Proposal Flow
    draw_flow_arrow(38.0, l3_y + l3_h, l4_y, PALETTE["proposal_flow"], "ProposedAction (a)")
    
    # Policy Decision Flow
    draw_flow_arrow(50.0, l4_y + l4_h, l5_y, PALETTE["decision_flow"], "PolicyDecision (d)")
    
    # Arbitrated Loop Flow
    draw_flow_arrow(64.0, l5_y + l5_h, l6_y, PALETTE["exec_flow"], "Arbitrated Action Dispatch")
    draw_flow_arrow(64.0, l6_y, l5_y + l5_h, PALETTE["exec_flow"])
    
    # Governance & Multi-Tenant Control Flow
    draw_flow_arrow(78.0, l6_y + l6_h, l7_y, "#334155", "Governance & Audit Stream")
    draw_flow_arrow(78.0, l7_y, l6_y + l6_h, "#334155")

    # Side-channel: Controlled execution side-effect back to Data Plane (Left side)
    side_path = patches.Path(
        [(7.2, l5_y + 3.5), (2.8, l5_y + 3.5), (2.8, l1_y + 5.5), (7.2, l1_y + 5.5)],
        [patches.Path.MOVETO, patches.Path.LINETO, patches.Path.LINETO, patches.Path.LINETO]
    )
    side_patch = patches.PathPatch(side_path, facecolor="none", edgecolor=PALETTE["exec_flow"],
                                   linewidth=2.0, linestyle="--", zorder=5)
    ax.add_patch(side_patch)
    side_arrow = FancyArrowPatch((3.8, l1_y + 5.5), (7.2, l1_y + 5.5),
                                 arrowstyle="-|>,head_length=5,head_width=3",
                                 color=PALETTE["exec_flow"], linewidth=2.0, zorder=6)
    ax.add_patch(side_arrow)
    ax.text(3.0, (l5_y + l1_y)/2 + 4.5, "GATED EXECUTION SIDE-EFFECTS\n(Shadow / Approval / Autonomous)",
            ha="center", va="center", color=PALETTE["exec_flow"], fontsize=7.2, fontweight="bold",
            fontfamily="sans-serif", rotation=90, zorder=6,
            bbox=dict(boxstyle="round,pad=0.25", facecolor="#FFFBEB", edgecolor=PALETTE["exec_flow"], linewidth=0.8))

    # Side-channel: Human Escalation & Approval Loop (Right side)
    esc_path = patches.Path(
        [(92.8, l5_y + 3.5), (97.2, l5_y + 3.5), (97.2, l7_y + 4.5), (92.8, l7_y + 4.5)],
        [patches.Path.MOVETO, patches.Path.LINETO, patches.Path.LINETO, patches.Path.LINETO]
    )
    esc_patch = patches.PathPatch(esc_path, facecolor="none", edgecolor=PALETTE["human_flow"],
                                  linewidth=2.0, linestyle=":", zorder=5)
    ax.add_patch(esc_patch)
    esc_arrow = FancyArrowPatch((95.8, l7_y + 4.5), (92.8, l7_y + 4.5),
                                arrowstyle="-|>,head_length=5,head_width=3",
                                color=PALETTE["human_flow"], linewidth=2.0, zorder=6)
    ax.add_patch(esc_arrow)
    ax.text(97.0, (l5_y + l7_y)/2 + 4.0, "HUMAN-IN-THE-LOOP INTERVENTIONS\n(Approvals Queue & Escalation Tickets)",
            ha="center", va="center", color=PALETTE["human_flow"], fontsize=7.2, fontweight="bold",
            fontfamily="sans-serif", rotation=270, zorder=6,
            bbox=dict(boxstyle="round,pad=0.25", facecolor="#FAF5FF", edgecolor=PALETTE["human_flow"], linewidth=0.8))

    # --------------------------------------------------------------------------
    # BOTTOM LEGEND & METADATA BAR
    # --------------------------------------------------------------------------
    legend_box = FancyBboxPatch((5, 1.0), 90, 4.2, boxstyle="round,pad=0,rounding_size=0.6",
                                facecolor="#F8FAFC", edgecolor="#CBD5E1", linewidth=1.2, zorder=2)
    ax.add_patch(legend_box)
    
    ax.text(7.0, 3.2, "FLOW LEGEND:", ha="left", va="center",
            color="#0F172A", fontsize=8.8, fontweight="bold", fontfamily="sans-serif", zorder=3)
    
    # Legend Item 1: Telemetry Flow
    ax.plot([17.0, 20.5], [3.2, 3.2], color=PALETTE["telemetry_flow"], linewidth=2.5, zorder=3)
    ax.text(21.2, 3.2, "Telemetry & Metric Stream", ha="left", va="center", color="#334155", fontsize=7.8, fontfamily="sans-serif", zorder=3)

    # Legend Item 2: Proposal Flow
    ax.plot([36.0, 39.5], [3.2, 3.2], color=PALETTE["proposal_flow"], linewidth=2.5, zorder=3)
    ax.text(40.2, 3.2, "Action Proposal (ProposedAction)", ha="left", va="center", color="#334155", fontsize=7.8, fontfamily="sans-serif", zorder=3)

    # Legend Item 3: Decision Flow
    ax.plot([58.0, 61.5], [3.2, 3.2], color=PALETTE["decision_flow"], linewidth=2.5, zorder=3)
    ax.text(62.2, 3.2, "Policy Verdict (PolicyDecision)", ha="left", va="center", color="#334155", fontsize=7.8, fontfamily="sans-serif", zorder=3)

    # Legend Item 4: Execution Flow
    ax.plot([78.0, 81.5], [3.2, 3.2], color=PALETTE["exec_flow"], linewidth=2.5, linestyle="--", zorder=3)
    ax.text(82.2, 3.2, "Controlled Side-Effect Flow", ha="left", va="center", color="#334155", fontsize=7.8, fontfamily="sans-serif", zorder=3)

    # Footnote / Publication Metadata
    ax.text(50, 1.8, "Figure: Formal Architectural Topology of the ACDE Autonomous Pipeline Governance Platform for IEEE Transactions.",
            ha="center", va="center", color="#64748B", fontsize=7.5, fontstyle="italic", fontfamily="sans-serif", zorder=3)

    # --------------------------------------------------------------------------
    # SAVE IN MULTIPLE FORMATS
    # --------------------------------------------------------------------------
    png_path = os.path.join(output_dir, "system_architecture.png")
    pdf_path = os.path.join(output_dir, "system_architecture.pdf")
    svg_path = os.path.join(output_dir, "system_architecture.svg")
    
    print(f"Saving updated Visio-style diagram to:")
    print(f"  -> PNG: {png_path} (300 DPI)")
    plt.savefig(png_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none", bbox_inches="tight")
    
    print(f"  -> PDF: {pdf_path} (Vector)")
    plt.savefig(pdf_path, format="pdf", facecolor=fig.get_facecolor(), edgecolor="none", bbox_inches="tight")
    
    print(f"  -> SVG: {svg_path} (Vector / Visio-compatible)")
    plt.savefig(svg_path, format="svg", facecolor=fig.get_facecolor(), edgecolor="none", bbox_inches="tight")
    
    plt.close(fig)
    print("Done! Perfectly aligned Visio-style architecture diagrams generated.")

if __name__ == "__main__":
    draw_visio_diagram()
