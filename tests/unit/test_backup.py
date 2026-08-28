"""Unit tests for pg_dump/pg_restore-backed backup & restore (D-099) -- subprocess is mocked."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from acde.config import Settings
from acde.ops import backup


@pytest.fixture(autouse=True)
def _settings(monkeypatch, tmp_path):
    monkeypatch.setattr(
        backup,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            postgres_host="dbhost",
            postgres_port=5433,
            postgres_user="acde",
            postgres_password="s3cret",
            postgres_db="acde",
            backup_dir=str(tmp_path / "backups"),
        ),
    )


class TestRequireTool:
    def test_raises_a_clear_error_when_missing(self, monkeypatch):
        monkeypatch.setattr(backup.shutil, "which", lambda name: None)
        with pytest.raises(RuntimeError, match="not found on PATH"):
            backup._require_tool("pg_dump")

    def test_returns_the_resolved_path_when_present(self, monkeypatch):
        monkeypatch.setattr(backup.shutil, "which", lambda name: f"/usr/bin/{name}")
        assert backup._require_tool("pg_dump") == "/usr/bin/pg_dump"


class TestBackup:
    def test_writes_a_timestamped_dump_file_and_calls_pg_dump_correctly(self, monkeypatch):
        monkeypatch.setattr(backup.shutil, "which", lambda name: f"/usr/bin/{name}")
        captured = {}

        def fake_run(args, env=None, capture_output=None, text=None):
            captured["args"] = args
            captured["env"] = env
            Path(args[args.index("-f") + 1]).write_bytes(b"fake dump content")
            return MagicMock(returncode=0, stderr="")

        monkeypatch.setattr(backup.subprocess, "run", fake_run)
        path = backup.backup()
        assert path.name.startswith("acde_backup_")
        assert path.name.endswith(".dump")
        assert path.exists()
        assert captured["args"][0] == "/usr/bin/pg_dump"
        assert "-Fc" in captured["args"]
        # connection goes through the environment, never argv -- the actual point of this design.
        assert captured["env"]["PGPASSWORD"] == "s3cret"
        assert captured["env"]["PGHOST"] == "dbhost"
        assert not any("s3cret" in str(a) for a in captured["args"])

    def test_raises_with_stderr_on_a_real_pg_dump_failure(self, monkeypatch):
        monkeypatch.setattr(backup.shutil, "which", lambda name: f"/usr/bin/{name}")
        monkeypatch.setattr(
            backup.subprocess,
            "run",
            lambda *a, **k: MagicMock(returncode=1, stderr="connection refused"),
        )
        with pytest.raises(RuntimeError, match="connection refused"):
            backup.backup()

    def test_creates_the_output_directory_if_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(backup.shutil, "which", lambda name: f"/usr/bin/{name}")

        def fake_run(args, env=None, capture_output=None, text=None):
            Path(args[args.index("-f") + 1]).write_bytes(b"x")
            return MagicMock(returncode=0, stderr="")

        monkeypatch.setattr(backup.subprocess, "run", fake_run)
        target = tmp_path / "nested" / "dir"
        assert not target.exists()
        path = backup.backup(output_dir=target)
        assert path.parent == target


class TestRestore:
    def test_raises_for_a_missing_dump_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(backup.shutil, "which", lambda name: f"/usr/bin/{name}")
        with pytest.raises(RuntimeError, match="no such dump file"):
            backup.restore(tmp_path / "nope.dump")

    def test_calls_pg_restore_with_clean_and_the_target_db(self, tmp_path, monkeypatch):
        monkeypatch.setattr(backup.shutil, "which", lambda name: f"/usr/bin/{name}")
        dump = tmp_path / "acde_backup_x.dump"
        dump.write_bytes(b"fake")
        captured = {}

        def fake_run(args, env=None, capture_output=None, text=None):
            captured["args"] = args
            captured["env"] = env
            return MagicMock(returncode=0, stderr="")

        monkeypatch.setattr(backup.subprocess, "run", fake_run)
        backup.restore(dump, target_db="acde_drill")
        assert "--clean" in captured["args"]
        assert "--if-exists" in captured["args"]
        assert captured["args"][captured["args"].index("-d") + 1] == "acde_drill"
        assert captured["env"]["PGDATABASE"] == "acde_drill"

    def test_defaults_target_db_to_the_configured_live_database(self, tmp_path, monkeypatch):
        monkeypatch.setattr(backup.shutil, "which", lambda name: f"/usr/bin/{name}")
        dump = tmp_path / "x.dump"
        dump.write_bytes(b"fake")
        captured = {}

        def fake_run(args, env=None, capture_output=None, text=None):
            captured["args"] = args
            return MagicMock(returncode=0, stderr="")

        monkeypatch.setattr(backup.subprocess, "run", fake_run)
        backup.restore(dump)
        assert captured["args"][captured["args"].index("-d") + 1] == "acde"

    def test_raises_on_a_real_pg_restore_failure(self, tmp_path, monkeypatch):
        monkeypatch.setattr(backup.shutil, "which", lambda name: f"/usr/bin/{name}")
        dump = tmp_path / "x.dump"
        dump.write_bytes(b"fake")
        monkeypatch.setattr(
            backup.subprocess,
            "run",
            lambda *a, **k: MagicMock(returncode=1, stderr="corrupt archive"),
        )
        with pytest.raises(RuntimeError, match="corrupt archive"):
            backup.restore(dump)
