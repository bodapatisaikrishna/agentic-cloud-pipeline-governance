"""Minimal server-rendered operator dashboard (T2.2): pending approvals + metrics.

No JS, no external assets (works air-gapped), no session storage — auth is the same
``_authenticate`` dependency the JSON API uses (HTTP Basic here, so a browser gets a native
credential prompt), and POSTing approve/reject calls the exact same ``acde.human.approvals``
functions as ``/approvals/{id}/approve|reject``, so there is no separate, weaker write path.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from acde.human import approvals
from acde.server import metrics

_templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def add_routes(app: FastAPI, actor_dep: Callable[..., str]) -> None:
    """Register the /ui routes on ``app``, authenticated via the same dependency as the JSON API."""

    @app.get("/ui", response_class=HTMLResponse)
    def dashboard(request: Request, actor: str = Depends(actor_dep)) -> HTMLResponse:
        flash = request.query_params.get("flash", "")
        return _templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "actor": actor,
                "m": metrics.snapshot(),
                "approvals": approvals.list_pending(),
                "flash": flash,
                "flash_ok": request.query_params.get("ok") == "1",
            },
        )

    @app.post("/ui/approvals/{approval_id}/approve")
    def ui_approve(approval_id: int, actor: str = Depends(actor_dep)) -> RedirectResponse:
        result = approvals.approve(approval_id, actor=actor)
        ok = "1" if result["status"] == "executed" else "0"
        msg = f"#{approval_id}: {result['status']} — {result['outcome']}"
        return RedirectResponse(f"/ui?flash={quote(msg)}&ok={ok}", status_code=303)

    @app.post("/ui/approvals/{approval_id}/reject")
    def ui_reject(approval_id: int, actor: str = Depends(actor_dep)) -> RedirectResponse:
        result = approvals.reject(approval_id, actor=actor)
        msg = f"#{approval_id}: {result['status']}"
        return RedirectResponse(f"/ui?flash={quote(msg)}&ok=1", status_code=303)
