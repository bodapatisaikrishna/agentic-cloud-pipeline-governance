#!/usr/bin/env python3
"""
Generate an authentic, realistic Microsoft Visio-style 7-Layer Architecture Diagram
specifically designed for IEEE Transactions / Journal papers.

Design principles (True Visio Engineering Style):
1. NO AI telltales: NO dark web-app banners, NO drop shadows, NO neon rainbow pills.
2. Authentic Visio geometry: Crisp rectangular shapes with standard 1pt technical borders,
   subtle container headers, and clean grid alignment.
3. Authentic Visio connectors: Orthogonal (right-angle) technical connectors with standard
   filled arrowheads and inline horizontal callout text boxes breaking the line.
4. Professional IEEE / Visio corporate palette: Classic Office Steel/Navy themes with restrained,
   high-contrast colors, pure white component boxes, and sharp typography.
5. Content: Strictly component names in bold, legible technical font (no bullet point clutter).
"""

import os
import shutil
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import Rectangle, FancyArrowPatch

def draw_visio_7layer_diagram(
    output_png="docs/system_architecture_7layer.png",
    output_pdf="docs/system_architecture_7layer.pdf"
):
    os.makedirs(os.path.dirname(output_png) or ".", exist_ok=True)

    # 15.0 x 12.2 inches at 300 DPI (4500 x 3660 px) - Classic Visio IEEE proportion
    fig = plt.figure(figsize=(15.0, 12.2), dpi=300)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    # Clean white background (standard Visio drawing canvas)
    ax.add_patch(Rectangle((0, 0), 100, 100, facecolor="#FFFFFF", edgecolor="none"))

    # Visio Corporate Engineering Color Themes per Layer
    visio_theme = {
        7: {"header_bg": "#1F4E78", "header_fg": "#FFFFFF", "body_bg": "#F2F5F9", "border": "#2F5597"},
        6: {"header_bg": "#2F5597", "header_fg": "#FFFFFF", "body_bg": "#F4F6F9", "border": "#41719C"},
        5: {"header_bg": "#843C0C", "header_fg": "#FFFFFF", "body_bg": "#FDF8F5", "border": "#C55A11"},
        4: {"header_bg": "#8B1E1E", "header_fg": "#FFFFFF", "body_bg": "#FDF4F4", "border": "#C00000"},
        3: {"header_bg": "#1E5E3A", "header_fg": "#FFFFFF", "body_bg": "#F2F8F4", "border": "#2E7D32"},
        2: {"header_bg": "#135D7A", "header_fg": "#FFFFFF", "body_bg": "#F0F7F9", "border": "#1976D2"},
        1: {"header_bg": "#1A365D", "header_fg": "#FFFFFF", "body_bg": "#F2F5F9", "border": "#2B4C7E"},
    }

    # 7 Architectural Layers definition (strictly component names, no clutter)
    layers_def = [
        {
            "num": 7,
            "title": "Layer 7: Enterprise Governance & Multi-Tenancy Plane",
            "tag": "[Control Catalog & Operator API]",
            "cards": [
                ("FastAPI Operator API", "REST Endpoints & Token Auth"),
                ("Role-Based Access Control", "RBAC Engine (Viewer/Approver/Admin)"),
                ("Tenant Registry & Isolation", "Multi-Tenant Quota Manager"),
                ("Streaming Keyset Audit", "O(1) Memory Compliance Exporter")
            ]
        },
        {
            "num": 6,
            "title": "Layer 6: Orchestration, Concurrency & Distributed Control",
            "tag": "[Distributed Consensus & Locks]",
            "cards": [
                ("Asynchronous ControlLoop", "Periodic Scanner & Resumability"),
                ("Two-Tier Conflict Arbitration", "Priority: Recovery > Schema > Opt"),
                ("PostgreSQL Advisory Locks", "Target-Level Non-Blocking Locks"),
                ("Durable Global Kill Switch", "Sub-Tick State Freeze & Heartbeat")
            ]
        },
        {
            "num": 5,
            "title": "Layer 5: Safe Execution & Graduated Autonomy Engine",
            "tag": "[Write-Ahead Audit & Dispatch]",
            "cards": [
                ("Write-Ahead Audit Log", "Pre-Execution State (WAL Engine)"),
                ("Tri-Mode Autonomy Ladder", "Shadow | Approval | Autonomous"),
                ("Action Dispatcher & Handlers", "Airflow, Kafka & Database Mutators"),
                ("Bounded Retry & Escalation", "3-Attempt Limit & Operator Fallback")
            ]
        },
        {
            "num": 4,
            "title": "Layer 4: Declarative Policy Gate & Containment Plane",
            "tag": "[Open Policy Agent (OPA)]",
            "cards": [
                ("Open Policy Agent", "Deterministic OPA Rego Engine"),
                ("Rate-Limit Runaway Guard", "Max 5 Operations / 10 Min Window"),
                ("Marginal Cost Budget Guard", "Marginal Delta C <= Budget Bound"),
                ("Fail-Safe Escalation Default", "Deny-by-Default Fallback Guarantee")
            ]
        },
        {
            "num": 3,
            "title": "Layer 3: Bounded Multi-Agent Supervisory Tier",
            "tag": "[Closed-Vocabulary Reasoning]",
            "ribbon": "Cognitive Invariants: Closed Pydantic Action Schema  |  Deterministic Temp = 0  |  Per-Incident Token Limits",
            "cards": [
                ("Monitoring Agent", "Fast-Tier LLM + Z-Score Pre-Filter"),
                ("Optimization Agent", "Reasoning-Tier Pool Tuning"),
                ("Schema Agent", "Breaking Drift & Quarantine"),
                ("Recovery Agent", "Task Replay & Partition Rollback")
            ]
        },
        {
            "num": 2,
            "title": "Layer 2: Telemetry & Observability Subsystem",
            "tag": "[Pipeline State & Metrics]",
            "cards": [
                ("Telemetry Collector Engine", "Airflow REST Probes & OS Metrics"),
                ("Data Freshness SLA Engine", "Stream Latency & Batch Staleness"),
                ("Normalized Hybrid Cost Ledger", "Step-Integrated Compute & Storage"),
                ("Failure & Incident Tracker", "Incident State & MTTR Ledger")
            ]
        },
        {
            "num": 1,
            "title": "Layer 1: Pipeline Data Plane & Connector Boundary",
            "tag": "[Execution Substrate & Storage]",
            "cards": [
                ("Connector Protocol Boundary", "Airflow / Prefect / Noop Plugs"),
                ("Batch Workload DAGs", "ETL Pipelines & TPC-DS Benchmarks"),
                ("Streaming Event Bus", "Redpanda / Kafka Window Aggregations"),
                ("Transactional Partition Manager", "Zero-Copy O(1) Rollback Pointer Flip")
            ]
        },
    ]

    # Balanced layout calculations
    container_x = 11.2
    container_w = 77.6
    layer_h = 9.2
    inter_layer_gap = 4.2
    card_w = 17.6
    card_spacing = 1.6
    cards_x_start = container_x + (container_w - (4 * card_w + 3 * card_spacing)) / 2

    # Compute layer positions from bottom up
    layer_positions = {}
    current_y = 4.6
    for ldef in reversed(layers_def):
        lnum = ldef["num"]
        lh = layer_h + 1.0 if "ribbon" in ldef else layer_h
        layer_positions[lnum] = {"y": current_y, "h": lh}
        current_y += lh + inter_layer_gap

    # ---------------- Draw Each Visio Layer Container ----------------
    for ldef in layers_def:
        lnum = ldef["num"]
        ly = layer_positions[lnum]["y"]
        lh = layer_positions[lnum]["h"]
        theme = visio_theme[lnum]

        # 1. Main Visio Container Box (Clean rectangular shape with 1pt technical border)
        container = Rectangle((container_x, ly), container_w, lh,
                              facecolor=theme["body_bg"], edgecolor=theme["border"],
                              linewidth=1.2, zorder=1)
        ax.add_patch(container)

        # 2. Visio Container Header Strip
        header_h = 2.2
        header_box = Rectangle((container_x, ly + lh - header_h), container_w, header_h,
                               facecolor=theme["header_bg"], edgecolor=theme["border"],
                               linewidth=1.2, zorder=2)
        ax.add_patch(header_box)

        # Header Title Text (Left) and Tag (Right)
        ax.text(container_x + 1.4, ly + lh - header_h / 2, ldef["title"],
                ha="left", va="center", color=theme["header_fg"], fontsize=10.0, fontweight="bold",
                fontfamily="sans-serif", zorder=3)
        ax.text(container_x + container_w - 1.4, ly + lh - header_h / 2, ldef["tag"],
                ha="right", va="center", color="#E0E8F0", fontsize=8.6, fontweight="bold",
                fontfamily="sans-serif", zorder=3)

        # 3. Optional Cognitive Ribbon inside Layer 3
        has_ribbon = "ribbon" in ldef
        ribbon_h = 1.0 if has_ribbon else 0
        if has_ribbon:
            ribbon_box = Rectangle((container_x + 1.0, ly + lh - header_h - 1.2), container_w - 2.0, ribbon_h,
                                   facecolor="#E8F5E9", edgecolor="#2E7D32",
                                   linewidth=0.8, linestyle="--", zorder=3)
            ax.add_patch(ribbon_box)
            ax.text(container_x + container_w / 2, ly + lh - header_h - 0.7, ldef["ribbon"],
                    ha="center", va="center", color="#1B5E20", fontsize=7.8, fontweight="bold",
                    fontfamily="sans-serif", zorder=4)

        # 4. Component Cards (Crisp Visio rectangular blocks: white fill, dark border)
        card_h = 5.4
        card_y = ly + 0.75

        for c_idx, (card_title, card_sub) in enumerate(ldef["cards"]):
            cx = cards_x_start + c_idx * (card_w + card_spacing)

            # Visio Shape: Sharp rectangle with clean technical border
            card = Rectangle((cx, card_y), card_w, card_h,
                             facecolor="#FFFFFF", edgecolor="#4A5568",
                             linewidth=1.0, zorder=3)
            ax.add_patch(card)

            # Top accent bar (classic Visio stencil accent)
            accent = Rectangle((cx, card_y + card_h - 0.3), card_w, 0.3,
                               facecolor=theme["border"], edgecolor="none", zorder=4)
            ax.add_patch(accent)

            # Component Name - Bold, Dark
            ax.text(cx + card_w / 2, card_y + card_h * 0.58, card_title,
                    ha="center", va="center", color="#111827", fontsize=9.2, fontweight="bold",
                    fontfamily="sans-serif", zorder=5)

            # Technical Subtitle / Role (clean dark gray, single line)
            ax.text(cx + card_w / 2, card_y + card_h * 0.28, card_sub,
                    ha="center", va="center", color="#4B5563", fontsize=7.2, fontweight="normal",
                    fontfamily="sans-serif", zorder=5)

    # ---------------- Authentic Visio Connectors (Between Layers) ----------------
    flows = [
        (1, 2, "Raw Metrics & Observation Stream"),
        (2, 3, "TelemetrySnapshot (S_t)"),
        (3, 4, "ProposedAction (a)  [Closed-Vocabulary Contract]"),
        (4, 5, "PolicyDecision (d)  [OPA Invariant Verdict]"),
        (5, 6, "Two-Tier Lock Arbitration & Concurrency Verification"),
        (6, 7, "Governance State & Keyset Audit Stream")
    ]

    for bot_num, top_num, flow_label in flows:
        y_bot = layer_positions[bot_num]["y"] + layer_positions[bot_num]["h"]
        y_top = layer_positions[top_num]["y"]
        y_mid = (y_bot + y_top) / 2

        # Visio Connector Line
        ax.plot([50.0, 50.0], [y_bot, y_top], color="#2B4C7E", linewidth=1.4, zorder=6)

        # Standard Visio Arrowhead at target
        ax.add_patch(FancyArrowPatch((50.0, y_top - 1.2), (50.0, y_top),
                                     arrowstyle="-|>", mutation_scale=11,
                                     color="#2B4C7E", linewidth=1.4, zorder=7))

        # Visio Connector Label: Clean white rectangular callout breaking the line
        label_w = len(flow_label) * 0.58 + 2.8
        label_h = 1.5
        label_box = Rectangle((50.0 - label_w / 2, y_mid - label_h / 2), label_w, label_h,
                              facecolor="#FFFFFF", edgecolor="#2B4C7E",
                              linewidth=0.9, zorder=8)
        ax.add_patch(label_box)
        ax.text(50.0, y_mid, flow_label,
                ha="center", va="center", color="#1F4E78", fontsize=7.6, fontweight="bold",
                fontfamily="sans-serif", zorder=9)

    # ---------------- Left Side: Orthogonal Actuation Feedback Connector ----------------
    # True Visio right-angled stepped connector with horizontal callout
    l5_mid_y = layer_positions[5]["y"] + layer_positions[5]["h"] / 2
    l1_mid_y = layer_positions[1]["y"] + layer_positions[1]["h"] / 2
    left_x = 5.2

    # Draw right-angle path: Layer 5 -> left -> down -> Layer 1
    ax.plot([container_x, left_x], [l5_mid_y, l5_mid_y], color="#C55A11", linewidth=1.5, zorder=6)
    ax.plot([left_x, left_x], [l5_mid_y, l1_mid_y], color="#C55A11", linewidth=1.5, zorder=6)
    ax.plot([left_x, container_x], [l1_mid_y, l1_mid_y], color="#C55A11", linewidth=1.5, zorder=6)

    # Visio Arrowhead pointing into Layer 1
    ax.add_patch(FancyArrowPatch((container_x - 1.2, l1_mid_y), (container_x, l1_mid_y),
                                 arrowstyle="-|>", mutation_scale=12,
                                 color="#C55A11", linewidth=1.5, zorder=7))

    # Visio Callout Box on vertical line (Horizontal text, clean white box)
    act_mid_y = (l5_mid_y + l1_mid_y) / 2
    act_box_w = 9.2
    act_box_h = 4.4
    act_box = Rectangle((left_x - act_box_w / 2, act_mid_y - act_box_h / 2), act_box_w, act_box_h,
                        facecolor="#FFF9F5", edgecolor="#C55A11",
                        linewidth=1.0, zorder=8)
    ax.add_patch(act_box)
    ax.text(left_x, act_mid_y + 1.1, "Gated Actuation Loop",
            ha="center", va="center", color="#843C0C", fontsize=8.2, fontweight="bold",
            fontfamily="sans-serif", zorder=9)
    ax.text(left_x, act_mid_y - 0.1, "Safe Data Plane Side-Effects",
            ha="center", va="center", color="#843C0C", fontsize=7.2, fontweight="normal",
            fontfamily="sans-serif", zorder=9)
    ax.text(left_x, act_mid_y - 1.2, "(Replay / Rollback / Sizing)",
            ha="center", va="center", color="#A04000", fontsize=6.8, style="italic",
            fontfamily="sans-serif", zorder=9)

    # ---------------- Right Side: Orthogonal Operator Escalations Connector ----------------
    # True Visio right-angled stepped connector with horizontal callout
    l7_mid_y = layer_positions[7]["y"] + layer_positions[7]["h"] / 2
    right_x = 94.8

    # Draw right-angle path: Layer 7 -> right -> down -> Layer 5
    ax.plot([container_x + container_w, right_x], [l7_mid_y, l7_mid_y], color="#5B2C6F", linewidth=1.5, zorder=6)
    ax.plot([right_x, right_x], [l7_mid_y, l5_mid_y], color="#5B2C6F", linewidth=1.5, zorder=6)
    ax.plot([right_x, container_x + container_w], [l5_mid_y, l5_mid_y], color="#5B2C6F", linewidth=1.5, zorder=6)

    # Visio Arrowhead pointing into Layer 5
    ax.add_patch(FancyArrowPatch((container_x + container_w + 1.2, l5_mid_y), (container_x + container_w, l5_mid_y),
                                 arrowstyle="-|>", mutation_scale=12,
                                 color="#5B2C6F", linewidth=1.5, zorder=7))

    # Visio Callout Box on vertical line (Horizontal text, clean white box)
    esc_mid_y = (l7_mid_y + l5_mid_y) / 2
    esc_box_w = 9.2
    esc_box_h = 4.4
    esc_box = Rectangle((right_x - esc_box_w / 2, esc_mid_y - esc_box_h / 2), esc_box_w, esc_box_h,
                        facecolor="#FBF7FC", edgecolor="#5B2C6F",
                        linewidth=1.0, zorder=8)
    ax.add_patch(esc_box)
    ax.text(right_x, esc_mid_y + 1.1, "Operator Escalation",
            ha="center", va="center", color="#4A148C", fontsize=8.2, fontweight="bold",
            fontfamily="sans-serif", zorder=9)
    ax.text(right_x, esc_mid_y - 0.1, "Human Approval Queue",
            ha="center", va="center", color="#4A148C", fontsize=7.2, fontweight="normal",
            fontfamily="sans-serif", zorder=9)
    ax.text(right_x, esc_mid_y - 1.2, "(Sign-off & Kill Switch)",
            ha="center", va="center", color="#6A1B9A", fontsize=6.8, style="italic",
            fontfamily="sans-serif", zorder=9)

    # Save high-res PNG and vector PDF
    plt.savefig(output_png, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.savefig(output_pdf, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()

    # Sync to paper diagram path and artifact directory
    shutil.copyfile(output_png, "docs/system_architecture_paper.png")
    artifact_dir = "/Users/bodapati/.gemini/antigravity/brain/ed669e01-a1e8-45d8-aefb-dde255fc5975"
    if os.path.exists(artifact_dir):
        shutil.copyfile(output_png, os.path.join(artifact_dir, "system_architecture_7layer.png"))
        shutil.copyfile(output_png, os.path.join(artifact_dir, "system_architecture_paper.png"))

    print(f"Successfully generated Visio-style 7-layer architecture diagram: {output_png} and {output_pdf}")

if __name__ == "__main__":
    draw_visio_7layer_diagram()
