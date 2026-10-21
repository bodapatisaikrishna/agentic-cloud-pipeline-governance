"""Draw the seven-layer architecture figure for the paper (Fig. 1).

Drawn at final print size (IEEE two-column width, 7.16 in) in the flat style of a hand-made
Visio/draw.io figure: Arial, square-ish boxes, orthogonal connectors, no gradients or shadows.
Light tints group the seven layers into the three logical planes of the base design (data plane,
agentic control plane, policy and governance plane) plus the enterprise layer; the tints stay
distinguishable in grayscale. Numbered markers trace one control-loop tick. Dashed boxes mark
components that are implemented but were not exercised in the evaluated campaign.

Usage: uv run python scripts/draw_architecture.py
Writes paper/figures/system_architecture.pdf (vector, used by the paper) and a 300-dpi PNG preview.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle

plt.rcParams.update(
    {
        "font.family": "Arial",
        "font.size": 6.5,
        "mathtext.fontset": "custom",
        "mathtext.rm": "Arial",
        "mathtext.it": "Arial:italic",
        "pdf.fonttype": 42,
    }
)

W, H = 7.16, 5.80  # inches; IEEE \textwidth
LW = 0.6  # line width (pt)
INK = "#1A1A1A"
BAND_X0, BAND_X1 = 1.12, 6.05
ROW_X0, ROW_X1 = 1.20, 5.97
BAND_H, GAP, TOP = 0.58, 0.19, 5.76
BOX_H = 0.36
TAB_X0, TAB_W = 0.04, 0.74
EXT_X0, EXT_X1 = 6.36, 7.10
ROUND = "round,pad=0,rounding_size=0.03"

# Plane palette: light band tint, darker edge/tab colour, and a mid tint for nested boxes.
PLANES = {
    "data": ("#E4EEF8", "#2F6DA3", "#CFE0F1", "Data plane"),
    "control": ("#E3F2EA", "#2A7A56", "#CBE7D8", "Agentic control plane"),
    "policy": ("#FBEEDB", "#A8640C", "#F4DDBA", "Policy and governance plane"),
    "enterprise": ("#F0F0F0", "#7A7A7A", "#E2E2E2", "Enterprise extension"),
}
LAYER_PLANE = {
    7: "enterprise",
    6: "control",
    5: "policy",
    4: "policy",
    3: "control",
    2: "data",
    1: "data",
}
NAMES = {
    7: "Enterprise\ngovernance",
    6: "Orchestration\nand trust",
    5: "Execution\nand audit",
    4: "Policy gate",
    3: "Bounded\nagents",
    2: "Telemetry",
    1: "Data plane",
}

fig = plt.figure(figsize=(W, H))
ax = fig.add_axes((0, 0, 1, 1))
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.axis("off")


def band_bottom(layer: int) -> float:
    """Bottom y of a layer band; layer 7 is at the top."""
    k = 7 - layer
    return TOP - (k + 1) * BAND_H - k * GAP


def mid(layer: int) -> float:
    return band_bottom(layer) + BAND_H / 2


def by(layer: int) -> float:
    return band_bottom(layer) + (BAND_H - BOX_H) / 2


def box(
    x: float,
    y: float,
    w: float,
    h: float,
    text: str = "",
    dashed: bool = False,
    bold: bool = False,
    fill: str = "white",
    edge: str = INK,
    va_top: bool = False,
) -> tuple[float, float, float, float]:
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle=ROUND,
            facecolor=fill,
            edgecolor=edge,
            lw=LW,
            linestyle=(0, (3, 2)) if dashed else "-",
            zorder=2,
        )
    )
    if text:
        ty = y + h - 0.075 if va_top else y + h / 2
        ax.text(
            x + w / 2,
            ty,
            text,
            ha="center",
            va="center",
            linespacing=1.15,
            color=INK,
            fontweight="bold" if bold else "normal",
            zorder=3,
        )
    return x, y, w, h


def row(widths: list[float], gap: float = 0.10) -> list[tuple[float, float]]:
    """Split the band's usable width into boxes proportional to ``widths``; return (x, w)."""
    span = ROW_X1 - ROW_X0 - gap * (len(widths) - 1)
    unit = span / sum(widths)
    out, x = [], ROW_X0
    for wr in widths:
        out.append((x, wr * unit))
        x += wr * unit + gap
    return out


def arrow(points: list[tuple[float, float]], dashed: bool = False, color: str = INK) -> None:
    """Orthogonal polyline ending in a filled arrowhead."""
    ls = (0, (3, 2)) if dashed else "-"
    xs, ys = zip(*points[:-1], strict=True)
    if len(points) > 2:
        ax.plot(xs, ys, color=color, lw=LW, linestyle=ls, solid_capstyle="butt", zorder=1)
    ax.annotate(
        "",
        xy=points[-1],
        xytext=points[-2],
        zorder=1,
        arrowprops={
            "arrowstyle": "-|>,head_length=0.45,head_width=0.2",
            "lw": LW,
            "color": color,
            "linestyle": ls,
            "shrinkA": 0,
            "shrinkB": 0,
        },
    )


def label(x: float, y: float, text: str, ha: str = "left", rot: float = 0) -> None:
    ax.text(
        x,
        y,
        text,
        ha=ha,
        va="center",
        fontsize=6,
        rotation=rot,
        style="italic",
        color=INK,
        zorder=3,
    )


def step(x: float, y: float, n: int) -> None:
    """Numbered marker for one stage of the control-loop tick."""
    ax.add_patch(Circle((x, y), 0.062, facecolor=INK, edgecolor="none", zorder=4))
    ax.text(
        x,
        y - 0.004,
        str(n),
        ha="center",
        va="center",
        color="white",
        fontsize=5.5,
        fontweight="bold",
        zorder=5,
    )


# ---- layer bands with plane-coloured tabs ------------------------------------------------------
for layer, name in NAMES.items():
    tint, edge, _, _ = PLANES[LAYER_PLANE[layer]]
    y = band_bottom(layer)
    ax.add_patch(
        Rectangle(
            (BAND_X0, y), BAND_X1 - BAND_X0, BAND_H, facecolor=tint, edgecolor=edge, lw=LW, zorder=0
        )
    )
    ax.add_patch(
        Rectangle((TAB_X0, y), TAB_W, BAND_H, facecolor=edge, edgecolor=edge, lw=LW, zorder=0)
    )
    lines = 1 + name.count("\n")
    cy = y + BAND_H / 2
    ax.text(
        TAB_X0 + 0.07,
        cy + lines * 0.055,
        f"Layer {layer}",
        ha="left",
        va="center",
        color="white",
        fontweight="bold",
    )
    ax.text(
        TAB_X0 + 0.07,
        cy + lines * 0.055 - 0.065,
        name,
        ha="left",
        va="top",
        color="white",
        linespacing=1.1,
    )


def sub(layer: int) -> str:
    return PLANES[LAYER_PLANE[layer]][2]


# ---- Layer 7 -----------------------------------------------------------------------------------
for (x, w), t in zip(
    row([1, 1.25, 1, 1]),
    [
        "Operator API\n(FastAPI)",
        "Role-based access\n(viewer, approver, admin)",
        "Tenant registry",
        "Audit export\n(keyset cursor)",
    ],
    strict=True,
):
    box(x, by(7), w, BOX_H, t, dashed=True)

# ---- Layer 6 -----------------------------------------------------------------------------------
l6 = row([1, 1, 1, 1.45])
box(l6[0][0], by(6), l6[0][1], BOX_H, "Control loop\n" + r"(tick $\tau$ = 2 s)")
box(l6[1][0], by(6), l6[1][1], BOX_H, "Arbitration\n(agent-priority bid)")
box(l6[2][0], by(6), l6[2][1], BOX_H, "Per-target\nadvisory lock")
box(l6[3][0], by(6), l6[3][1], BOX_H, "Autonomy modes, kill switch,\nblast-radius cap", dashed=True)

# ---- Layer 5: handlers <- dispatcher <- write-ahead audit log ---------------------------------
hx, dx, ax5 = row([1.35, 1, 1.1], gap=0.34)
handlers = box(hx[0], by(5), hx[1], BOX_H, "Execution handlers\n(Airflow, PostgreSQL)")
dispatch = box(dx[0], by(5), dx[1], BOX_H, "Action dispatcher")
audit = box(ax5[0], by(5), ax5[1], BOX_H, "Write-ahead audit log\n(intent row, then outcome)")
arrow([(audit[0], mid(5)), (dispatch[0] + dispatch[2], mid(5))])
arrow([(dispatch[0], mid(5)), (handlers[0] + handlers[2], mid(5))])
step((audit[0] + dispatch[0] + dispatch[2]) / 2, mid(5) + 0.11, 6)

# ---- Layer 4: context builder -> OPA with four policy packs ------------------------------------
cx, ox = row([1, 2.9], gap=0.34)
ctx = box(cx[0], by(4), cx[1], BOX_H, "Context builder\n" + r"$c = (m, B, n, \kappa, v)$")
opa_y, opa_h = band_bottom(4) + 0.05, BAND_H - 0.10
opa = box(ox[0], opa_y, ox[1], opa_h, "Open Policy Agent (Rego)", va_top=True, bold=True)
packs = ["Rate limit", "Cost budget", "Recovery\napproval", "Schema\ncompatibility"]
pw = (ox[1] - 0.10 - 0.06 * 3) / 4
for i, t in enumerate(packs):
    box(ox[0] + 0.05 + i * (pw + 0.06), opa_y + 0.05, pw, 0.25, t, fill=sub(4))
arrow([(ctx[0] + ctx[2], mid(4)), (opa[0], mid(4))])
label((ctx[0] + ctx[2] + opa[0]) / 2, mid(4) + 0.07, r"$c$", ha="center")

# ---- Layer 3: LLM client <- agents -> contract check -------------------------------------------
lx, gx, kx = row([0.95, 3.1, 1.05], gap=0.30)
llm = box(lx[0], by(3), lx[1], BOX_H, "LLM client\n(live or mock)")
grp_y, grp_h = band_bottom(3) + 0.04, BAND_H - 0.08
grp = box(gx[0], grp_y, gx[1], grp_h, "")
ax.text(
    gx[0] + gx[1] / 2,
    grp_y + grp_h - 0.07,
    "Four bounded agents",
    ha="center",
    va="center",
    fontweight="bold",
    color=INK,
    zorder=3,
)
aw = (gx[1] - 0.10 - 0.06 * 3) / 4
for i, t in enumerate(["Monitoring", "Optimization", "Schema", "Recovery"]):
    box(gx[0] + 0.05 + i * (aw + 0.06), grp_y + 0.05, aw, 0.24, t, fill=sub(3))
contract = box(kx[0], by(3), kx[1], BOX_H, "Contract check\n(ProposedAction)")
arrow([(grp[0], mid(3) + 0.05), (llm[0] + llm[2], mid(3) + 0.05)])
arrow([(llm[0] + llm[2], mid(3) - 0.07), (grp[0], mid(3) - 0.07)])
arrow([(grp[0] + grp[2], mid(3)), (contract[0], mid(3))])
step((llm[0] + llm[2] + grp[0]) / 2, mid(3) + 0.17, 3)

# ---- Layer 2 -----------------------------------------------------------------------------------
l2 = row([0.9, 0.95, 1.35, 1.05], gap=0.22)
ledger = box(l2[0][0], by(2), l2[0][1], BOX_H, "Cost ledger")
box(l2[1][0], by(2), l2[1][1], BOX_H, "Freshness tracker")
store = box(l2[2][0], by(2), l2[2][1], BOX_H, "Telemetry store\n(PostgreSQL schema)")
coll = box(l2[3][0], by(2), l2[3][1], BOX_H, "Telemetry collector")
arrow([(coll[0], mid(2)), (store[0] + store[2], mid(2))])

# ---- Layer 1 -----------------------------------------------------------------------------------
l1 = row([1.1, 1.15, 1, 1])
airflow = box(l1[0][0], by(1), l1[0][1], BOX_H, "Apache Airflow\n(batch DAGs)")
box(l1[1][0], by(1), l1[1][1], BOX_H, "Warehouse\n(versioned partitions)")
box(l1[2][0], by(1), l1[2][1], BOX_H, "Redpanda\n(stream topic)")
box(l1[3][0], by(1), l1[3][1], BOX_H, "Stream consumer")

# ---- inter-layer flows (numbered: one control-loop tick) --------------------------------------
top1, top2, top3, top4 = (band_bottom(i) + BAND_H for i in (1, 2, 3, 4))
x_col = coll[0] + coll[2] / 2
arrow([(x_col, top1), (x_col, coll[1])])
label(x_col - 0.13, (top1 + band_bottom(2)) / 2, "metrics, task runs, failure events", ha="right")
step(x_col + 0.0, (top1 + band_bottom(2)) / 2, 1)

x_snap = store[0] + store[2] / 2
arrow([(x_snap, store[1] + store[3]), (x_snap, grp_y)])
label(x_snap + 0.13, (top2 + band_bottom(3)) / 2, r"snapshot $s_k$")
step(x_snap, (top2 + band_bottom(3)) / 2, 2)

x_prop = contract[0] + contract[2] / 2
arrow([(x_prop, contract[1] + contract[3]), (x_prop, opa_y)])
label(x_prop + 0.13, (top3 + band_bottom(4)) / 2, r"proposal $a$")
step(x_prop, (top3 + band_bottom(4)) / 2, 4)

x_dec = audit[0] + audit[2] / 2
arrow([(x_dec, opa_y + opa_h), (x_dec, audit[1])])
label(x_dec - 0.13, (top4 + band_bottom(5)) / 2, r"decision $d$: allow, deny, escalate", ha="right")
step(x_dec, (top4 + band_bottom(5)) / 2, 5)

# left corridors: context inputs (inner) and mitigation actions (outer)
XI, XO = 1.02, 0.86
arrow([(ledger[0], mid(2)), (XI, mid(2)), (XI, mid(4)), (ctx[0], mid(4))])
label(XI - 0.045, (mid(2) + mid(4)) / 2 - 0.05, "cost, budget, action count", ha="center", rot=90)
arrow([(handlers[0], mid(5)), (XO, mid(5)), (XO, mid(1)), (airflow[0], mid(1))])
label(XO - 0.045, (mid(4) + mid(5)) / 2 - 0.10, "mitigation actions", ha="center", rot=90)
step(XO, (mid(1) + mid(2)) / 2, 7)

# ---- external actors ---------------------------------------------------------------------------
ax.text(
    (EXT_X0 + EXT_X1) / 2, TOP - 0.02, "External", ha="center", va="top", style="italic", color=INK
)
oncall = box(EXT_X0, mid(5) - 0.25, EXT_X1 - EXT_X0, 0.50, "On-call\nengineer\n(simulated)")
arrow([(audit[0] + audit[2], mid(5) + 0.08), (oncall[0], mid(5) + 0.08)])
label((BAND_X1 + EXT_X0) / 2, mid(5) + 0.21, "escalate", ha="center")
XE = 6.20
arrow(
    [
        (oncall[0], mid(5) - 0.12),
        (XE, mid(5) - 0.12),
        (XE, mid(1) + 0.10),
        (BAND_X1, mid(1) + 0.10),
    ],
    dashed=True,
)
label(XE + 0.05, (mid(2) + mid(3)) / 2, "manual remediation", ha="center", rot=90)
inj = box(EXT_X0, mid(1) - 0.27, EXT_X1 - EXT_X0, 0.30, "Fault injector")
arrow([(inj[0], mid(1) - 0.12), (BAND_X1, mid(1) - 0.12)])

# ---- legend ------------------------------------------------------------------------------------
ly1, ly2 = 0.25, 0.09
for x, key in zip(
    (0.04, 0.95, 2.40, 4.17), ("data", "control", "policy", "enterprise"), strict=True
):
    tint, edge, _, name = PLANES[key]
    ax.add_patch(Rectangle((x, ly1 - 0.055), 0.22, 0.11, facecolor=tint, edgecolor=edge, lw=LW))
    ax.text(x + 0.28, ly1, name, va="center", color=INK)
arrow([(0.04, ly2), (0.39, ly2)])
ax.text(0.45, ly2, "data, proposal, and decision flow", va="center", color=INK)
arrow([(1.97, ly2), (2.32, ly2)], dashed=True)
ax.text(2.38, ly2, "human action", va="center", color=INK)
ax.add_patch(
    FancyBboxPatch(
        (3.12, ly2 - 0.06),
        0.30,
        0.12,
        boxstyle=ROUND,
        facecolor="white",
        edgecolor=INK,
        lw=LW,
        linestyle=(0, (3, 2)),
    )
)
ax.text(3.48, ly2, "implemented, not exercised in the evaluation", va="center", color=INK)
step(5.58, ly2, 1)
ax.text(5.66, ly2, "\u2013", va="center", color=INK)
step(5.80, ly2, 7)
ax.text(5.89, ly2, "one control-loop tick", va="center", color=INK)

out_dir = (
    Path(sys.argv[1])
    if len(sys.argv) > 1
    else (Path(__file__).resolve().parents[1] / "paper" / "figures")
)
out = out_dir / "system_architecture"
fig.savefig(out.with_suffix(".pdf"))
fig.savefig(out.with_suffix(".png"), dpi=300)
print(f"wrote {out.with_suffix('.pdf')} and .png")
