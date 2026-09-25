"""Unit tests for the campaign supervisor (no stack, no subprocesses, no sleeping)."""

import json
import subprocess
import threading
import time
from pathlib import Path

import pytest

from acde.config import Settings
from acde.experiments import campaign, runner
from acde.experiments.campaign import Arm, CampaignConfig
from acde.experiments.configs import Run


def _cfg(tmp_path: Path, arms: list[Arm], **kw) -> CampaignConfig:
    return CampaignConfig(
        arms=arms, status_path=tmp_path / "status.json", stop_path=tmp_path / "STOP", **kw
    )


def _smoke_arm(tmp_path: Path, live: bool = False) -> Arm:
    return Arm("smoke", tmp_path / "res", frozenset({"baseline", "full"}), live, "smoke")


class FakeRunner:
    """Stands in for the child process: records one run per call, like the real runner would."""

    def __init__(self, arm: Arm, degraded: float = 0.0, tokens: float = 100.0, fail_first=0):
        self.arm, self.degraded, self.tokens, self.fail_first = arm, degraded, tokens, fail_first
        self.calls = 0

    def __call__(self, arm: Arm) -> int:
        self.calls += 1
        if self.calls <= self.fail_first:
            return 1
        run = runner.remaining_runs(arm.profile, arm.results_dir, arm.configs)[0]
        arm.results_dir.mkdir(parents=True, exist_ok=True)
        metrics = {
            "mttr_s": 1.0,
            "wall_clock_s": 2.0,
            "api_tokens": self.tokens,
            "llm_degraded": self.degraded,
        }
        runner._write_rows(arm.results_dir / "raw.csv", run, 1, metrics)
        runner._append_manifest(arm.results_dir / "manifest.jsonl", run, 1, metrics)
        return 0


def _go(cfg, invoke, health=lambda: [], sleeps=None, code_changed=lambda sha: False):
    return campaign.run_campaign(
        cfg,
        start_sha="abc",
        invoke=invoke,
        health=health,
        sleep=(sleeps.append if sleeps is not None else lambda s: None),
        code_changed=code_changed,
    )


class TestArms:
    def test_paper_arms_partition_the_matrix_without_overlap(self, tmp_path):
        arms = campaign.arms_for("paper", tmp_path)
        assert [a.name for a in arms] == ["live-agents", "baselines", "mock-full"]
        assert [a.live for a in arms] == [True, False, False]
        assert len({a.results_dir for a in arms}) == 3  # live and mock never share a dir
        live, base, _ = arms
        assert live.configs.isdisjoint(base.configs)
        covered = live.configs | base.configs
        assert covered == set(runner.ALL_CONFIGS)  # arms A+B cover the whole paper matrix

    def test_pilot2_is_one_live_arm(self, tmp_path):
        (arm,) = campaign.arms_for("pilot2", tmp_path)
        assert arm.live and arm.profile == "pilot2"

    def test_smoke_is_one_free_mock_arm(self, tmp_path):
        (arm,) = campaign.arms_for("smoke", tmp_path)
        assert not arm.live and arm.profile == "smoke"

    def test_pilot_is_one_live_arm(self, tmp_path):
        (arm,) = campaign.arms_for("pilot", tmp_path)
        assert arm.live and arm.profile == "pilot"


class TestLoop:
    def test_runs_everything_and_writes_heartbeat(self, tmp_path):
        arm = _smoke_arm(tmp_path)
        cfg = _cfg(tmp_path, [arm])
        fake = FakeRunner(arm)
        assert _go(cfg, fake) == campaign.COMPLETE
        assert fake.calls == 2
        status = json.loads(cfg.status_path.read_text())
        assert status["state"] == campaign.COMPLETE
        assert status["arms"]["smoke"] == {"done": 2, "total": 2}

    def test_resume_does_not_repeat_or_duplicate(self, tmp_path):
        arm = _smoke_arm(tmp_path)
        cfg = _cfg(tmp_path, [arm])
        FakeRunner(arm)(arm)  # a previous session finished one run, then died
        fake = FakeRunner(arm)
        assert _go(cfg, fake) == campaign.COMPLETE
        assert fake.calls == 1  # only the outstanding run
        rows = (arm.results_dir / "raw.csv").read_text().splitlines()
        assert len(rows) == len(set(rows))  # no duplicate rows

    def test_retries_a_failed_child_then_succeeds(self, tmp_path):
        arm = _smoke_arm(tmp_path)
        sleeps: list[float] = []
        fake = FakeRunner(arm, fail_first=2)
        assert _go(_cfg(tmp_path, [arm]), fake, sleeps=sleeps) == campaign.COMPLETE
        assert fake.calls == 4 and sleeps.count(60.0) == 2

    def test_aborts_after_repeated_failures(self, tmp_path):
        arm = _smoke_arm(tmp_path)
        cfg = _cfg(tmp_path, [arm], max_consecutive_failures=3)
        assert _go(cfg, FakeRunner(arm, fail_first=99)) == campaign.FAILURE_ABORT

    def test_zero_exit_that_recorded_nothing_counts_as_failure(self, tmp_path):
        arm = _smoke_arm(tmp_path)
        cfg = _cfg(tmp_path, [arm], max_consecutive_failures=2)
        assert _go(cfg, lambda a: 0) == campaign.FAILURE_ABORT

    def test_waits_for_health_then_proceeds(self, tmp_path):
        arm = _smoke_arm(tmp_path)
        states = iter([["postgres"], ["postgres", "opa"], []] + [[]] * 10)
        sleeps: list[float] = []
        health = lambda: next(states)  # noqa: E731
        out = _go(_cfg(tmp_path, [arm]), FakeRunner(arm), health=health, sleeps=sleeps)
        assert out == campaign.COMPLETE and sleeps[:2] == [60.0, 60.0]

    def test_aborts_if_stack_never_recovers(self, tmp_path):
        arm = _smoke_arm(tmp_path)
        cfg = _cfg(tmp_path, [arm], health_max_wait_s=120)
        fake = FakeRunner(arm)
        assert _go(cfg, fake, health=lambda: ["postgres"]) == campaign.UNHEALTHY_ABORT
        assert fake.calls == 0  # never burned a run against a dead stack

    def test_stop_file_halts_gracefully(self, tmp_path):
        arm = _smoke_arm(tmp_path)
        cfg = _cfg(tmp_path, [arm])
        cfg.stop_path.write_text("")
        fake = FakeRunner(arm)
        assert _go(cfg, fake) == campaign.STOPPED and fake.calls == 0

    def test_code_change_aborts(self, tmp_path):
        arm = _smoke_arm(tmp_path)
        fake = FakeRunner(arm)
        out = _go(_cfg(tmp_path, [arm]), fake, code_changed=lambda sha: True)
        assert out == campaign.CODE_CHANGED and fake.calls == 0


class TestGuards:
    def test_token_ceiling_stops_live_arm(self, tmp_path):
        (arm,) = campaign.arms_for("pilot", tmp_path)  # 8 runs, so the ceiling can bite
        cfg = _cfg(tmp_path, [arm], max_tokens=150.0)
        fake = FakeRunner(arm, tokens=100.0)
        assert _go(cfg, fake) == campaign.TOKEN_CEILING
        assert fake.calls == 2  # stops once 200 >= 150, before a third would start

    def test_ceiling_ignores_non_live_arms(self, tmp_path):
        arm = _smoke_arm(tmp_path, live=False)
        cfg = _cfg(tmp_path, [arm], max_tokens=1.0)
        assert _go(cfg, FakeRunner(arm, tokens=1e9)) == campaign.COMPLETE

    def test_degraded_streak_backs_off_then_aborts(self, tmp_path):
        arm = Arm("p", tmp_path / "r", frozenset({"full", "recovery_only"}), True, "pilot")
        cfg = _cfg(tmp_path, [arm], degraded_pause_after=2, degraded_abort_after=4)
        sleeps: list[float] = []
        out = _go(cfg, FakeRunner(arm, degraded=50.0), sleeps=sleeps)
        assert out == campaign.DEGRADED_ABORT
        assert 600.0 in sleeps  # paused before giving up

    def test_healthy_run_resets_degraded_streak(self, tmp_path):
        arm = _smoke_arm(tmp_path, live=True)
        cfg = _cfg(tmp_path, [arm], degraded_pause_after=1)
        sleeps: list[float] = []
        assert _go(cfg, FakeRunner(arm, degraded=0.0), sleeps=sleeps) == campaign.COMPLETE
        assert 600.0 not in sleeps


_GOOD = {
    "action_type": "no_action",
    "target": "none",
    "params": {},
    "justification": "j",
    "confidence": 0.5,
}


class _StubClient:
    """Stands in for LLMClient: returns a canned proposal or a degraded one."""

    def __init__(self, action, unavailable=False):
        from acde.llm.client import LLMResult, LLMStats

        self.stats = LLMStats()
        self._res = LLMResult(action, 1, 1, "m")
        self._unavailable = unavailable

    def model_for(self, agent):
        return f"model-for-{agent}"

    def propose(self, agent, snapshot, prompt):
        self.stats.degraded_unavailable += int(self._unavailable)
        return self._res


class TestPreflight:
    def test_healthy_models_pass(self):
        assert campaign.preflight_live_models(lambda: _StubClient(_GOOD)) == []

    def test_unavailable_model_is_named(self):
        problems = campaign.preflight_live_models(lambda: _StubClient(_GOOD, unavailable=True))
        assert len(problems) == 2  # both roles probed
        assert "model-for-monitoring" in problems[0] and "unavailable" in problems[0]

    def test_invalid_output_is_a_problem(self):
        bad = {
            "action_type": "delete_database",
            "target": "t",
            "justification": "j",
            "confidence": 0.5,
        }
        problems = campaign.preflight_live_models(lambda: _StubClient(bad))
        assert len(problems) == 2 and "invalid output" in problems[0]


class TestPrimitives:
    def test_write_status_is_atomic_and_leaves_no_temp(self, tmp_path):
        campaign.write_status(tmp_path / "s.json", {"a": 1})
        campaign.write_status(tmp_path / "s.json", {"a": 2})
        assert json.loads((tmp_path / "s.json").read_text()) == {"a": 2}
        assert not list(tmp_path.glob("*.tmp"))

    def test_total_tokens_sums_only_live_api_tokens(self, tmp_path):
        live, mock = _smoke_arm(tmp_path / "a", True), _smoke_arm(tmp_path / "b", False)
        for arm in (live, mock):
            FakeRunner(arm, tokens=40.0)(arm)
            FakeRunner(arm, tokens=40.0)(arm)
        assert campaign.total_tokens([live, mock]) == 80.0
        assert campaign.total_tokens([_smoke_arm(tmp_path / "none", True)]) == 0.0

    def test_run_metric(self, tmp_path):
        arm = _smoke_arm(tmp_path)
        FakeRunner(arm, degraded=7.0)(arm)
        rid = runner.run_id_for(Run("baseline", "upstream_delay", 0))
        assert campaign.run_metric(arm.results_dir, rid, "llm_degraded") == 7.0
        assert campaign.run_metric(arm.results_dir, rid, "nope") is None
        assert campaign.run_metric(tmp_path / "missing", rid, "x") is None

    def test_missing_credentials_never_leaks_a_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        for provider, expect in [
            ("gemini", "GEMINI_API_KEY"),
            ("openai_compatible", "OAI_API_KEY"),
            ("anthropic", "ANTHROPIC_API_KEY"),
        ]:
            why = campaign.missing_credentials(Settings(_env_file=None, llm_provider=provider))
            assert why is not None and expect in why
        ok = Settings(_env_file=None, llm_provider="gemini", gemini_api_key="sekrit-value")
        assert campaign.missing_credentials(ok) is None

    def test_check_health_reports_each_failing_dependency(self, monkeypatch):
        def bad_db(*a, **k):
            raise RuntimeError("down")

        monkeypatch.setattr(campaign.db, "fetch_one", bad_db)
        monkeypatch.setattr(campaign, "_http_ok", lambda url: "8181" not in url)
        assert campaign.check_health(Settings(_env_file=None)) == ["postgres", "opa"]
        monkeypatch.setattr(campaign.db, "fetch_one", lambda *a, **k: {"ok": 1})
        monkeypatch.setattr(campaign, "_http_ok", lambda url: True)
        assert campaign.check_health(Settings(_env_file=None)) == []

    def test_check_health_bounds_a_hanging_db_call(self, monkeypatch):
        """A real incident: db.fetch_one blocked 2+h with Postgres down, freezing health checks."""
        monkeypatch.setattr(campaign, "_HEALTH_DB_TIMEOUT_S", 0.05)
        monkeypatch.setattr(campaign.db, "fetch_one", lambda *a, **k: threading.Event().wait(30))
        monkeypatch.setattr(campaign, "_http_ok", lambda url: True)
        started = time.monotonic()
        assert campaign.check_health(Settings(_env_file=None)) == ["postgres"]
        assert time.monotonic() - started < 2.0  # bounded, not the 30s stall

    def test_http_ok(self, monkeypatch):
        class Resp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(campaign.urllib.request, "urlopen", lambda *a, **k: Resp())
        assert campaign._http_ok("http://x")

        def boom(*a, **k):
            raise OSError("refused")

        monkeypatch.setattr(campaign.urllib.request, "urlopen", boom)
        assert not campaign._http_ok("http://x")

    @pytest.mark.parametrize(("rc", "expected"), [(0, False), (1, True), (128, False)])
    def test_code_changed_since(self, monkeypatch, rc, expected):
        monkeypatch.setattr(
            campaign.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, rc)
        )
        assert campaign.code_changed_since("abc") is expected

    def test_code_changed_since_survives_missing_git(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("no git")

        monkeypatch.setattr(campaign.subprocess, "run", boom)
        assert campaign.code_changed_since("abc") is False

    def test_spawn_runner_builds_one_run_command_with_mode_env(self, tmp_path, monkeypatch):
        seen = {}

        def fake_run(cmd, env, stdout, stderr, timeout, check):
            seen.update(cmd=cmd, env=env, timeout=timeout)
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(campaign.subprocess, "run", fake_run)
        arm = Arm("a", tmp_path / "d", frozenset({"full", "baseline"}), True, "paper")
        assert campaign.spawn_runner(arm, 99.0, tmp_path / "log" / "c.log") == 0
        assert seen["cmd"][-2:] == ["--max-runs", "1"]
        assert "baseline,full" in seen["cmd"] and seen["env"]["MOCK_LLM"] == "0"
        mock_arm = Arm("b", tmp_path / "d", frozenset({"full"}), False, "paper")
        campaign.spawn_runner(mock_arm, 99.0, tmp_path / "c.log")
        assert seen["env"]["MOCK_LLM"] == "1"

    def test_spawn_runner_maps_timeout_to_124(self, tmp_path, monkeypatch):
        def hang(*a, **k):
            raise subprocess.TimeoutExpired("x", 1)

        monkeypatch.setattr(campaign.subprocess, "run", hang)
        arm = Arm("a", tmp_path, frozenset({"full"}), True, "paper")
        assert campaign.spawn_runner(arm, 1.0, tmp_path / "c.log") == 124
