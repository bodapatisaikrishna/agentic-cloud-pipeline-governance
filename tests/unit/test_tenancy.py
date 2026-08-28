"""Unit tests for the tenant registry (D-097) -- mocked db."""

from unittest.mock import MagicMock

import pytest

from acde import tenancy


class TestCreateTenant:
    def test_inserts_and_returns_the_new_row(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_one.side_effect = [
            None,  # get_tenant's pre-check: no existing row
            {
                "tenant_id": "acme",
                "display_name": "Acme Inc",
                "status": "active",
                "created_ts": "t",
            },
        ]
        monkeypatch.setattr(tenancy, "db", fake)
        t = tenancy.create_tenant("acme", "Acme Inc")
        assert t["tenant_id"] == "acme"
        assert t["status"] == "active"

    def test_raises_on_duplicate_tenant_id(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_one.return_value = {
            "tenant_id": "acme",
            "display_name": "Acme Inc",
            "status": "active",
            "created_ts": "t",
        }
        monkeypatch.setattr(tenancy, "db", fake)
        with pytest.raises(ValueError, match="already exists"):
            tenancy.create_tenant("acme", "Acme Inc Again")
        # mutation-test proof this check matters: no INSERT was ever attempted after the duplicate
        # was found -- fetch_one was called exactly once (the pre-check), not twice.
        assert fake.fetch_one.call_count == 1


class TestListTenants:
    def test_returns_all_rows(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_all.return_value = [
            {"tenant_id": "default", "display_name": "Default Tenant", "status": "active"},
            {"tenant_id": "acme", "display_name": "Acme Inc", "status": "suspended"},
        ]
        monkeypatch.setattr(tenancy, "db", fake)
        rows = tenancy.list_tenants()
        assert [r["tenant_id"] for r in rows] == ["default", "acme"]


class TestGetTenant:
    def test_returns_none_for_unknown_tenant(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_one.return_value = None
        monkeypatch.setattr(tenancy, "db", fake)
        assert tenancy.get_tenant("nope") is None

    def test_returns_the_row_for_a_known_tenant(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_one.return_value = {
            "tenant_id": "acme",
            "display_name": "Acme Inc",
            "status": "active",
            "created_ts": "t",
        }
        monkeypatch.setattr(tenancy, "db", fake)
        t = tenancy.get_tenant("acme")
        assert t is not None
        assert t["status"] == "active"


class TestSetTenantStatus:
    def test_suspends_a_known_tenant(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_one.return_value = {
            "tenant_id": "acme",
            "display_name": "Acme Inc",
            "status": "suspended",
            "created_ts": "t",
        }
        monkeypatch.setattr(tenancy, "db", fake)
        t = tenancy.set_tenant_status("acme", "suspended")
        assert t["status"] == "suspended"

    def test_raises_for_unknown_tenant(self, monkeypatch):
        fake = MagicMock()
        fake.fetch_one.return_value = None
        monkeypatch.setattr(tenancy, "db", fake)
        with pytest.raises(ValueError, match="no such tenant"):
            tenancy.set_tenant_status("nope", "active")

    def test_raises_for_invalid_status_without_touching_the_db(self, monkeypatch):
        fake = MagicMock()
        monkeypatch.setattr(tenancy, "db", fake)
        with pytest.raises(ValueError, match="status must be one of"):
            tenancy.set_tenant_status("acme", "deleted")
        # mutation-test proof the validation runs before any query -- not just that it raises.
        fake.fetch_one.assert_not_called()


class TestCurrentScope:
    def test_defaults_to_default_default(self, monkeypatch):
        from acde.config import Settings

        monkeypatch.setattr(tenancy, "get_settings", lambda: Settings(_env_file=None))
        assert tenancy.current_scope() == ("default", "default")

    def test_unchanged_process_wide_default(self, monkeypatch):
        from acde.config import Settings

        monkeypatch.setattr(
            tenancy,
            "get_settings",
            lambda: Settings(_env_file=None, tenant_id="t1", environment="e1"),
        )
        assert tenancy.current_scope() == ("t1", "e1")
