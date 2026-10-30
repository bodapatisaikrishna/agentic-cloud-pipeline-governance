"""Campaign preflight: stack health and live-model checks run before and between runs (D-104).

Split out of the supervisor so each check can be exercised on its own. A campaign that starts
against a dead stack, a missing key, or a retired model would record the outage, not the system.
"""

from __future__ import annotations

import datetime as dt
import os
import urllib.request
from collections.abc import Callable

from pydantic import ValidationError

from acde import db
from acde.config import Settings, get_settings
from acde.contracts import ProposedAction, TelemetrySnapshot
from acde.llm.client import LLMClient, call_with_deadline


def _http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return bool(200 <= resp.status < 300)
    except Exception:
        return False


# psycopg_pool's checkout has no reliably-short bound when the server is refusing connections (a
# real incident: ``db.fetch_one`` blocked for 2+ hours while Postgres was down, silently freezing
# the whole health-check loop -- not just this one check). Give it a hard wall-clock deadline like
# every LLM call already has, so a dead database can never again stall the supervisor itself.
_HEALTH_DB_TIMEOUT_S = 10.0


def check_health(settings: Settings | None = None) -> list[str]:
    """Names of unhealthy dependencies (empty list == healthy)."""
    s = settings or get_settings()
    problems: list[str] = []
    try:
        call_with_deadline(lambda: db.fetch_one("SELECT 1 AS ok"), _HEALTH_DB_TIMEOUT_S)
    except Exception:
        problems.append("postgres")
    if not _http_ok(f"{s.opa_url.rstrip('/')}/health"):
        problems.append("opa")
    airflow_root = s.airflow_url.split("/api/", 1)[0].rstrip("/")
    if not _http_ok(f"{airflow_root}/health"):
        problems.append("airflow")
    return problems


def missing_credentials(settings: Settings) -> str | None:
    """Why a live run cannot work (a provider key is unset), or None. Never reveals a key."""
    provider = settings.llm_provider
    if provider == "gemini" and not settings.gemini_api_key.get_secret_value():
        return "GEMINI_API_KEY is not set"
    if provider == "openai_compatible" and not settings.oai_api_key.get_secret_value():
        return "OAI_API_KEY is not set"
    if provider == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"):
        return "ANTHROPIC_API_KEY is not set"
    return None


def preflight_live_models(client_factory: Callable[[], LLMClient] = LLMClient) -> list[str]:
    """One real call per model role; reasons any is unusable (empty == both roles work).

    A model can be listed by a provider yet retired, unentitled, or hanging (the pilot met all
    three). Monitoring routes to the fast model and every other agent to the reasoning model, so
    probing one agent of each role covers both. An unavailable model would degrade to ``no_action``
    for the whole campaign and the numbers would measure the outage, not the system.
    """
    from acde.agents.base import load_prompt

    now = dt.datetime.now(dt.UTC)
    snapshot = TelemetrySnapshot(
        experiment_run="preflight",
        window_start=now,
        window_end=now,
        open_anomalies=[
            {"event_id": "preflight", "scenario": "schema_drift", "fault_type": "schema_drift"}
        ],
        schema_compat="breaking",
    )
    problems: list[str] = []
    for agent in ("monitoring", "recovery"):
        client = client_factory()
        model = client.model_for(agent)
        result = client.propose(agent, snapshot, load_prompt(agent))
        if client.stats.degraded_unavailable:
            problems.append(f"{agent}: model {model} is unavailable")
            continue
        try:
            ProposedAction.model_validate({**result.action_json, "agent": agent})
        except ValidationError as exc:
            problems.append(f"{agent}: model {model} returned invalid output ({exc.error_count()})")
    return problems
