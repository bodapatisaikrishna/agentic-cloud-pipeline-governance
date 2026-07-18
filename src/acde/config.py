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
    # bounded retry for Airflow-REST side effects before the executor degrades to escalate (D-052)
    executor_retry_attempts: int = 3
    executor_retry_backoff_s: float = 0.5

    # --- Streaming broker (Redpanda) ---
    broker_bootstrap: str = "localhost:9092"
    stream_topic: str = "acde.stream.events"
    stream_default_workers: int = 2
    stream_min_workers: int = 1
    stream_max_workers: int = 8
    stream_window_s: float = 60.0  # tumbling-window width

    # --- Datasets (Phase 1) ---
    data_dir: str = "data"
    tpcds_scale_rows: int = 20_000  # downscaled synthetic SF1 fact-row count
    opengov_rows: int = 5_000
    use_real_tlc: bool = False  # opt-in: download real NYC TLC parquet
    use_real_opengov: bool = False  # opt-in: fetch a real open-gov CSV

    # --- Policy engine ---
    opa_url: str = "http://localhost:8181"

    # --- Airflow REST API (Phase 1+) ---
    airflow_url: str = "http://localhost:8080/api/v1"
    airflow_user: str = "admin"
    airflow_password: str = "admin"

    # --- LLM layer ---
    # Live-call provider: "anthropic" (default) or "gemini" (D-056). Ignored under MOCK_LLM.
    llm_provider: str = "anthropic"
    anthropic_api_key: str = ""
    model_reasoning: str = "claude-sonnet-4-6"
    model_fast: str = "claude-haiku-4-5"
    # Gemini live provider (opt-in; key + models via .env). IDs are overridable if they change.
    gemini_api_key: str = ""
    gemini_model_reasoning: str = "gemini-2.5-pro"
    gemini_model_fast: str = "gemini-2.5-flash"
    # Generic OpenAI-compatible provider (NVIDIA NIM / Groq / OpenRouter / z.ai) — D-057.
    # Larger per-call cap so "thinking" models (e.g. GLM-5.2) can reach the JSON.
    oai_base_url: str = "https://integrate.api.nvidia.com/v1"
    oai_api_key: str = ""
    oai_model_reasoning: str = "z-ai/glm-5.2"
    oai_model_fast: str = "meta/llama-3.1-8b-instruct"
    oai_max_tokens_per_call: int = 8192
    mock_llm: bool = True  # default everywhere; live runs must opt out explicitly
    llm_max_calls_per_run: int = 60
    llm_max_tokens_per_run: int = 150_000
    llm_max_tokens_per_call: int = 1024

    # --- Cost model (§5.5, disclosed in README/DEVIATIONS) ---
    cost_rate_compute_unit_second: float = 0.05
    cost_rate_storage_gb_hour: float = 0.01

    # --- SLAs ---
    freshness_sla_streaming_s: float = 60.0

    # --- Policy plane ---
    budget_default_units: float = 100.0  # per-run cost budget the cost policy checks against
    rate_limit_max_per_10min: int = 5  # runaway-loop guard (mirrors rate_limit.rego)

    # --- Human simulator (§6 baseline) ---
    human_latency_median_s: float = 360.0
    human_latency_sigma: float = 0.5

    # --- Non-agent baselines (Phase A credibility) ---
    # Rule-based automation resolves faults it has a predefined rule for at a fixed remediation
    # latency; autoscaling reacts to resource pressure only. Faults outside coverage escalate to
    # the human. Both are stronger baselines than the raw human (DEVIATIONS D-058).
    rule_remediation_s: float = 30.0
    autoscale_reaction_s: float = 20.0

    # --- Cost model v2: provisioning (Phase B, D-061) ---
    # Static configs hold a fixed over-provisioned allocation; dynamically-scaling configs
    # (autoscale + optimization agent) right-size to actual load. Provisioning cost is charged over
    # a fixed horizon so it is comparable across profiles (independent of compressed run timings).
    provisioned_units_static: float = 8.0
    provisioned_units_rightsized: float = 3.0
    provisioning_horizon_s: float = 300.0

    # --- Agents / anomaly detection (§5.6) ---
    anomaly_z_threshold: float = 3.0  # z-score above which a metric point is anomalous
    cpu_high_pct: float = 80.0  # resource-contention detection threshold
    agent_min_confidence: float = 0.0  # proposals below this are downgraded to no_action

    # --- Orchestrator (§8 Phase 6) ---
    monitoring_interval_s: float = 15.0  # control-loop tick period
    soak_duration_s: float = 1200.0  # 20-min soak (manual checklist)

    # --- Experiments (§8 Phase 7) ---
    results_dir: str = "results"  # git-ignored raw.csv + manifest.jsonl land here

    # --- Analysis (§8 Phase 8) ---
    bootstrap_resamples: int = 10000
    paper_mttr_pct: float = 45.0  # paper's claimed MTTR reduction (full vs baseline)
    paper_cost_pct: float = 25.0  # paper's claimed operational-cost reduction
    paper_intervention_pct: float = 70.0  # paper's claimed manual-intervention reduction

    # --- Chaos harness (§6/§8 Phase 4) ---
    chaos_warmup_s: float = 120.0
    chaos_fault_window_s: float = 180.0
    chaos_recovery_s: float = 120.0
    chaos_hard_cap_s: float = 720.0
    chaos_burst_min: float = 5.0
    chaos_burst_max: float = 10.0
    chaos_delay_ms_max: int = 5000
    chaos_drop_pct_max: float = 0.5
    chaos_cpu_workers_max: int = 4
    stress_use_container: bool = False
    stress_image: str = "ghcr.io/colinianking/stress-ng:latest"

    # --- Telemetry ---
    experiment_run: str = "adhoc"  # tags every telemetry row; overridden by the runner (P7)
    telemetry_interval_s: float = 5.0  # collector sampling period
    cost_window_s: float = 60.0  # cost-ledger aggregation window

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
