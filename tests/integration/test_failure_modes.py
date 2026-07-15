"""Integration failure-mode test (requires `make up` + `make seed`, MOCK_LLM=1).

Proves the headline fault-tolerance behaviour end-to-end: when the OPA policy engine is
unreachable, the gate fails safe by escalating, the executor records a human intervention, and the
agent cycle completes without crashing (DEVIATIONS D-052/D-053). The unit suite covers the
Airflow-down and DB-blip degrade paths with mocks; this test exercises the real OPA-down path by
stopping the ``opa`` container. OPA is always restarted (and its health confirmed) in teardown.
"""

from __future__ import annotations

import subprocess
import time
import urllib.error
import urllib.request

import pytest

from acde import db
from acde.agents.recovery import RecoveryAgent
from acde.chaos.injector import FaultInjector
from acde.chaos.scenarios import run_seed
from acde.config import get_settings

pytestmark = pytest.mark.integration

RUN = "itest-failmode"


def _compose(*args: str) -> None:
    # inherits the caller's env (e.g. DOCKER_CONTEXT=desktop-linux) like the Makefile does
    subprocess.run(["docker", "compose", *args], check=True)


def _opa_healthy(timeout: float = 30.0) -> bool:
    url = f"{get_settings().opa_url}/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            time.sleep(1)
    return False


@pytest.fixture
def opa_down():
    """Stop the OPA container for the test body; guarantee it is back and healthy afterwards."""
    db.execute("DELETE FROM telemetry.failure_events WHERE experiment_run = %s", (RUN,))
    db.execute("DELETE FROM telemetry.agent_actions WHERE experiment_run = %s", (RUN,))
    db.execute("DELETE FROM telemetry.manual_interventions WHERE experiment_run = %s", (RUN,))
    _compose("stop", "opa")
    try:
        yield
    finally:
        _compose("start", "opa")
        assert _opa_healthy(), "OPA did not become healthy again after restart"


def test_opa_down_fails_safe_to_escalation(opa_down):
    """OPA unreachable ⇒ gate escalates, executor logs a manual intervention, no crash."""
    seed = run_seed("full", "upstream_delay", 0)
    FaultInjector(experiment_run=RUN).inject("upstream_delay", seed)

    # must not raise even though the policy engine is down
    result = RecoveryAgent(experiment_run=RUN).run_once()

    action = db.fetch_one(
        "SELECT policy_decision, policy_reason, executed FROM telemetry.agent_actions "
        "WHERE experiment_run = %s AND agent = 'recovery' ORDER BY ts DESC LIMIT 1",
        (RUN,),
    )
    assert action is not None, "recovery agent logged no action"
    assert action["policy_decision"] == "escalated"
    assert not action["executed"]

    intervention = db.fetch_one(
        "SELECT count(*) AS n FROM telemetry.manual_interventions WHERE experiment_run = %s",
        (RUN,),
    )
    assert intervention["n"] >= 1
    assert result.outcome  # a structured outcome was returned rather than an exception
