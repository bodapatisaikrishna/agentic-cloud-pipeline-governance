"""Unit tests for the Phase 1 data-plane settings."""

from acde.config import Settings


class TestDataplaneDefaults:
    def test_streaming_defaults(self):
        s = Settings(_env_file=None)
        assert s.stream_topic == "acde.stream.events"
        assert s.stream_default_workers == 2
        assert (s.stream_min_workers, s.stream_max_workers) == (1, 8)
        assert s.stream_window_s == 60.0

    def test_dataset_defaults(self):
        s = Settings(_env_file=None)
        assert s.data_dir == "data"
        assert s.use_real_tlc is False
        assert s.use_real_opengov is False

    def test_env_overrides(self, monkeypatch):
        monkeypatch.setenv("STREAM_MAX_WORKERS", "16")
        monkeypatch.setenv("USE_REAL_TLC", "1")
        monkeypatch.setenv("DATA_DIR", "/data")
        s = Settings(_env_file=None)
        assert s.stream_max_workers == 16
        assert s.use_real_tlc is True
        assert s.data_dir == "/data"

    def test_telemetry_defaults_and_overrides(self, monkeypatch):
        s = Settings(_env_file=None)
        assert s.experiment_run == "adhoc"
        assert s.telemetry_interval_s == 5.0
        assert s.cost_window_s == 60.0
        monkeypatch.setenv("EXPERIMENT_RUN", "exp-7")
        monkeypatch.setenv("COST_WINDOW_S", "30")
        s2 = Settings(_env_file=None)
        assert s2.experiment_run == "exp-7"
        assert s2.cost_window_s == 30.0
