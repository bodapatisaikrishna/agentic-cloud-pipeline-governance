"""Unit tests for bounded adaptation (mocked db + settings)."""

from unittest.mock import MagicMock

from acde.agents import adaptation
from acde.config import Settings


def test_success_prior_neutral_without_history(monkeypatch):
    fake = MagicMock()
    fake.fetch_one.return_value = {"n": 0, "ok": 0}
    monkeypatch.setattr(adaptation, "db", fake)
    assert adaptation.success_prior("schema_drift", "quarantine_partition") == 0.5


def test_success_prior_ratio(monkeypatch):
    fake = MagicMock()
    fake.fetch_one.return_value = {"n": 4, "ok": 3}
    monkeypatch.setattr(adaptation, "db", fake)
    assert adaptation.success_prior("upstream_delay", "replay") == 0.75


def test_blend_is_bounded(monkeypatch):
    monkeypatch.setattr(
        adaptation,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            adaptation_weight=0.3,
            adaptation_min_confidence=0.1,
            adaptation_max_confidence=0.99,
        ),
    )
    # a zero prior cannot suppress below the clamp; a perfect prior cannot exceed the ceiling
    assert adaptation.blend_confidence(0.2, 0.0) >= 0.1
    assert adaptation.blend_confidence(1.0, 1.0) <= 0.99
    # a middling blend moves toward the prior
    assert 0.5 < adaptation.blend_confidence(0.5, 1.0) < 0.99


def test_disabled_is_identity(monkeypatch):
    monkeypatch.setattr(
        adaptation, "get_settings", lambda: Settings(_env_file=None, adaptation_enabled=False)
    )
    assert adaptation.adapt_confidence("schema_drift", "quarantine_partition", 0.42) == 0.42
