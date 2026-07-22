"""FastAPI operator API (P3): health, metrics, proposals, audit, approvals.

Multi-actor auth (T2.1): each request is authenticated via ``X-API-Key`` (JSON/CLI clients) or HTTP
Basic (browser dashboard — username=actor, password=key) against ``Settings.api_key_map``, and the
resolved *actor name* — not a client-supplied field — is what lands in the audit trail. The app
**refuses to build** with no key configured at all, so it can never be exposed unauthenticated by
accident. TLS is expected to be terminated by a reverse proxy (documented in docs/OPERATIONS.md).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from acde import db
from acde.config import get_settings
from acde.human import approvals
from acde.logging import get_logger
from acde.ops.health import doctor
from acde.server import dashboard, metrics

log = get_logger("server.app")

_basic = HTTPBasic(auto_error=False)


def _authenticate(
    x_api_key: Annotated[str, Header()] = "",
    basic: Annotated[HTTPBasicCredentials | None, Depends(_basic)] = None,
) -> str:
    """Resolve the caller to an actor name via X-API-Key or HTTP Basic; 401 on any mismatch."""
    key_map = get_settings().api_key_map
    if x_api_key:
        for actor, key in key_map.items():
            if x_api_key == key:
                return actor
    elif basic is not None:
        expected = key_map.get(basic.username)
        if expected is not None and basic.password == expected:
            return basic.username
    raise HTTPException(
        status_code=401,
        detail="invalid or missing credentials (X-API-Key header or HTTP Basic)",
        headers={"WWW-Authenticate": "Basic"},
    )


def create_app(require_key: bool = True) -> FastAPI:
    """Build the operator API. Raises if no API key at all is configured (fail-closed)."""
    if require_key and not get_settings().api_key_map:
        raise RuntimeError(
            "ACDE has no api_key/api_keys configured — refusing to start unauthenticated"
        )

    app = FastAPI(title="ACDE Operator API", version="2.0")
    auth = [Depends(_authenticate)] if require_key else []
    # In no-auth test mode there's no identity to resolve; fall back to a fixed actor name.
    actor_dep = _authenticate if require_key else (lambda: "api")

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

    @app.post("/approvals/{approval_id}/approve")
    def approve(approval_id: int, actor: str = Depends(actor_dep)) -> dict[str, Any]:
        return approvals.approve(approval_id, actor=actor)

    @app.post("/approvals/{approval_id}/reject")
    def reject(approval_id: int, note: str = "", actor: str = Depends(actor_dep)) -> dict[str, Any]:
        return approvals.reject(approval_id, actor=actor, note=note)

    dashboard.add_routes(app, actor_dep)
    return app


def main() -> None:  # pragma: no cover - server entrypoint
    import uvicorn

    s = get_settings()
    uvicorn.run(create_app(), host=s.api_host, port=s.api_port)


if __name__ == "__main__":  # pragma: no cover
    main()
