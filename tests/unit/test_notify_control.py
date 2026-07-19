"""Unit tests for webhook notifications and runtime controls (kill switch + blast radius)."""

from unittest.mock import MagicMock

from acde.config import Settings
from acde.contracts import PolicyDecision, ProposedAction
from acde.notify import webhook
from acde.orchestrator import control


def _action():
    return ProposedAction(
        agent="schema",
        action_type="quarantine_partition",
        target="store_sales",
        justification="drift detected",
        confidence=0.9,
    )


ALLOW_ESCALATE = PolicyDecision(allowed=True, escalate=True, reason="contained", policy_id="schema")


class TestWebhook:
    def test_payload_is_slack_compatible_and_redacted(self):
        p = webhook.build_payload(
            "pending_approval", _action(), ALLOW_ESCALATE, "prod", approval_id=9
        )
        assert "text" in p and "ACDE" in p["text"]
        assert p["acde"]["action_type"] == "quarantine_partition"
        assert p["acde"]["approval_id"] == 9
        # action params must never be included (may reference data)
        assert "params" not in p["acde"]

    def test_disabled_when_no_url(self, monkeypatch):
        monkeypatch.setattr(
            webhook, "get_settings", lambda: Settings(_env_file=None, webhook_url="")
        )
        assert webhook.notify("escalation", _action(), ALLOW_ESCALATE, "prod") is False

    def test_filtered_events_not_sent(self, monkeypatch):
        monkeypatch.setattr(
            webhook,
            "get_settings",
            lambda: Settings(_env_file=None, webhook_url="http://x", webhook_events="escalation"),
        )
        # 'shadow_proposal' is not in the filter → not sent
        assert webhook.notify("shadow_proposal", _action(), ALLOW_ESCALATE, "prod") is False

    def test_enabled_event_is_queued(self, monkeypatch):
        monkeypatch.setattr(
            webhook,
            "get_settings",
            lambda: Settings(_env_file=None, webhook_url="http://x", webhook_events="escalation"),
        )
        monkeypatch.setattr(webhook.threading, "Thread", lambda **k: MagicMock(start=lambda: None))
        assert webhook.notify("escalation", _action(), ALLOW_ESCALATE, "prod") is True


class TestControl:
    def test_is_paused_reads_desired_state(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_one.return_value = {"value": {"paused": True}}
        monkeypatch.setattr(control, "db", fake)
        assert control.is_paused() is True

    def test_not_paused_when_absent(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_one.return_value = None
        monkeypatch.setattr(control, "db", fake)
        assert control.is_paused() is False

    def test_blast_radius_unlimited_when_cap_zero(self, monkeypatch):
        monkeypatch.setattr(
            control, "get_settings", lambda: Settings(_env_file=None, blast_radius_max_per_hour=0)
        )
        assert control.blast_radius_exceeded("prod", "tgt") is False

    def test_blast_radius_trips_at_cap(self, monkeypatch):
        monkeypatch.setattr(
            control, "get_settings", lambda: Settings(_env_file=None, blast_radius_max_per_hour=3)
        )
        fake = MagicMock()
        fake.fetch_one.return_value = {"n": 3}
        monkeypatch.setattr(control, "db", fake)
        assert control.blast_radius_exceeded("prod", "tgt") is True
