"""Unit tests for the in-process request-rate limiter (D-098)."""

from acde.server.ratelimit import RateLimiter, reset_total_rate_limited, total_rate_limited


class TestRateLimiter:
    def test_disabled_by_default_always_allows(self):
        limiter = RateLimiter(limit_per_minute=0)
        for _ in range(1000):
            allowed, _ = limiter.check("actor")
            assert allowed is True

    def test_allows_up_to_the_limit_then_rejects(self):
        limiter = RateLimiter(limit_per_minute=3)
        results = [limiter.check("actor")[0] for _ in range(4)]
        assert results == [True, True, True, False]

    def test_rejection_carries_a_positive_retry_after(self):
        limiter = RateLimiter(limit_per_minute=1, window_s=60.0)
        limiter.check("actor")
        allowed, retry_after = limiter.check("actor")
        assert allowed is False
        assert retry_after > 0

    def test_distinct_keys_have_independent_budgets(self):
        limiter = RateLimiter(limit_per_minute=1)
        assert limiter.check("alice")[0] is True
        assert limiter.check("bob")[0] is True  # bob's budget untouched by alice's request
        assert limiter.check("alice")[0] is False
        assert limiter.check("bob")[0] is False

    def test_window_resets_after_it_elapses(self, monkeypatch):
        import acde.server.ratelimit as ratelimit_mod

        fake_now = [1000.0]
        monkeypatch.setattr(ratelimit_mod.time, "monotonic", lambda: fake_now[0])
        limiter = RateLimiter(limit_per_minute=1, window_s=60.0)
        assert limiter.check("actor")[0] is True
        assert limiter.check("actor")[0] is False  # still within the window
        fake_now[0] += 61.0  # past the window
        assert limiter.check("actor")[0] is True  # mutation-test proof: a stuck window would 429

    def test_reset_clears_all_window_state(self):
        limiter = RateLimiter(limit_per_minute=1)
        limiter.check("actor")
        assert limiter.check("actor")[0] is False
        limiter.reset()
        assert limiter.check("actor")[0] is True


class TestTotalRateLimited:
    def test_increments_only_on_rejection(self):
        reset_total_rate_limited()
        limiter = RateLimiter(limit_per_minute=1)
        limiter.check("actor")  # allowed -- must not increment
        assert total_rate_limited() == 0
        limiter.check("actor")  # rejected -- must increment
        assert total_rate_limited() == 1
        reset_total_rate_limited()
