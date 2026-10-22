"""Draw the Azure reference-deployment figure for the paper (single IEEE column).

Same flat style as ``draw_architecture.py``. Every component, port and setting is taken from
``deploy/azure/`` (``deploy.sh``, ``cloud-init.yaml``, ``docker-compose.azure.yml``, ``Caddyfile``)
and ``deploy/docker-compose.prod.yml``; see DEVIATIONS D-104t.

Usage: uv run python scripts/draw_deployment.py
Writes paper/figures/azure_deployment.pdf (vector, used by the paper) and a 300-dpi PNG preview.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

plt.rcParams.update({"font.family": "Arial", "font.size": 5.5, "pdf.fonttype": 42})

W, H = 3.5, 3.95  # inches; IEEE \columnwidth
LW = 0.5
INK = "#1A1A1A"
ROUND = "round,pad=0,rounding_size=0.025"
AZ = ("#E4EEF8", "#2F6DA3")  # Azure boundary
NET = ("#FBEEDB", "#A8640C")  # network edge
VM = ("#E3F2EA", "#2A7A56")  # virtual machine
EXT = ("#F0F0F0", "#7A7A7A")  # external actors

fig = plt.figure(figsize=(W, H))
ax = fig.add_axes((0, 0, 1, 1))
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.axis("off")


def box(
    x: float,
    y: float,
    w: float,
    h: float,
    text: str = "",
    fill: str = "white",
    edge: str = INK,
    dashed: bool = False,
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
        )
    )
    if text:
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", color=INK, linespacing=1.2)
    return x, y, w, h


def arrow(p: tuple[float, float], q: tuple[float, float], both: bool = False) -> None:
    style = ("<|-|>" if both else "-|>") + ",head_length=0.35,head_width=0.15"
    ax.annotate(
        "",
        xy=q,
        xytext=p,
        arrowprops={"arrowstyle": style, "lw": LW, "color": INK, "shrinkA": 0, "shrinkB": 0},
    )


def label(x: float, y: float, text: str, ha: str = "left") -> None:
    ax.text(x, y, text, ha=ha, va="center", fontsize=5, style="italic", color=INK)


def title(x: float, y: float, text: str, color: str, bold: bool = True) -> None:
    ax.text(
        x, y, text, ha="left", va="center", color=color, fontweight="bold" if bold else "normal"
    )


# ---- external actors (top row) -----------------------------------------------------------------
user = box(0.05, 3.50, 1.05, 0.40, "Operator browser\n/ API client", *EXT)
dev = box(1.225, 3.50, 1.05, 0.40, "Developer laptop\n(Azure CLI)", *EXT)
le = box(2.40, 3.50, 1.05, 0.40, "Let's Encrypt\n(ACME)", *EXT)

# ---- Azure boundary, network edge, VM ----------------------------------------------------------
az = box(0.05, 0.05, 3.40, 3.25, "", *AZ)
title(0.12, 3.17, "Microsoft Azure · rg-acde · Southeast Asia", AZ[1])
net = box(
    0.15,
    2.62,
    3.20,
    0.42,
    "Public IP + DNS name (*.cloudapp.azure.com)\nNSG: 443/80 open; 22 from deployer IP only",
    *NET,
)
vm = box(0.15, 0.15, 3.20, 2.37, "", *VM)
title(0.22, 2.40, "VM acde-vm · Standard_B2pls_v2 (Arm64, 2 vCPU, 4 GB)", VM[1])
title(0.22, 2.27, "Ubuntu 24.04 LTS · Docker Compose", VM[1], bold=False)

L, R, CW = 0.25, 1.95, 1.30
caddy = box(L, 1.68, CW, 0.40, "Caddy 2.8\nHTTPS reverse proxy")
server = box(R, 1.68, CW, 0.40, "acde-server\nFastAPI API + dashboard")
loop = box(L, 1.02, CW, 0.46, "acde-loop: control loop\n(shadow mode, mock LLM,\nno-op connector)")
opa = box(R, 1.02, CW, 0.46, "OPA 0.68.0\nRego policy gate")
pg = box(L, 0.58, R + CW - L, 0.28, "PostgreSQL 16.6: telemetry, proposals, audit log")
box(
    L,
    0.22,
    R + CW - L,
    0.28,
    "cloud-init (first boot): install Docker, generate secrets (never in git), compose up",
    dashed=True,
)

# ---- flows -------------------------------------------------------------------------------------
ux = user[0] + user[2] / 2
arrow((ux, user[1]), (ux, net[1] + net[3]))
label(ux + 0.04, 3.40, "HTTPS")
lx = le[0] + le[2] / 2
arrow((lx, le[1]), (lx, net[1] + net[3]))
label(lx + 0.04, 3.40, "TLS certificate")
dx = dev[0] + dev[2] / 2
arrow((dx, dev[1]), (dx, az[1] + az[3]))
label(dx + 0.04, 3.40, "deploy.sh")

cx = caddy[0] + caddy[2] / 2
arrow((cx, net[1]), (cx, caddy[1] + caddy[3]))
label(cx + 0.04, 2.14, "443 (80 → redirect)")
arrow((caddy[0] + caddy[2], 1.88), (server[0], 1.88))
label((caddy[0] + caddy[2] + server[0]) / 2, 1.95, ":8099", ha="center")
sx = server[0] + server[2] / 2
arrow((sx, server[1]), (sx, opa[1] + opa[3]))
label(sx + 0.04, 1.58, "health probe")
arrow((loop[0] + loop[2], 1.25), (opa[0], 1.25))
label((loop[0] + loop[2] + opa[0]) / 2, 1.32, "proposal", ha="center")
qx = loop[0] + loop[2] / 2
arrow((qx, loop[1]), (qx, pg[1] + pg[3]), both=True)
XR = 3.30
ax.plot([server[0] + server[2], XR, XR], [1.78, 1.78, 0.72], color=INK, lw=LW)
arrow((XR, 0.72), (pg[0] + pg[2], 0.72))

out = Path(__file__).resolve().parents[1] / "paper" / "figures" / "azure_deployment"
fig.savefig(out.with_suffix(".pdf"))
fig.savefig(out.with_suffix(".png"), dpi=300)
print(f"wrote {out.with_suffix('.pdf')} and .png")
