"""Central configuration for ACDE.

Every environment-dependent knob lives here (Rule: no config literals scattered
in code). Values come from environment variables or a git-ignored ``.env`` file;
see ``.env.example`` for the full catalogue.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All ACDE configuration, loaded from the environment / ``.env``."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Postgres (telemetry / warehouse / control schemas) ---
    postgres_host: str = "localhost"
    postgres_port: int = 5433  # host-published port; 5433 avoids clashing with a local pg on 5432
    postgres_user: str = "acde"
    postgres_password: str = "acde"
    postgres_db: str = "acde"
    db_pool_min_size: int = 1
    db_pool_max_size: int = 8
    db_retry_attempts: int = 3
    db_retry_backoff_s: float = 0.5

    # --- Streaming broker (Redpanda, Phase 1) ---
    broker_bootstrap: str = "localhost:9092"

    # --- Policy engine ---
    opa_url: str = "http://localhost:8181"

    # --- Airflow REST API (Phase 1+) ---
    airflow_url: str = "http://localhost:8080/api/v1"
    airflow_user: str = "admin"
    airflow_password: str = "admin"

    # --- LLM layer ---
    anthropic_api_key: str = ""
    model_reasoning: str = "claude-sonnet-4-6"
    model_fast: str = "claude-haiku-4-5"
    mock_llm: bool = True  # default everywhere; live runs must opt out explicitly
    llm_max_calls_per_run: int = 60
    llm_max_tokens_per_run: int = 150_000
    llm_max_tokens_per_call: int = 1024

    # --- Cost model (§5.5, disclosed in README/DEVIATIONS) ---
    cost_rate_compute_unit_second: float = 0.05
    cost_rate_storage_gb_hour: float = 0.01

    # --- SLAs ---
    freshness_sla_streaming_s: float = 60.0

    # --- Determinism ---
    default_seed: int = 42

    # --- Logging ---
    log_level: str = "INFO"

    @property
    def postgres_dsn(self) -> str:
        """libpq connection string for the ACDE database."""
        return (
            f"host={self.postgres_host} port={self.postgres_port} "
            f"user={self.postgres_user} password={self.postgres_password} "
            f"dbname={self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings singleton (cached)."""
    return Settings()
