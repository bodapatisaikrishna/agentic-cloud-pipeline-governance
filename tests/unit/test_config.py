"""Unit tests for Settings (config.py)."""

from acde.config import Settings, get_settings


def _fresh(monkeypatch, **env) -> Settings:
    """Build Settings from a controlled environment, ignoring any local .env."""
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)


class TestDefaults:
    def test_mock_llm_defaults_on(self):
        assert Settings(_env_file=None).mock_llm is True

    def test_cost_model_constants_match_spec(self):
        s = Settings(_env_file=None)
        assert s.cost_rate_compute_unit_second == 0.05
        assert s.cost_rate_storage_gb_hour == 0.01

    def test_budget_caps_match_spec(self):
        s = Settings(_env_file=None)
        assert s.llm_max_calls_per_run == 60
        assert s.llm_max_tokens_per_run == 150_000

    def test_freshness_sla(self):
        assert Settings(_env_file=None).freshness_sla_streaming_s == 60.0

    def test_dsn_assembled_from_parts(self):
        dsn = Settings(_env_file=None).postgres_dsn
        assert "host=localhost" in dsn
        assert "dbname=acde" in dsn


class TestEnvOverrides:
    def test_env_vars_override_defaults(self, monkeypatch):
        s = _fresh(
            monkeypatch,
            POSTGRES_HOST="db.internal",
            MOCK_LLM="0",
            MODEL_REASONING="claude-x",
            LLM_MAX_CALLS_PER_RUN="5",
        )
        assert s.postgres_host == "db.internal"
        assert s.mock_llm is False
        assert s.model_reasoning == "claude-x"
        assert s.llm_max_calls_per_run == 5

    def test_get_settings_is_cached_singleton(self):
        get_settings.cache_clear()
        assert get_settings() is get_settings()
        get_settings.cache_clear()


class TestApiKeyMap:
    def test_empty_when_nothing_configured(self):
        assert Settings(_env_file=None, api_key="", api_keys="").api_key_map == {}

    def test_legacy_single_key_maps_to_operator(self):
        s = Settings(_env_file=None, api_key="secret", api_keys="")
        assert s.api_key_map == {"operator": "secret"}

    def test_multi_key_csv_parses_each_pair(self):
        s = Settings(_env_file=None, api_key="", api_keys="alice:key1, bob:key2")
        assert s.api_key_map == {"alice": "key1", "bob": "key2"}

    def test_legacy_and_multi_merge(self):
        s = Settings(_env_file=None, api_key="opkey", api_keys="alice:key1")
        assert s.api_key_map == {"operator": "opkey", "alice": "key1"}

    def test_malformed_pairs_are_skipped(self):
        s = Settings(_env_file=None, api_key="", api_keys="alice:key1, no-colon-here, :novalue")
        assert s.api_key_map == {"alice": "key1"}

    def test_key_extraction_unaffected_by_an_optional_role_field(self):
        # actor:key:role must still yield the right key, not "key:role" or "key" truncated wrong.
        s = Settings(_env_file=None, api_key="", api_keys="alice:key1:viewer,bob:key2")
        assert s.api_key_map == {"alice": "key1", "bob": "key2"}


class TestRoleMap:
    """D-093."""

    def test_empty_when_nothing_configured(self):
        assert Settings(_env_file=None, api_key="", api_keys="").role_map == {}

    def test_legacy_single_key_defaults_to_admin(self):
        s = Settings(_env_file=None, api_key="secret", api_keys="")
        assert s.role_map == {"operator": "admin"}

    def test_explicit_role_is_read(self):
        s = Settings(_env_file=None, api_key="", api_keys="alice:key1:viewer,bob:key2:approver")
        assert s.role_map == {"alice": "viewer", "bob": "approver"}

    def test_missing_role_on_a_multi_key_actor_defaults_to_admin(self):
        # every deployment that already has api_keys configured today has no role syntax at all --
        # this must not silently downgrade anyone's access on upgrade.
        s = Settings(_env_file=None, api_key="", api_keys="alice:key1")
        assert s.role_map == {"alice": "admin"}
