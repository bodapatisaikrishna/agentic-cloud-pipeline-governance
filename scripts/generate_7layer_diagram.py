#!/usr/bin/env python3
"""
Generate a pristine, publication-grade 7-Layer System Architecture diagram
specifically designed for IEEE Transactions / Journal papers.

Features:
- Exactly 7 architectural layers (Layers 1-7) derived from the ACDE codebase.
- Uncluttered, minimalist card design: keeps strictly the component names in bold, legible typography.
- Perfectly balanced horizontal symmetry and margins.
- High-precision vector arrows with filled arrowheads and crisp flow badges.
- Professional IEEE publication color palette with high contrast.
- Clear data flow, policy boundary, lock arbitration, and side-effect actuation paths.
- Generates 300 DPI high-resolution PNG and vector PDF formatted for IEEE double-column width.
"""

import os
import shutil
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

def draw_7layer_architecture(
    output_png="docs/system_architecture_7layer.png",
    output_pdf="docs/system_architecture_7layer.pdf"
):
    os.makedirs(os.path.dirname(output_png) or ".", exist_ok=True)

    # 16 x 14.0 inches at 300 DPI (4800 x 4200 px)
    fig = plt.figure(figsize=(16, 14.0), dpi=300)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    # Clean white background
    ax.add_patch(patches.Rectangle((0, 0), 100, 100, facecolor="#FFFFFF", edgecolor="none"))

    # Color Palette per Layer - Distinct, sophisticated IEEE styling
    layer_theme = {
        7: {"bg": "#F8FAFC", "border": "#334155", "header": "#1E293B", "card_bg": "#FFFFFF", "card_border": "#475569"},
        6: {"bg": "#F8FAFC", "border": "#475569", "header": "#334155", "card_bg": "#FFFFFF", "card_border": "#64748B"},
        5: {"bg": "#FFFBEB", "border": "#D97706", "header": "#B45309", "card_bg": "#FFFFFF", "card_border": "#D97706"},
        4: {"bg": "#FEF2F2", "border": "#DC2626", "header": "#B91C1C", "card_bg": "#FFFFFF", "card_border": "#DC2626"},
        3: {"bg": "#F0FDF4", "border": "#059669", "header": "#047857", "card_bg": "#FFFFFF", "card_border": "#059669"},
        2: {"bg": "#F0F9FF", "border": "#0284C7", "header": "#0369A1", "card_bg": "#FFFFFF", "card_border": "#0284C7"},
        1: {"bg": "#EEF2FF", "border": "#4F46E5", "header": "#3730A3", "card_bg": "#FFFFFF", "card_border": "#4F46E5"},
    }

    # Symmetrical horizontal geometry
    container_x = 6.8
    container_w = 86.4
    card_w = 19.4
    card_spacing = 1.4
    cards_x_start = container_x + (container_w - (4 * card_w + 3 * card_spacing)) / 2

    # 1. Main Header Banner
    title_box = FancyBboxPatch((container_x, 95.2), container_w, 4.0,
                               boxstyle="round,pad=0,rounding_size=0.6",
                               facecolor="#0F172A", edgecolor="none", zorder=3)
    ax.add_patch(title_box)

    ax.text(50.0, 97.4, "ACDE: Autonomous Cloud Data Engineering Control Plane",
            ha="center", va="center", color="#FFFFFF", fontsize=15.0, fontweight="bold",
            fontfamily="sans-serif", zorder=4)
    ax.text(50.0, 96.1, "Seven-Layer Supervisory Architecture for Policy-Bounded Autonomous Data Platforms",
            ha="center", va="center", color="#94A3B8", fontsize=9.6, fontweight="normal",
            fontfamily="sans-serif", zorder=4)

    # Layer specifications (from top Layer 7 down to bottom Layer 1)
    layers_def = [
        {
            "num": 7,
            "title": "LAYER 7: ENTERPRISE GOVERNANCE & MULTI-TENANCY PLANE",
            "tag": "API & Governance",
            "height": 8.6,
            "cards": [
                "FastAPI Operator API",
                "Role-Based Access Control\n(RBAC)",
                "Tenant Registry &\nIsolation Manager",
                "Streaming Keyset\nAudit Exporter"
            ]
        },
        {
            "num": 6,
            "title": "LAYER 6: ORCHESTRATION, CONCURRENCY & DISTRIBUTED CONTROL",
            "tag": "Control & Arbitration",
            "height": 8.6,
            "cards": [
                "Asynchronous\nControl Loop",
                "Two-Tier Conflict\nArbitration",
                "Distributed PostgreSQL\nAdvisory Locks",
                "Durable Global\nKill Switch"
            ]
        },
        {
            "num": 5,
            "title": "LAYER 5: SAFE EXECUTION & GRADUATED AUTONOMY ENGINE",
            "tag": "Execution & Containment",
            "height": 8.6,
            "cards": [
                "Write-Ahead Audit Log\n(WAL Engine)",
                "Tri-Mode Autonomy Ladder\n(Shadow | Approval | Auto)",
                "Action Dispatcher &\nExecution Handlers",
                "Bounded Retry &\nEscalation Manager"
            ]
        },
        {
            "num": 4,
            "title": "LAYER 4: DECLARATIVE POLICY GATE & CONTAINMENT PLANE",
            "tag": "Policy Gate",
            "height": 8.6,
            "cards": [
                "Open Policy Agent\n(OPA Rego Engine)",
                "Rate-Limit Runaway\nGuard",
                "Marginal Cost Budget\nGuard",
                "Fail-Safe Escalation\nDefault"
            ]
        },
        {
            "num": 3,
            "title": "LAYER 3: BOUNDED MULTI-AGENT SUPERVISORY TIER",
            "tag": "Closed-Vocabulary Agents",
            "height": 9.9,
            "ribbon": "Cognitive Boundaries: Closed Pydantic Action Schema  •  Deterministic Temp=0  •  Per-Incident Token Limits",
            "cards": [
                "Monitoring Agent",
                "Optimization Agent",
                "Schema Agent",
                "Recovery Agent"
            ]
        },
        {
            "num": 2,
            "title": "LAYER 2: TELEMETRY & OBSERVABILITY SUBSYSTEM",
            "tag": "Telemetry & Metrics",
            "height": 8.6,
            "cards": [
                "Telemetry Collector\nEngine",
                "Data Freshness SLA\nEngine",
                "Normalized Hybrid\nCost Ledger",
                "Failure & Incident\nTracker"
            ]
        },
        {
            "num": 1,
            "title": "LAYER 1: PIPELINE DATA PLANE & CONNECTOR BOUNDARY",
            "tag": "Pipeline Substrate",
            "height": 8.6,
            "cards": [
                "Connector Protocol\n(Airflow / Prefect / Noop)",
                "Batch Workload DAGs\n(ETL & TPC-DS)",
                "Streaming Event Bus\n(Kafka / Redpanda)",
                "Transactional Partition\nManager"
            ]
        },
    ]

    inter_layer_gap = 4.1
    layer_positions = {}
    current_y = 5.8
    for ldef in reversed(layers_def):
        lnum = ldef["num"]
        layer_positions[lnum] = {
            "y": current_y,
            "h": ldef["height"]
        }
        current_y += ldef["height"] + inter_layer_gap

    # Draw Each Layer
    for ldef in layers_def:
        lnum = ldef["num"]
        ly = layer_positions[lnum]["y"]
        lh = layer_positions[lnum]["h"]
        theme = layer_theme[lnum]

        # Layer Outer Box
        container = FancyBboxPatch((container_x, ly), container_w, lh,
                                   boxstyle="round,pad=0,rounding_size=0.5",
                                   facecolor=theme["bg"], edgecolor=theme["border"],
                                   linewidth=1.4, zorder=1)
        ax.add_patch(container)

        # Layer Header Banner
        header_h = 2.0
        header_box = FancyBboxPatch((container_x, ly + lh - header_h), container_w, header_h,
                                    boxstyle="round,pad=0,rounding_size=0.5",
                                    facecolor=theme["header"], edgecolor="none", zorder=2)
        ax.add_patch(header_box)
        ax.add_patch(patches.Rectangle((container_x, ly + lh - header_h), container_w, 0.4,
                                       facecolor=theme["header"], edgecolor="none", zorder=2))

        # Header Title (Left) and Tag (Right)
        ax.text(container_x + 1.6, ly + lh - header_h/2, ldef["title"],
                ha="left", va="center", color="#FFFFFF", fontsize=9.8, fontweight="bold",
                fontfamily="sans-serif", zorder=3)
        ax.text(container_x + container_w - 1.6, ly + lh - header_h/2, ldef["tag"],
                ha="right", va="center", color="#CBD5E1", fontsize=8.6, fontweight="bold",
                fontfamily="sans-serif", zorder=3)

        # Cognitive Ribbon for Layer 3
        has_ribbon = "ribbon" in ldef
        ribbon_h = 1.1 if has_ribbon else 0
        if has_ribbon:
            ribbon_box = FancyBboxPatch((container_x + 1.5, ly + lh - header_h - 1.3), container_w - 3.0, ribbon_h,
                                        boxstyle="round,pad=0,rounding_size=0.25",
                                        facecolor="#065F46", edgecolor="none", zorder=3)
            ax.add_patch(ribbon_box)
            ax.text(container_x + container_w/2, ly + lh - header_h - 0.75, ldef["ribbon"],
                    ha="center", va="center", color="#A7F3D0", fontsize=7.8, fontweight="bold",
                    fontfamily="sans-serif", zorder=4)

        card_h = 5.3
        card_y = ly + 0.65

        for c_idx, card_title in enumerate(ldef["cards"]):
            cx = cards_x_start + c_idx * (card_w + card_spacing)

            # Soft Shadow
            shadow = FancyBboxPatch((cx + 0.12, card_y - 0.12), card_w, card_h,
                                    boxstyle="round,pad=0,rounding_size=0.4",
                                    facecolor="#CBD5E1", edgecolor="none", alpha=0.5, zorder=2)
            ax.add_patch(shadow)

            # Main Card Box
            card = FancyBboxPatch((cx, card_y), card_w, card_h,
                                  boxstyle="round,pad=0,rounding_size=0.4",
                                  facecolor=theme["card_bg"], edgecolor=theme["card_border"],
                                  linewidth=1.2, zorder=3)
            ax.add_patch(card)

            # Top Accent Line
            ax.add_patch(FancyBboxPatch((cx, card_y + card_h - 0.35), card_w, 0.35,
                                        boxstyle="round,pad=0,rounding_size=0.18",
                                        facecolor=theme["border"], edgecolor="none", zorder=4))

            # Component Name - Bold, Centered
            ax.text(cx + card_w/2, card_y + card_h * 0.48, card_title,
                    ha="center", va="center", color="#0F172A", fontsize=9.6, fontweight="bold",
                    fontfamily="sans-serif", multialignment="center", linespacing=1.2, zorder=5)

    # ---------------- Inter-Layer Connecting Flow Arrows ----------------
    flows = [
        (1, 2, "Raw Metrics & Observations"),
        (2, 3, "TelemetrySnapshot (S_t)"),
        (3, 4, "ProposedAction (a)"),
        (4, 5, "PolicyDecision (d)"),
        (5, 6, "Two-Tier Arbitration & Locks"),
        (6, 7, "Governance & Keyset Audit")
    ]

    for bot_num, top_num, flow_label in flows:
        y_bot = layer_positions[bot_num]["y"] + layer_positions[bot_num]["h"]
        y_top = layer_positions[top_num]["y"]
        y_mid = (y_bot + y_top) / 2

        badge_w = len(flow_label) * 0.65 + 3.4
        badge_h = 1.7

        # Lower line segment
        ax.add_patch(FancyArrowPatch((50.0, y_bot + 0.1), (50.0, y_mid - badge_h/2 - 0.1),
                                     arrowstyle="-", color="#0284C7", linewidth=1.8, zorder=6))

        # Upper arrow segment pointing into upper layer
        ax.add_patch(FancyArrowPatch((50.0, y_mid + badge_h/2 + 0.1), (50.0, y_top - 0.1),
                                     arrowstyle="-|>", mutation_scale=12,
                                     color="#0284C7", linewidth=1.8, zorder=6))

        # Flow Label Badge
        badge = FancyBboxPatch((50.0 - badge_w/2, y_mid - badge_h/2), badge_w, badge_h,
                               boxstyle="round,pad=0,rounding_size=0.35",
                               facecolor="#FFFFFF", edgecolor="#0284C7", linewidth=1.2, zorder=7)
        ax.add_patch(badge)
        ax.text(50.0, y_mid, flow_label,
                ha="center", va="center", color="#0369A1", fontsize=7.6, fontweight="bold",
                fontfamily="sans-serif", zorder=8)

    # ---------------- Left Side: Gated Actuation Feedback Path ----------------
    l5_mid_y = layer_positions[5]["y"] + layer_positions[5]["h"] / 2
    l1_mid_y = layer_positions[1]["y"] + layer_positions[1]["h"] / 2

    ax.plot([container_x, 3.8], [l5_mid_y, l5_mid_y], color="#D97706", lw=2.0, zorder=6)
    ax.plot([3.8, 3.8], [l5_mid_y, l1_mid_y], color="#D97706", lw=2.0, zorder=6)
    ax.add_patch(FancyArrowPatch((3.8, l1_mid_y), (container_x - 0.1, l1_mid_y),
                                 arrowstyle="-|>", mutation_scale=13,
                                 color="#D97706", linewidth=2.0, zorder=6))

    left_banner = FancyBboxPatch((1.1, (l5_mid_y + l1_mid_y)/2 - 11.5), 2.0, 23.0,
                                 boxstyle="round,pad=0,rounding_size=0.4",
                                 facecolor="#FEF3C7", edgecolor="#D97706", linewidth=1.2, zorder=7)
    ax.add_patch(left_banner)
    ax.text(2.1, (l5_mid_y + l1_mid_y)/2, "GATED PIPELINE ACTUATION (Safe Side-Effects)",
            ha="center", va="center", color="#B45309", fontsize=8.0, fontweight="bold",
            rotation=90, fontfamily="sans-serif", zorder=8)

    # ---------------- Right Side: Operator Governance & Escalations ----------------
    l7_mid_y = layer_positions[7]["y"] + layer_positions[7]["h"] / 2

    ax.plot([container_x + container_w, 96.2], [l7_mid_y, l7_mid_y], color="#7C3AED", lw=2.0, zorder=6)
    ax.plot([96.2, 96.2], [l7_mid_y, l5_mid_y], color="#7C3AED", lw=2.0, zorder=6)
    ax.add_patch(FancyArrowPatch((96.2, l5_mid_y), (container_x + container_w + 0.1, l5_mid_y),
                                 arrowstyle="-|>", mutation_scale=13,
                                 color="#7C3AED", linewidth=2.0, zorder=6))

    right_banner = FancyBboxPatch((96.9, (l7_mid_y + l5_mid_y)/2 - 10.5), 2.0, 21.0,
                                  boxstyle="round,pad=0,rounding_size=0.4",
                                  facecolor="#F3E8FF", edgecolor="#7C3AED", linewidth=1.2, zorder=7)
    ax.add_patch(right_banner)
    ax.text(97.9, (l7_mid_y + l5_mid_y)/2, "OPERATOR APPROVALS & ESCALATIONS",
            ha="center", va="center", color="#6D28D9", fontsize=8.0, fontweight="bold",
            rotation=-90, fontfamily="sans-serif", zorder=8)

    # ---------------- Bottom Legend ----------------
    leg_box = FancyBboxPatch((container_x, 1.2), container_w, 3.2,
                             boxstyle="round,pad=0,rounding_size=0.5",
                             facecolor="#F8FAFC", edgecolor="#CBD5E1", linewidth=1.0, zorder=2)
    ax.add_patch(leg_box)

    ax.text(container_x + 1.8, 2.8, "FLOW LEGEND:", ha="left", va="center",
            color="#0F172A", fontsize=9.0, fontweight="bold", fontfamily="sans-serif", zorder=3)

    ax.plot([container_x + 14.0, container_x + 17.5], [2.8, 2.8], color="#0284C7", lw=2.0)
    ax.text(container_x + 18.3, 2.8, "Inter-Layer State & Formal Protocol Stream",
            ha="left", va="center", color="#334155", fontsize=8.4, fontfamily="sans-serif", zorder=3)

    ax.plot([container_x + 44.0, container_x + 47.5], [2.8, 2.8], color="#D97706", lw=2.2)
    ax.text(container_x + 48.3, 2.8, "Gated Pipeline Actuation (Rollback / Tuning)",
            ha="left", va="center", color="#334155", fontsize=8.4, fontfamily="sans-serif", zorder=3)

    ax.plot([container_x + 71.0, container_x + 74.5], [2.8, 2.8], color="#7C3AED", lw=2.2)
    ax.text(container_x + 75.3, 2.8, "Human Escalation & Approvals",
            ha="left", va="center", color="#334155", fontsize=8.4, fontfamily="sans-serif", zorder=3)

    # Save 300 DPI PNG
    plt.savefig(output_png, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none")
    # Save Vector PDF
    plt.savefig(output_pdf, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()

    # Sync to paper diagram path and artifact directory
    shutil.copyfile(output_png, "docs/system_architecture_paper.png")
    artifact_dir = "/Users/bodapati/.gemini/antigravity/brain/ed669e01-a1e8-45d8-aefb-dde255fc5975"
    if os.path.exists(artifact_dir):
        shutil.copyfile(output_png, os.path.join(artifact_dir, "system_architecture_7layer.png"))
        shutil.copyfile(output_png, os.path.join(artifact_dir, "system_architecture_paper.png"))

    print(f"Successfully generated 7-layer architecture diagram: {output_png} and {output_pdf}")

if __name__ == "__main__":
    draw_7layer_architecture()
