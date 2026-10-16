"""Draw the seven-layer architecture figure for the paper (Fig. 1).

Drawn at final print size (IEEE two-column width, 7.16 in) in the plain style of a hand-made
Visio/draw.io figure: grayscale, Arial, square boxes, orthogonal connectors, and arrows that follow
the real control loop of Section IV. Dashed boxes mark components that are implemented but were not
exercised in the evaluated campaign.

Usage: uv run python scripts/draw_architecture.py
Writes paper/figures/system_architecture.pdf (vector, used by the paper) and a 300-dpi PNG preview.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

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

W, H = 7.16, 5.55  # inches; IEEE \textwidth
LW = 0.6  # line width (pt)
LINE_H = 6.5 * 1.15 / 72  # one text line (in)
BAND_X0, BAND_X1 = 1.05, 6.05
ROW_X0, ROW_X1 = 1.12, 5.98
BAND_H, GAP, TOP = 0.58, 0.19, 5.50
BOX_H = 0.36
EXT_X0, EXT_X1 = 6.36, 7.10
BAND_FILL, BAND_EDGE = "#EFEFEF", "#7F7F7F"

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


def box(
    x: float,
    y: float,
    w: float,
    h: float,
    text: str = "",
    dashed: bool = False,
    bold: bool = False,
    fill: str = "white",
    va_top: bool = False,
) -> tuple[float, float, float, float]:
    ax.add_patch(
        Rectangle(
            (x, y), w, h, facecolor=fill, edgecolor="black", lw=LW,
            linestyle=(0, (3, 2)) if dashed else "-",
        )
    )
    if text:
        ty = y + h - 0.075 if va_top else y + h / 2
        ax.text(
            x + w / 2, ty, text, ha="center", va="center", linespacing=1.15,
            fontweight="bold" if bold else "normal",
        )
    return x, y, w, h


def row(layer: int, widths: list[float], gap: float = 0.10) -> list[tuple[float, float]]:
    """Split the band's usable width into boxes proportional to ``widths``; return (x, w)."""
    span = ROW_X1 - ROW_X0 - gap * (len(widths) - 1)
    unit = span / sum(widths)
    out, x = [], ROW_X0
    for wr in widths:
        out.append((x, wr * unit))
        x += wr * unit + gap
    return out


def arrow(points: list[tuple[float, float]], dashed: bool = False) -> None:
    """Orthogonal polyline ending in a filled arrowhead."""
    ls = (0, (3, 2)) if dashed else "-"
    xs, ys = zip(*points[:-1], strict=True)
    if len(points) > 2:
        ax.plot(xs, ys, color="black", lw=LW, linestyle=ls, solid_capstyle="butt")
    ax.annotate(
        "", xy=points[-1], xytext=points[-2],
        arrowprops={
            "arrowstyle": "-|>,head_length=0.45,head_width=0.2", "lw": LW,
            "color": "black", "linestyle": ls, "shrinkA": 0, "shrinkB": 0,
        },
    )


def label(x: float, y: float, text: str, ha: str = "left", rot: float = 0) -> None:
    ax.text(x, y, text, ha=ha, va="center", fontsize=6, rotation=rot, style="italic")


# ---- layer bands and left-hand labels ---------------------------------------------------------
NAMES = {
    7: "Enterprise\ngovernance",
    6: "Orchestration\nand trust",
    5: "Execution\nand audit",
    4: "Policy gate",
    3: "Bounded\nagents",
    2: "Telemetry",
    1: "Data plane",
}
for layer, name in NAMES.items():
    y = band_bottom(layer)
    ax.add_patch(
        Rectangle((BAND_X0, y), BAND_X1 - BAND_X0, BAND_H, facecolor=BAND_FILL,
                  edgecolor=BAND_EDGE, lw=LW)
    )
    lines = 2 + name.count("\n")
    top = y + BAND_H / 2 + (lines - 1) * LINE_H / 2
    ax.text(0.06, top, f"Layer {layer}", ha="left", va="center", fontweight="bold")
    ax.text(0.06, top - 0.55 * LINE_H, name, ha="left", va="top", linespacing=1.15)


def by(layer: int) -> float:
    return band_bottom(layer) + (BAND_H - BOX_H) / 2


# ---- Layer 7 -----------------------------------------------------------------------------------
for (x, w), t in zip(
    row(7, [1, 1.25, 1, 1]),
    ["Operator API\n(FastAPI)", "Role-based access\n(viewer, approver, admin)", "Tenant registry",
     "Audit export\n(keyset cursor)"],
    strict=True,
):
    box(x, by(7), w, BOX_H, t, dashed=True)

# ---- Layer 6 -----------------------------------------------------------------------------------
l6 = row(6, [1, 1, 1, 1.45])
box(l6[0][0], by(6), l6[0][1], BOX_H, "Control loop\n" + r"(tick $\tau$ = 15 s)")
box(l6[1][0], by(6), l6[1][1], BOX_H, "Arbitration\n(agent-priority bid)")
box(l6[2][0], by(6), l6[2][1], BOX_H, "Per-target\nadvisory lock")
box(l6[3][0], by(6), l6[3][1], BOX_H, "Autonomy modes, kill switch,\nblast-radius cap",
    dashed=True)

# ---- Layer 5: handlers <- dispatcher <- write-ahead audit log ---------------------------------
hx, dx, ax5 = row(5, [1.35, 1, 1.1], gap=0.32)
handlers = box(hx[0], by(5), hx[1], BOX_H, "Execution handlers\n(Airflow, PostgreSQL)")
dispatch = box(dx[0], by(5), dx[1], BOX_H, "Action dispatcher")
audit = box(ax5[0], by(5), ax5[1], BOX_H, "Write-ahead audit log\n(intent row, then outcome)")
arrow([(audit[0], mid(5)), (dispatch[0] + dispatch[2], mid(5))])
arrow([(dispatch[0], mid(5)), (handlers[0] + handlers[2], mid(5))])

# ---- Layer 4: context builder -> OPA with four policy packs ------------------------------------
cx, ox = row(4, [1, 2.9], gap=0.32)
ctx = box(cx[0], by(4), cx[1], BOX_H, "Context builder\n" + r"$c = (m, B, n, \kappa, v)$")
opa_y, opa_h = band_bottom(4) + 0.05, BAND_H - 0.10
opa = box(ox[0], opa_y, ox[1], opa_h, "Open Policy Agent (Rego)", va_top=True)
packs = ["Rate limit", "Cost budget", "Recovery\napproval", "Schema\ncompatibility"]
pw = (ox[1] - 0.10 - 0.06 * 3) / 4
for i, t in enumerate(packs):
    box(ox[0] + 0.05 + i * (pw + 0.06), opa_y + 0.05, pw, 0.25, t, fill="#F7F7F7")
arrow([(ctx[0] + ctx[2], mid(4)), (opa[0], mid(4))])
label((ctx[0] + ctx[2] + opa[0]) / 2, mid(4) + 0.06, r"$c$", ha="center")

# ---- Layer 3: LLM client <- agents -> contract check -------------------------------------------
lx, gx, kx = row(3, [0.95, 3.1, 1.05], gap=0.30)
llm = box(lx[0], by(3), lx[1], BOX_H, "LLM client\n(live or mock)")
grp_y, grp_h = band_bottom(3) + 0.04, BAND_H - 0.08
grp = box(gx[0], grp_y, gx[1], grp_h, "", fill="white")
ax.text(gx[0] + gx[1] / 2, grp_y + grp_h - 0.07, "Four bounded agents", ha="center",
        va="center", fontweight="bold")
aw = (gx[1] - 0.10 - 0.06 * 3) / 4
for i, t in enumerate(["Monitoring", "Optimization", "Schema", "Recovery"]):
    box(gx[0] + 0.05 + i * (aw + 0.06), grp_y + 0.05, aw, 0.24, t, fill="#F7F7F7")
contract = box(kx[0], by(3), kx[1], BOX_H, "Contract check\n(ProposedAction)")
arrow([(grp[0], mid(3) + 0.05), (llm[0] + llm[2], mid(3) + 0.05)])
arrow([(llm[0] + llm[2], mid(3) - 0.07), (grp[0], mid(3) - 0.07)])
arrow([(grp[0] + grp[2], mid(3)), (contract[0], mid(3))])

# ---- Layer 2 -----------------------------------------------------------------------------------
l2 = row(2, [0.9, 0.95, 1.35, 1.05], gap=0.22)
ledger = box(l2[0][0], by(2), l2[0][1], BOX_H, "Cost ledger")
box(l2[1][0], by(2), l2[1][1], BOX_H, "Freshness tracker")
store = box(l2[2][0], by(2), l2[2][1], BOX_H, "Telemetry store\n(PostgreSQL schema)")
coll = box(l2[3][0], by(2), l2[3][1], BOX_H, "Telemetry collector")
arrow([(coll[0], mid(2)), (store[0] + store[2], mid(2))])

# ---- Layer 1 -----------------------------------------------------------------------------------
l1 = row(1, [1.1, 1.15, 1, 1])
airflow = box(l1[0][0], by(1), l1[0][1], BOX_H, "Apache Airflow\n(batch DAGs)")
box(l1[1][0], by(1), l1[1][1], BOX_H, "Warehouse\n(versioned partitions)")
box(l1[2][0], by(1), l1[2][1], BOX_H, "Redpanda\n(stream topic)")
box(l1[3][0], by(1), l1[3][1], BOX_H, "Stream consumer")

# ---- inter-layer flows -------------------------------------------------------------------------
top1, top2, top3, top4 = (band_bottom(i) + BAND_H for i in (1, 2, 3, 4))
x_col = coll[0] + coll[2] / 2
arrow([(x_col, top1), (x_col, coll[1])])
label(x_col - 0.05, (top1 + band_bottom(2)) / 2, "metrics, task runs, failure events", ha="right")

x_snap = store[0] + store[2] / 2
arrow([(x_snap, store[1] + store[3]), (x_snap, grp_y)])
label(x_snap + 0.05, (top2 + band_bottom(3)) / 2, r"snapshot $s_k$")

x_prop = contract[0] + contract[2] / 2
arrow([(x_prop, contract[1] + contract[3]), (x_prop, opa_y)])
label(x_prop + 0.05, (top3 + band_bottom(4)) / 2, r"proposal $a$")

x_dec = audit[0] + audit[2] / 2
arrow([(x_dec, opa_y + opa_h), (x_dec, audit[1])])
label(x_dec + 0.05, (top4 + band_bottom(5)) / 2, r"decision $d$")

# left corridors: context inputs (inner) and mitigation actions (outer)
XI, XO = 0.97, 0.80
arrow([(ledger[0], mid(2)), (XI, mid(2)), (XI, mid(4)), (ctx[0], mid(4))])
label(XI - 0.045, (mid(2) + mid(4)) / 2, "cost, budget, action count", ha="center", rot=90)
arrow([(handlers[0], mid(5)), (XO, mid(5)), (XO, mid(1)), (airflow[0], mid(1))])
label(XO - 0.045, (mid(3) + mid(4)) / 2 + 0.55, "mitigation actions", ha="center", rot=90)

# ---- external actors ---------------------------------------------------------------------------
ax.text((EXT_X0 + EXT_X1) / 2, TOP - 0.02, "External", ha="center", va="top", style="italic")
oncall = box(EXT_X0, mid(5) - 0.25, EXT_X1 - EXT_X0, 0.50,
             "On-call\nengineer\n(simulated)")
arrow([(audit[0] + audit[2], mid(5) + 0.08), (oncall[0], mid(5) + 0.08)])
label((BAND_X1 + EXT_X0) / 2, mid(5) + 0.19, "escalate", ha="center")
XE = 6.20
arrow([(oncall[0], mid(5) - 0.12), (XE, mid(5) - 0.12), (XE, mid(1) + 0.10),
       (BAND_X1, mid(1) + 0.10)], dashed=True)
label(XE + 0.05, (mid(2) + mid(3)) / 2, "manual remediation", ha="center", rot=90)
inj = box(EXT_X0, mid(1) - 0.27, EXT_X1 - EXT_X0, 0.30, "Fault injector")
arrow([(inj[0], mid(1) - 0.12), (BAND_X1, mid(1) - 0.12)])

# ---- legend ------------------------------------------------------------------------------------
ly = 0.11
arrow([(1.12, ly), (1.47, ly)])
ax.text(1.53, ly, "data, proposal, and decision flow", va="center")
arrow([(2.95, ly), (3.30, ly)], dashed=True)
ax.text(3.36, ly, "human action", va="center")
ax.add_patch(Rectangle((4.15, ly - 0.06), 0.30, 0.12, facecolor="white", edgecolor="black",
                       lw=LW, linestyle=(0, (3, 2))))
ax.text(4.51, ly, "implemented, not exercised in the evaluation", va="center")

out = Path(__file__).resolve().parents[1] / "paper" / "figures" / "system_architecture"
fig.savefig(out.with_suffix(".pdf"))
fig.savefig(out.with_suffix(".png"), dpi=300)
print(f"wrote {out.with_suffix('.pdf')} and .png")
