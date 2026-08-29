"""Unit tests for webhook notifications and runtime controls (kill switch + blast radius)."""

from unittest.mock import MagicMock

from acde.config import Settings
from acde.contracts import PolicyDecision, ProposedAction
from acde.notify import pagerduty, webhook
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

    def test_payload_carries_a_slack_attachments_block(self):
        # D-101: additive, not a replacement -- text/acde must still be present alongside it.
        p = webhook.build_payload("escalation", _action(), ALLOW_ESCALATE, "prod")
        assert "text" in p and "acde" in p
        attachment = p["attachments"][0]
        assert attachment["color"] == "#E01E5A"  # escalation -> red
        blocks = attachment["blocks"]
        assert blocks[0]["text"]["text"] == p["text"]
        fields_text = " ".join(f["text"] for f in blocks[1]["fields"])
        assert "quarantine_partition" in fields_text
        assert "store_sales" in fields_text

    def test_attachment_color_by_severity(self):
        assert (
            webhook.build_payload("shadow_proposal", _action(), ALLOW_ESCALATE, "prod")[
                "attachments"
            ][0]["color"]
            == "#868686"
        )
        assert (
            webhook.build_payload("pending_approval", _action(), ALLOW_ESCALATE, "prod")[
                "attachments"
            ][0]["color"]
            == "#ECB22E"
        )

    def test_notify_dispatches_to_pagerduty_too(self, monkeypatch):
        monkeypatch.setattr(
            webhook,
            "get_settings",
            lambda: Settings(
                _env_file=None,
                webhook_url="",
                webhook_events="escalation",
                pagerduty_routing_key="rk",
            ),
        )
        monkeypatch.setattr(
            pagerduty,
            "get_settings",
            lambda: Settings(
                _env_file=None, webhook_events="escalation", pagerduty_routing_key="rk"
            ),
        )
        monkeypatch.setattr(
            pagerduty.threading, "Thread", lambda **k: MagicMock(start=lambda: None)
        )
        # no webhook_url configured, but PagerDuty is -- notify() must still report success.
        assert webhook.notify("escalation", _action(), ALLOW_ESCALATE, "prod") is True


class TestPagerDuty:
    def test_disabled_when_no_routing_key(self, monkeypatch):
        monkeypatch.setattr(
            pagerduty, "get_settings", lambda: Settings(_env_file=None, pagerduty_routing_key="")
        )
        assert pagerduty.send("escalation", _action(), ALLOW_ESCALATE, "prod") is False

    def test_shadow_proposal_never_pages_even_when_configured(self, monkeypatch):
        # the exact bug this exclusion prevents: without it, a shadow-mode "would have done this"
        # log entry would page someone for taking no real action at all.
        monkeypatch.setattr(
            pagerduty,
            "get_settings",
            lambda: Settings(
                _env_file=None, webhook_events="shadow_proposal", pagerduty_routing_key="rk"
            ),
        )
        assert pagerduty.send("shadow_proposal", _action(), ALLOW_ESCALATE, "prod") is False

    def test_escalation_pages_when_configured(self, monkeypatch):
        monkeypatch.setattr(
            pagerduty,
            "get_settings",
            lambda: Settings(
                _env_file=None, webhook_events="escalation", pagerduty_routing_key="rk"
            ),
        )
        monkeypatch.setattr(
            pagerduty.threading, "Thread", lambda **k: MagicMock(start=lambda: None)
        )
        assert pagerduty.send("escalation", _action(), ALLOW_ESCALATE, "prod") is True

    def test_event_payload_shape_and_redaction(self):
        action = _action()
        event = pagerduty.build_event("rk", "escalation", action, ALLOW_ESCALATE, "prod")
        assert event["routing_key"] == "rk"
        assert event["event_action"] == "trigger"
        assert event["dedup_key"] == str(action.action_id)
        assert event["payload"]["severity"] == "critical"
        assert "params" not in event["payload"]["custom_details"]
        assert event["payload"]["custom_details"]["action_type"] == "quarantine_partition"

    def test_severity_by_event(self):
        assert (
            pagerduty.build_event("rk", "pending_approval", _action(), ALLOW_ESCALATE, "prod")[
                "payload"
            ]["severity"]
            == "warning"
        )
        assert (
            pagerduty.build_event("rk", "execution_failure", _action(), ALLOW_ESCALATE, "prod")[
                "payload"
            ]["severity"]
            == "error"
        )


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


class TestHeartbeat:
    """D-088: the loop-liveness signal `acde loop-health` reads."""

    def test_record_heartbeat_upserts_desired_state(self, monkeypatch):
        fake = MagicMock()
        monkeypatch.setattr(control, "db", fake)
        control.record_heartbeat("prod")
        sql, params = fake.execute.call_args.args
        assert "control.desired_state" in sql
        assert params[0] == "acde.loop_heartbeat"
        assert '"experiment_run": "prod"' in params[1]

    def test_heartbeat_age_none_when_never_recorded(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_one.return_value = None
        monkeypatch.setattr(control, "db", fake)
        assert control.heartbeat_age_s() is None

    def test_heartbeat_age_reflects_elapsed_time(self, monkeypatch):
        import datetime as dt

        fake = MagicMock()
        fake.fetch_one.return_value = {
            "updated_ts": dt.datetime.now(dt.UTC) - dt.timedelta(seconds=30)
        }
        monkeypatch.setattr(control, "db", fake)
        age = control.heartbeat_age_s()
        assert age is not None
        assert 29 <= age <= 31
