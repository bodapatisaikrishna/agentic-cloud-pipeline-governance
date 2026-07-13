"""Unit tests for the collector's pure parsers/mappers."""

import pytest

from acde.telemetry.collector import (
    TelemetryCollector,
    _parse_mem_mb,
    component_workers,
    parse_docker_stats,
    task_instance_to_row,
)


class TestCollectorInit:
    def test_experiment_run_override(self):
        assert TelemetryCollector(experiment_run="exp-9").experiment_run == "exp-9"

    def test_experiment_run_defaults_from_settings(self):
        assert TelemetryCollector().experiment_run == "adhoc"


class TestParseMemMb:
    @pytest.mark.parametrize(
        ("text", "mb"),
        [
            ("529.7MiB / 3.826GiB", 529.7),
            ("2GiB / 4GiB", 2000.0),
            ("512KiB / 4GiB", 0.512),
            ("58.82MiB", 58.82),
        ],
    )
    def test_parses_used_side(self, text, mb):
        assert _parse_mem_mb(text) == pytest.approx(mb, rel=1e-3)


class TestParseDockerStats:
    def test_parses_lines(self):
        text = (
            "acde-postgres-1|1.00%|58.82MiB / 3.826GiB\nacde-redpanda-1|0.31%|654.6MiB / 3.826GiB\n"
        )
        rows = parse_docker_stats(text)
        assert len(rows) == 2
        assert rows[0]["component"] == "acde-postgres-1"
        assert rows[0]["cpu_pct"] == 1.0
        assert rows[0]["mem_mb"] == pytest.approx(58.82)
        assert rows[1]["cpu_pct"] == pytest.approx(0.31)

    def test_ignores_blank_lines(self):
        assert parse_docker_stats("\n\n") == []


class TestTaskInstanceToRow:
    def test_maps_fields(self):
        ti = {
            "dag_run_id": "run_1",
            "dag_id": "tpcds_ingest",
            "task_id": "ingest",
            "state": "success",
            "start_date": "2026-01-01T00:00:00+00:00",
            "end_date": "2026-01-01T00:00:01+00:00",
            "duration": 1.0,
            "try_number": 1,
        }
        row = task_instance_to_row(ti, "run-x")
        assert row == (
            "run_1",
            "tpcds_ingest",
            "ingest",
            "success",
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:00:01+00:00",
            1.0,
            1,
            None,
            "run-x",
        )

    def test_missing_try_number_defaults_zero(self):
        assert task_instance_to_row({"dag_id": "d"}, "r")[7] == 0


class TestComponentWorkers:
    def test_streaming_uses_streaming_workers(self):
        assert component_workers("streaming", running_slots=3, streaming_workers=5) == 5

    def test_batch_uses_running_slots(self):
        assert component_workers("batch", running_slots=3, streaming_workers=5) == 3

    def test_other_is_one(self):
        assert component_workers("acde-postgres-1", running_slots=3, streaming_workers=5) == 1
