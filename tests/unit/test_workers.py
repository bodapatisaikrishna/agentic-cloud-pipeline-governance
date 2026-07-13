"""Unit tests for the worker-pool resize decision + async pool."""

import asyncio
from unittest.mock import MagicMock

import pytest

from acde.dataplane.streaming import workers
from acde.dataplane.streaming.workers import WorkerPool, clamp_workers, resize_plan


class TestResizeDecision:
    @pytest.mark.parametrize(("desired", "expected"), [(-1, 1), (0, 1), (4, 4), (8, 8), (99, 8)])
    def test_clamp(self, desired, expected):
        assert clamp_workers(desired, 1, 8) == expected

    def test_resize_plan_scale_up(self):
        assert resize_plan(current=2, desired=5, lo=1, hi=8) == (5, 3, 0)

    def test_resize_plan_scale_down(self):
        assert resize_plan(current=6, desired=2, lo=1, hi=8) == (2, 0, 4)

    def test_resize_plan_clamps_desired(self):
        assert resize_plan(current=1, desired=99, lo=1, hi=8) == (8, 7, 0)


class TestReadDesiredWorkers:
    def test_reads_json_value(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_one.return_value = {"value": {"n": 4}}
        monkeypatch.setattr(workers, "db", fake)
        assert workers.read_desired_workers(default=2) == 4

    def test_parses_string_json(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_one.return_value = {"value": '{"n": 6}'}
        monkeypatch.setattr(workers, "db", fake)
        assert workers.read_desired_workers(default=2) == 6

    def test_falls_back_when_absent(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_one.return_value = None
        monkeypatch.setattr(workers, "db", fake)
        assert workers.read_desired_workers(default=3) == 3


class TestWorkerPool:
    async def _idle_worker(self, index, stop):
        await stop.wait()

    def test_resize_grows_and_shrinks(self):
        async def scenario():
            pool = WorkerPool(self._idle_worker, lo=1, hi=8)
            await pool.resize(3)
            assert pool.size() == 3
            await pool.resize(5)
            assert pool.size() == 5
            await pool.resize(2)
            assert pool.size() == 2
            await pool.shutdown()
            assert pool.size() == 0

        asyncio.run(scenario())

    def test_resize_respects_bounds(self):
        async def scenario():
            pool = WorkerPool(self._idle_worker, lo=1, hi=4)
            await pool.resize(99)
            assert pool.size() == 4
            await pool.resize(0)  # clamped up to lo
            assert pool.size() == 1
            await pool.shutdown()

        asyncio.run(scenario())
