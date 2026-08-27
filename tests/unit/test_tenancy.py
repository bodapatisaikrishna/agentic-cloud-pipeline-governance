"""Unit tests for the tenant/environment scope resolver (D-085)."""

from acde.config import Settings
from acde.tenancy import current_scope


def test_defaults_to_default_default(monkeypatch):
    import acde.tenancy as tenancy_mod

    monkeypatch.setattr(tenancy_mod, "get_settings", lambda: Settings(_env_file=None))
    assert current_scope() == ("default", "default")


def test_reads_configured_values(monkeypatch):
    import acde.tenancy as tenancy_mod

    monkeypatch.setattr(
        tenancy_mod,
        "get_settings",
        lambda: Settings(_env_file=None, tenant_id="acme", environment="prod"),
    )
    assert current_scope() == ("acme", "prod")
