"""FastAPI operator API (P3): health, metrics, proposals, audit, approvals.

Static API-key auth (``X-API-Key``) on every route except ``/health``. The app **refuses to build**
without an ``api_key`` configured, so it can never be exposed unauthenticated by accident. TLS is
expected to be terminated by a reverse proxy (documented in docs/OPERATIONS.md).
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Response

from acde import db
from acde.config import get_settings
from acde.human import approvals
from acde.logging import get_logger
from acde.ops.health import doctor
from acde.server import metrics

log = get_logger("server.app")


def _require_key(x_api_key: str = Header(default="")) -> None:
    expected = get_settings().api_key
    if not expected or x_api_key != expected:
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")


def create_app(require_key: bool = True) -> FastAPI:
    """Build the operator API. Raises if no api_key is configured (fail-closed)."""
    if require_key and not get_settings().api_key:
        raise RuntimeError("ACDE api_key is not set — refusing to start an unauthenticated API")

    app = FastAPI(title="ACDE Operator API", version="2.0")
    auth = [Depends(_require_key)] if require_key else []

    @app.get("/health")
    def health() -> dict[str, Any]:  # unauthenticated liveness/readiness
        return doctor()

    @app.get("/metrics", dependencies=auth)
    def metrics_endpoint() -> Response:
        return Response(content=metrics.render(), media_type="text/plain; version=0.0.4")

    @app.get("/proposals", dependencies=auth)
    def proposals(limit: int = 50) -> list[dict[str, Any]]:
        return db.fetch_all(
            "SELECT agent, action_type, target, policy_decision, executed, outcome, ts "
            "FROM telemetry.agent_actions ORDER BY ts DESC LIMIT %s",
            (min(limit, 500),),
        )

    @app.get("/audit", dependencies=auth)
    def audit(limit: int = 100) -> list[dict[str, Any]]:
        return db.fetch_all(
            "SELECT agent, action_type, target, policy_decision, policy_reason, executed, "
            "outcome, llm_model, ts FROM telemetry.agent_actions ORDER BY ts DESC LIMIT %s",
            (min(limit, 1000),),
        )

    @app.get("/approvals", dependencies=auth)
    def list_approvals() -> list[dict[str, Any]]:
        return approvals.list_pending()

    @app.post("/approvals/{approval_id}/approve", dependencies=auth)
    def approve(approval_id: int, actor: str = "api") -> dict[str, Any]:
        return approvals.approve(approval_id, actor=actor)

    @app.post("/approvals/{approval_id}/reject", dependencies=auth)
    def reject(approval_id: int, actor: str = "api", note: str = "") -> dict[str, Any]:
        return approvals.reject(approval_id, actor=actor, note=note)

    return app


def main() -> None:  # pragma: no cover - server entrypoint
    import uvicorn

    s = get_settings()
    uvicorn.run(create_app(), host=s.api_host, port=s.api_port)


if __name__ == "__main__":  # pragma: no cover
    main()
