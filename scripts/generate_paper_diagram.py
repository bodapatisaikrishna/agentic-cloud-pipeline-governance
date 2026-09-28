#!/usr/bin/env python3
"""
Generate a sleek, compact, publication-ready System Architecture diagram
specifically dimensioned and formatted for IEEE journal papers.

Design principles:
1. Compact 16:8.2 widescreen ratio that spans two columns in IEEEtran
   (\\begin{figure*} ... \\end{figure*}) taking only ~3.2 inches of page height.
2. Large, highly legible typography designed to remain razor-sharp when scaled down.
3. Balanced vertical rhythm with zero wasted whitespace inside component cards.
4. Saves directly to docs/system_architecture_paper.png (300 DPI).
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

def draw_paper_diagram(output_path="docs/system_architecture_paper.png"):
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # 16 x 8.4 inches at 300 DPI (4800 x 2520 px) - compact, publication-perfect ratio
    fig = plt.figure(figsize=(16, 8.4), dpi=300)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    # Clean white background
    ax.add_patch(patches.Rectangle((0, 0), 100, 100, facecolor="#FFFFFF", edgecolor="none"))

    # Color Palette - Professional IEEE Publication Palette
    C = {
        "title_bg": "#0F172A",
        "t4_bg": "#F8FAFC", "t4_border": "#475569", "t4_badge": "#334155",
        "t3_bg": "#FEF2F2", "t3_border": "#DC2626", "t3_badge": "#991B1B",
        "t2_bg": "#F0FDF4", "t2_border": "#059669", "t2_badge": "#065F46",
        "t1_bg": "#EFF6FF", "t1_border": "#2563EB", "t1_badge": "#1E40AF",
        "flow_tel": "#0284C7",
        "flow_prop": "#059669",
        "flow_dec": "#DC2626",
        "flow_exec": "#D97706",
        "flow_human": "#7C3AED",
    }

    # Helper: Card with header band
    def draw_card(x, y, w, h, border, title, bullets):
        # Soft shadow
        shadow = FancyBboxPatch((x + 0.18, y - 0.18), w, h,
                                boxstyle="round,pad=0,rounding_size=0.5",
                                facecolor="#E2E8F0", edgecolor="none", alpha=0.5, zorder=2)
        ax.add_patch(shadow)

        # Card body
        card = FancyBboxPatch((x, y), w, h,
                              boxstyle="round,pad=0,rounding_size=0.5",
                              facecolor="#FFFFFF", edgecolor=border, linewidth=1.3, zorder=3)
        ax.add_patch(card)

        # Card header bar
        header_h = 2.4
        header = FancyBboxPatch((x, y + h - header_h), w, header_h,
                                boxstyle="round,pad=0,rounding_size=0.5",
                                facecolor=border, edgecolor="none", zorder=4)
        ax.add_patch(header)
        ax.add_patch(patches.Rectangle((x, y + h - header_h), w, 0.5, facecolor=border, edgecolor="none", zorder=4))

        # Title text
        ax.text(x + w/2, y + h - header_h/2, title,
                ha="center", va="center", color="#FFFFFF", fontsize=10.2, fontweight="bold",
                fontfamily="sans-serif", zorder=5)

        # Content bullets (distributed evenly)
        usable_h = h - header_h - 1.2
        n_lines = len(bullets)
        spacing = usable_h / max(n_lines - 1, 1) if n_lines > 1 else 0
        spacing = min(spacing, 1.4)
        curr_y = y + h - header_h - 1.1

        for b in bullets:
            is_bold = b.startswith("•") or b.startswith("[") or b.endswith(":")
            weight = "bold" if is_bold else "normal"
            fsize = 8.6 if is_bold else 8.2
            color = "#0F172A" if is_bold else "#334155"
            ax.text(x + 0.65, curr_y, b, ha="left", va="center",
                    color=color, fontsize=fsize, fontweight=weight, fontfamily="sans-serif", zorder=5)
            curr_y -= spacing

    # Helper: Tier Container
    def draw_tier(y, h, name, subtitle, colors):
        x, w = 5, 90
        container = FancyBboxPatch((x, y), w, h,
                                   boxstyle="round,pad=0,rounding_size=0.8",
                                   facecolor=colors["bg"], edgecolor=colors["border"],
                                   linewidth=1.4, zorder=1)
        ax.add_patch(container)

        # Tier Tab Badge
        tab_w = 32
        tab_h = 2.4
        tab = FancyBboxPatch((x + 1.2, y + h - tab_h + 0.2), tab_w, tab_h,
                             boxstyle="round,pad=0,rounding_size=0.4",
                             facecolor=colors["badge"], edgecolor="none", zorder=2)
        ax.add_patch(tab)
        ax.text(x + 2.0, y + h - tab_h/2 + 0.2, name.upper(),
                ha="left", va="center", color="#FFFFFF", fontsize=9.0, fontweight="bold",
                fontfamily="sans-serif", zorder=3)

        # Subtitle
        ax.text(x + tab_w + 2.5, y + h - tab_h/2 + 0.2, subtitle,
                ha="left", va="center", color=colors["border"], fontsize=8.6, fontstyle="italic",
                fontfamily="sans-serif", zorder=3)

    # --------------------------------------------------------------------------
    # 0. TOP TITLE BANNER
    # --------------------------------------------------------------------------
    title_box = FancyBboxPatch((5, 93.8), 90, 4.6, boxstyle="round,pad=0,rounding_size=0.7",
                               facecolor=C["title_bg"], edgecolor="none", zorder=2)
    ax.add_patch(title_box)
    ax.text(50, 96.6, "ACDE: Policy-Bounded Autonomous Cloud Data Engineering Control Plane",
            ha="center", va="center", color="#FFFFFF", fontsize=14.5, fontweight="bold",
            fontfamily="sans-serif", zorder=3)
    ax.text(50, 94.9, "Supervisory Governance Framework for Cloud Data Pipelines (Batch DAGs & Streaming Windows)",
            ha="center", va="center", color="#94A3B8", fontsize=9.2, fontfamily="sans-serif", zorder=3)

    # --------------------------------------------------------------------------
    # TIER 4: ORCHESTRATION & ENTERPRISE GOVERNANCE (TOP)
    # --------------------------------------------------------------------------
    t4_y, t4_h = 73.0, 18.2
    draw_tier(t4_y, t4_h, "Tier 4: Orchestration & Governance",
              "Distributed ControlLoop · Two-Tier Arbitration · Multi-Actor RBAC · Keyset Audit Export",
              {"bg": C["t4_bg"], "border": C["t4_border"], "badge": C["t4_badge"]})

    draw_card(7.2, t4_y + 0.8, 20.0, 14.2, C["t4_border"],
              "ControlLoop Scheduler", [
                  "• Asynchronous Periodic Ticks",
                  "  Periodic monitoring scans",
                  "  Reactive execution on open faults",
                  "• Liveness & Resumability",
                  "  Durable heartbeat in control catalog",
                  "  Stateless: clean crash recovery"
              ])

    draw_card(29.0, t4_y + 0.8, 20.0, 14.2, C["t4_border"],
              "2-Tier Conflict Arbitration", [
                  "• Tier 1: Multi-Agent Bidding",
                  "  Priority: Recovery > Schema > Opt",
                  "  Tie-broken by action confidence",
                  "• Tier 2: Distributed Locks",
                  "  pg_try_advisory_lock on target",
                  "  Zero lock leakage across instances"
              ])

    draw_card(50.8, t4_y + 0.8, 20.0, 14.2, C["t4_border"],
              "Runtime Safety Controls", [
                  "• Durable Global Kill Switch",
                  "  Cross-process shared pause flag",
                  "  Halts action dispatch in <= 1 tick",
                  "• Hourly Blast-Radius Limits",
                  "  Enforces action caps per target",
                  "  Prevents cumulative infra fatigue"
              ])

    draw_card(72.6, t4_y + 0.8, 20.2, 14.2, C["t4_border"],
              "Enterprise API & Tenancy", [
                  "• Authenticated Operator API",
                  "  Constant-time compare_digest auth",
                  "  Hierarchical RBAC: viewer/approver/admin",
                  "• Keyset Streaming Audit",
                  "  O(1) memory compliance export",
                  "  Multi-tenant database segregation"
              ])

    # --------------------------------------------------------------------------
    # TIER 3: DECLARATIVE POLICY GATE & SAFE EXECUTION (OPA)
    # --------------------------------------------------------------------------
    t3_y, t3_h = 51.5, 18.2
    draw_tier(t3_y, t3_h, "Tier 3: Policy Gate & Safe Execution",
              "Open Policy Agent (OPA) · Formal Safety Invariants · Write-Ahead Audit · Tri-Mode Autonomy",
              {"bg": C["t3_bg"], "border": C["t3_border"], "badge": C["t3_badge"]})

    draw_card(7.2, t3_y + 0.8, 20.0, 14.2, C["t3_border"],
              "OPA Declarative Gate", [
                  "• Rate-Limit Runaway Guard",
                  "  Max 5 actions / 10m sliding window",
                  "• Marginal Cost Budget Gate",
                  "  Projected cost: ΔC <= Budget",
                  "• Safety Invariants",
                  "  Prior version check for rollback",
                  "  Breaking schema quarantine check"
              ])

    draw_card(29.0, t3_y + 0.8, 20.0, 14.2, C["t3_border"],
              "Fail-Safe Principle", [
                  "• Fail-Safe Containment",
                  "  If OPA is unreachable / timeout:",
                  "  Gate FAILS SAFE: allowed=False,",
                  "  escalate=True (human escalation)",
                  "• Formal Safety Guarantee",
                  "  100% empirical containment rate",
                  "  Zero uncertified actions executed"
              ])

    draw_card(50.8, t3_y + 0.8, 20.0, 14.2, C["t3_border"],
              "Write-Ahead Audit Trail", [
                  "• Write-Ahead Logging (WAL)",
                  "  Row committed with status='executing'",
                  "  BEFORE external side-effects run",
                  "  Guarantees zero phantom actions",
                  "• Target Invariant Sanitizer",
                  "  Rejects hallucinated model targets",
                  "  prior to external API invocation"
              ])

    draw_card(72.6, t3_y + 0.8, 20.2, 14.2, C["t3_border"],
              "Tri-Mode Autonomy Ladder", [
                  "• Shadow Mode",
                  "  Logs proposal, triggers webhook",
                  "• Approval Mode (Human-in-Loop)",
                  "  Enqueues action in approvals table",
                  "  Operator sign-off via CLI / API",
                  "• Autonomous Mode",
                  "  Direct execution with bounded retry"
              ])

    # --------------------------------------------------------------------------
    # TIER 2: BOUNDED MULTI-AGENT SUPERVISORY TIER
    # --------------------------------------------------------------------------
    t2_y, t2_h = 28.5, 19.5
    draw_tier(t2_y, t2_h, "Tier 2: Bounded Multi-Agent Supervisory Tier",
              "Specialized Closed-Vocabulary Agents · Dual-Tier LLM Gateway · Bayesian Adaptation · Pydantic Contracts",
              {"bg": C["t2_bg"], "border": C["t2_border"], "badge": C["t2_badge"]})

    # Cognitive infrastructure ribbon
    cog_ribbon = FancyBboxPatch((7.2, t2_y + 14.3), 85.6, 2.0, boxstyle="round,pad=0,rounding_size=0.4",
                                facecolor="#DCFCE7", edgecolor="#059669", linewidth=1.1, zorder=2)
    ax.add_patch(cog_ribbon)
    ax.text(8.2, t2_y + 15.3, "COGNITIVE BOUNDARIES:",
            ha="left", va="center", color="#065F46", fontsize=8.6, fontweight="bold", fontfamily="sans-serif", zorder=3)
    ax.text(26.2, t2_y + 15.3, "Closed Pydantic Action Schema  |  Temp=0  |  Budget Limits (60 calls, 150k tokens)  |  Clamped Bayesian Adaptation",
            ha="left", va="center", color="#1E293B", fontsize=8.2, fontfamily="sans-serif", zorder=3)

    draw_card(7.2, t2_y + 0.8, 20.0, 12.8, C["t2_border"],
              "Monitoring Agent", [
                  "• Fast-Tier LLM (Haiku / Flash)",
                  "• Statistical z-score pre-filter",
                  "• Task failure & retry detection",
                  "• Freshness SLA breach monitor",
                  "• Stamps detected_ts (MTTR start)"
              ])

    draw_card(29.0, t2_y + 0.8, 20.0, 12.8, C["t2_border"],
              "Optimization Agent", [
                  "• Reasoning-Tier (Sonnet / Pro)",
                  "• Dynamic worker scaling (1..8)",
                  "• Orchestrator pool slot adjustments",
                  "• Pipeline DAG reprioritization",
                  "• Stamps resolved_ts on success"
              ])

    draw_card(50.8, t2_y + 0.8, 20.0, 12.8, C["t2_border"],
              "Schema Agent", [
                  "• Reasoning-Tier (Sonnet / Pro)",
                  "• Schema evolution detection",
                  "• Backward-compatible mapping",
                  "• Quarantine isolation for breaking drift",
                  "• Stamps resolved_ts on success"
              ])

    draw_card(72.6, t2_y + 0.8, 20.2, 12.8, C["t2_border"],
              "Recovery Agent", [
                  "• Reasoning-Tier (Sonnet / Pro)",
                  "• Transactional rollback (v - 1)",
                  "• Orchestrator task instance replay",
                  "• Upstream partial recomputation",
                  "• Stamps resolved_ts (MTTR end)"
              ])

    # --------------------------------------------------------------------------
    # TIER 1: DATA PLANE, TELEMETRY & CONNECTORS (BOTTOM)
    # --------------------------------------------------------------------------
    t1_y, t1_h = 6.2, 19.0
    draw_tier(t1_y, t1_h, "Tier 1: Pipeline Data Plane & Telemetry Engine",
              "Connector Protocol · Batch DAGs · Streaming Aggregations · Transactional Partitions · Cost Ledger",
              {"bg": C["t1_bg"], "border": C["t1_border"], "badge": C["t1_badge"]})

    draw_card(7.2, t1_y + 0.8, 20.0, 15.0, C["t1_border"],
              "Connector Protocol", [
                  "• Orchestrator Abstraction (C)",
                  "  Airflow least-privilege REST",
                  "  Prefect & Noop adapters",
                  "  trigger(), clear_tasks(), set_pool()",
                  "• Health & Diagnostic Probes",
                  "  Continuous connectivity checks",
                  "  Production execution safety flags"
              ])

    draw_card(29.0, t1_y + 0.8, 20.0, 15.0, C["t1_border"],
              "Workload Pipelines", [
                  "• Batch: Apache Airflow",
                  "  TPC-DS ingest & validation DAGs",
                  "  Execution pools & task status",
                  "• Streaming: Redpanda / Kafka",
                  "  Tumbling 60s window aggregates",
                  "  Dynamic worker sizing (1..8)",
                  "  Live consumer group monitoring"
              ])

    draw_card(50.8, t1_y + 0.8, 20.0, 15.0, C["t1_border"],
              "Transactional Partitions", [
                  "• Versioned Warehouse Tables",
                  "  Immutable partition naming schema",
                  "  pg_advisory_xact_lock concurrency",
                  "• Zero-Copy Rollback Pointer Flip",
                  "  Instantaneous O(1) version flip",
                  "  Isolated quarantine table sink"
              ])

    draw_card(72.6, t1_y + 0.8, 20.2, 15.0, C["t1_border"],
              "Telemetry & Cost Engine", [
                  "• Exact Freshness Engine",
                  "  Stream: t_mat - t_event <= 60s",
                  "  Batch: staleness = t_now - t_create",
                  "• Disclosed Hybrid Cost Model",
                  "  Step-integrated compute: ∫ W(t) dt",
                  "  Persisted warehouse storage (GB)",
                  "  Avoided over-provisioning credit"
              ])

    # --------------------------------------------------------------------------
    # CONNECTING FLOW ARROWS
    # --------------------------------------------------------------------------
    def draw_flow_arrow(x, y_start, y_end, color, label=""):
        arrow = FancyArrowPatch((x, y_start), (x, y_end),
                                arrowstyle="-|>,head_length=5,head_width=3",
                                connectionstyle="arc3,rad=0",
                                color=color, linewidth=2.4, zorder=6)
        ax.add_patch(arrow)
        if label:
            ax.text(x + 0.8, (y_start + y_end)/2, label,
                    ha="left", va="center", color=color, fontsize=7.6, fontweight="bold",
                    fontfamily="sans-serif", zorder=7,
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="#FFFFFF", edgecolor=color, linewidth=0.9, alpha=0.96))

    # Upward Telemetry Stream: Tier 1 -> Tier 2
    draw_flow_arrow(22.0, t1_y + t1_h, t2_y, C["flow_tel"], "TelemetrySnapshot (S_t)")

    # Upward Action Proposals: Tier 2 -> Tier 3
    draw_flow_arrow(39.0, t2_y + t2_h, t3_y, C["flow_prop"], "ProposedAction (a)")

    # Upward Policy Decisions: Tier 3 -> Tier 4
    draw_flow_arrow(60.0, t3_y + t3_h, t4_y, C["flow_dec"], "PolicyDecision (d)")

    # Downward Controlled Side-Effect Channel (Left)
    side_path = patches.Path(
        [(7.2, t3_y + 7.5), (2.8, t3_y + 7.5), (2.8, t1_y + 8.0), (7.2, t1_y + 8.0)],
        [patches.Path.MOVETO, patches.Path.LINETO, patches.Path.LINETO, patches.Path.LINETO]
    )
    side_patch = patches.PathPatch(side_path, facecolor="none", edgecolor=C["flow_exec"],
                                   linewidth=2.2, linestyle="--", zorder=5)
    ax.add_patch(side_patch)
    side_arrow = FancyArrowPatch((3.8, t1_y + 8.0), (7.2, t1_y + 8.0),
                                 arrowstyle="-|>,head_length=5,head_width=3",
                                 color=C["flow_exec"], linewidth=2.2, zorder=6)
    ax.add_patch(side_arrow)
    ax.text(3.0, (t3_y + t1_y)/2 + 7.5, "GATED EXECUTION SIDE-EFFECTS\n(Shadow / Approval / Autonomous)",
            ha="center", va="center", color=C["flow_exec"], fontsize=7.4, fontweight="bold",
            fontfamily="sans-serif", rotation=90, zorder=6,
            bbox=dict(boxstyle="round,pad=0.22", facecolor="#FFFBEB", edgecolor=C["flow_exec"], linewidth=0.9))

    # Downward Human Intervention Channel (Right)
    esc_path = patches.Path(
        [(92.8, t3_y + 7.5), (97.2, t3_y + 7.5), (97.2, t4_y + 7.5), (92.8, t4_y + 7.5)],
        [patches.Path.MOVETO, patches.Path.LINETO, patches.Path.LINETO, patches.Path.LINETO]
    )
    esc_patch = patches.PathPatch(esc_path, facecolor="none", edgecolor=C["flow_human"],
                                  linewidth=2.2, linestyle=":", zorder=5)
    ax.add_patch(esc_patch)
    esc_arrow = FancyArrowPatch((96.0, t4_y + 7.5), (92.8, t4_y + 7.5),
                                arrowstyle="-|>,head_length=5,head_width=3",
                                color=C["flow_human"], linewidth=2.2, zorder=6)
    ax.add_patch(esc_arrow)
    ax.text(97.0, (t3_y + t4_y)/2 + 7.5, "HUMAN ESCALATIONS & APPROVALS\n(Queue & Interventions)",
            ha="center", va="center", color=C["flow_human"], fontsize=7.4, fontweight="bold",
            fontfamily="sans-serif", rotation=270, zorder=6,
            bbox=dict(boxstyle="round,pad=0.22", facecolor="#FAF5FF", edgecolor=C["flow_human"], linewidth=0.9))

    # --------------------------------------------------------------------------
    # BOTTOM FLOW LEGEND BAR
    # --------------------------------------------------------------------------
    legend_box = FancyBboxPatch((5, 1.0), 90, 3.4, boxstyle="round,pad=0,rounding_size=0.5",
                                facecolor="#F8FAFC", edgecolor="#CBD5E1", linewidth=1.1, zorder=2)
    ax.add_patch(legend_box)

    ax.text(7.2, 2.7, "FLOW LEGEND:", ha="left", va="center",
            color="#0F172A", fontsize=8.6, fontweight="bold", fontfamily="sans-serif", zorder=3)

    # Item 1: Telemetry
    ax.plot([16.5, 20.0], [2.7, 2.7], color=C["flow_tel"], linewidth=2.6, zorder=3)
    ax.text(20.8, 2.7, "Telemetry Snapshot Stream", ha="left", va="center", color="#334155", fontsize=8.0, fontfamily="sans-serif", zorder=3)

    # Item 2: Proposal
    ax.plot([36.0, 39.5], [2.7, 2.7], color=C["flow_prop"], linewidth=2.6, zorder=3)
    ax.text(40.3, 2.7, "Action Proposal (ProposedAction)", ha="left", va="center", color="#334155", fontsize=8.0, fontfamily="sans-serif", zorder=3)

    # Item 3: Decision
    ax.plot([58.0, 61.5], [2.7, 2.7], color=C["flow_dec"], linewidth=2.6, zorder=3)
    ax.text(62.3, 2.7, "Policy Verdict (PolicyDecision)", ha="left", va="center", color="#334155", fontsize=8.0, fontfamily="sans-serif", zorder=3)

    # Item 4: Execution
    ax.plot([78.5, 82.0], [2.7, 2.7], color=C["flow_exec"], linewidth=2.6, linestyle="--", zorder=3)
    ax.text(82.8, 2.7, "Controlled Side-Effects", ha="left", va="center", color="#334155", fontsize=8.0, fontfamily="sans-serif", zorder=3)

    # Save
    plt.savefig(output_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none", bbox_inches="tight")
    plt.close(fig)
    print(f"Paper-ready diagram successfully saved to {output_path} ({os.path.getsize(output_path)} bytes)")

if __name__ == "__main__":
    draw_paper_diagram()
