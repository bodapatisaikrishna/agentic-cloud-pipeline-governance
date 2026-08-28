"""Unit tests for live decision-quality monitoring (D-100) -- mocked db."""

from unittest.mock import MagicMock

from acde.ops import decision_quality


class TestLiveDecisionQuality:
    def test_scores_correct_and_incorrect_incidents(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_all.return_value = [
            {
                "event_id": "e1",
                "fault_type": "schema_breaking",
                "actions_taken": ["quarantine_partition"],
            },
            {
                "event_id": "e2",
                "fault_type": "cpu_high",
                "actions_taken": ["reprioritize_pipeline"],
            },
            {
                "event_id": "e3",
                "fault_type": "task_failed",
                "actions_taken": ["scale_workers"],
            },  # wrong
        ]
        monkeypatch.setattr(decision_quality, "db", fake)
        result = decision_quality.live_decision_quality(since_hours=24.0)
        assert result["total_scored"] == 3
        assert result["correct"] == 2
        assert result["accuracy"] == 0.667
        assert result["unscored"] == 0

    def test_unmapped_fault_type_is_unscored_not_incorrect(self, monkeypatch):
        # the exact bug this taxonomy fixes: an unmapped fault_type must not silently drag
        # accuracy down by being counted as a wrong answer.
        fake = MagicMock()
        fake.fetch_all.return_value = [
            {
                "event_id": "e1",
                "fault_type": "schema_breaking",
                "actions_taken": ["quarantine_partition"],
            },
            {"event_id": "e2", "fault_type": "some_future_detector_kind", "actions_taken": []},
        ]
        monkeypatch.setattr(decision_quality, "db", fake)
        result = decision_quality.live_decision_quality()
        assert result["total_scored"] == 1
        assert result["correct"] == 1
        assert result["accuracy"] == 1.0
        assert result["unscored"] == 1
        assert "some_future_detector_kind" not in result["by_fault_type"]

    def test_no_incidents_gives_none_accuracy_not_zero(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_all.return_value = []
        monkeypatch.setattr(decision_quality, "db", fake)
        result = decision_quality.live_decision_quality()
        assert result["total_scored"] == 0
        assert result["accuracy"] is None

    def test_no_action_taken_is_incorrect(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_all.return_value = [
            {"event_id": "e1", "fault_type": "cpu_high", "actions_taken": []},
        ]
        monkeypatch.setattr(decision_quality, "db", fake)
        result = decision_quality.live_decision_quality()
        assert result["correct"] == 0
        assert result["total_scored"] == 1

    def test_by_fault_type_breakdown(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_all.return_value = [
            {"event_id": "e1", "fault_type": "cpu_high", "actions_taken": ["scale_workers"]},
            {"event_id": "e2", "fault_type": "cpu_high", "actions_taken": []},
        ]
        monkeypatch.setattr(decision_quality, "db", fake)
        result = decision_quality.live_decision_quality()
        assert result["by_fault_type"]["cpu_high"] == {"total": 2, "correct": 1}

    def test_tenant_id_adds_the_filter_clause_and_param(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_all.return_value = []
        monkeypatch.setattr(decision_quality, "db", fake)
        decision_quality.live_decision_quality(tenant_id="acme")
        sql, params = fake.fetch_all.call_args.args
        assert "fe.tenant_id = %(tenant_id)s" in sql
        assert params == {"tenant_id": "acme"}
