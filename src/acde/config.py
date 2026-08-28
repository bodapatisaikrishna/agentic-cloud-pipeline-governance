"""Central configuration for ACDE.

Every environment-dependent knob lives here (Rule: no config literals scattered
in code). Values come from environment variables or a git-ignored ``.env`` file;
see ``.env.example`` for the full catalogue.
"""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All ACDE configuration, loaded from the environment / ``.env``."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Tenancy (D-085): server-side only, never client-supplied. A single deployment is one
    # tenant/environment today (self-hosted, one Postgres) -- these columns exist on every scoped
    # telemetry table so a future shared-database multi-tenant deployment needs no further schema
    # change, without building the tenant-routing/auth machinery a real hosted SaaS would need now.
    tenant_id: str = "default"
    environment: str = "default"

    # --- Retention (D-086): off by default, so upgrading never silently deletes data. The audit
    # trail (agent_actions) is exempt on purpose -- it's the compliance record, not noise.
    retention_days: int = 0

    # --- Postgres (telemetry / warehouse / control schemas) ---
    postgres_host: str = "localhost"
    postgres_port: int = 5433  # host-published port; 5433 avoids clashing with a local pg on 5432
    postgres_user: str = "acde"
    postgres_password: SecretStr = SecretStr("acde")
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
    airflow_password: SecretStr = SecretStr("admin")
    airflow_auth_token: str = ""  # bearer token; used instead of basic auth when set (prod SSO)
    airflow_verify_tls: bool = True  # verify TLS certs on the customer's Airflow endpoint
    # Which orchestrator connector the runtime attaches to: "airflow" (their Airflow), "prefect"
    # (their Prefect Server/Cloud, T2.4), or "noop" (observe-only — propose + gate + log, never
    # act). See docs/CONNECTING.md (D-066, D-073).
    connector_kind: str = "airflow"
    # Prefect connector (T2.4): REST API base URL; api_key is optional (Prefect Cloud only — a
    # self-hosted Prefect Server typically has no auth by default).
    prefect_api_url: str = "http://localhost:4200/api"
    prefect_api_key: SecretStr = SecretStr("")
    # Whether the connected environment is production. Game-day/chaos refuses to run unless this is
    # False (a staging connector), so incident rehearsals never hit prod.
    connector_is_production: bool = True

    # --- LLM layer ---
    # Live-call provider: "anthropic" (default) or "gemini" (D-056). Ignored under MOCK_LLM.
    llm_provider: str = "anthropic"
    anthropic_api_key: SecretStr = SecretStr("")
    model_reasoning: str = "claude-sonnet-4-6"
    model_fast: str = "claude-haiku-4-5"
    # Gemini live provider (opt-in; key + models via .env). IDs are overridable if they change.
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model_reasoning: str = "gemini-2.5-pro"
    gemini_model_fast: str = "gemini-2.5-flash"
    # Generic OpenAI-compatible provider (NVIDIA NIM / Groq / OpenRouter / z.ai) — D-057.
    # Larger per-call cap so "thinking" models (e.g. GLM-5.2) can reach the JSON.
    oai_base_url: str = "https://integrate.api.nvidia.com/v1"
    oai_api_key: SecretStr = SecretStr("")
    oai_model_reasoning: str = "z-ai/glm-5.2"
    oai_model_fast: str = "nvidia/nemotron-3-nano-30b-a3b"
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

    # --- Bounded adaptation (Phase E, D-064) — off by default for a deterministic benchmark ---
    adaptation_enabled: bool = False
    adaptation_weight: float = 0.3  # how much logged outcomes move a proposal's confidence
    adaptation_min_confidence: float = 0.1
    adaptation_max_confidence: float = 0.99

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

    # --- Production trust core (v2, P1) ---
    # Execution mode: "shadow" (log, never touch the pipeline), "approval" (queue for human sign-off
    # before executing), "autonomous" (execute allowed actions). Code default stays autonomous for
    # the research benchmark's determinism; the prod env template ships ACDE_MODE=shadow and the
    # `acde run` entrypoint defaults to shadow when unset. See docs/OPERATIONS.md (D-065).
    acde_mode: str = "autonomous"
    # Allowed actions of these types always require human approval, even in autonomous mode (CSV of
    # action_types, e.g. "rollback,quarantine_partition,block_ingestion"). Empty = none.
    approval_required_action_types: str = ""
    # Outbound webhook for operator notifications (Slack-compatible JSON). Empty disables.
    webhook_url: str = ""
    webhook_events: str = "pending_approval,escalation,execution_failure"
    webhook_timeout_s: float = 5.0
    # Blast-radius cap: max executed (side-effecting) actions per target per hour (0 = unlimited).
    blast_radius_max_per_hour: int = 0
    # Operator API (acde.server): requires either api_key (single legacy key, resolves to actor
    # "operator") or api_keys (multi-user: "actor1:key1,actor2:key2") — at least one must be set,
    # or the API refuses to start, so it is never accidentally exposed unauthenticated. Accepted
    # via the X-API-Key header (JSON/CLI clients) or HTTP Basic (actor=username, key=password;
    # lets a browser hit the dashboard with a native credential prompt). TLS via reverse proxy.
    api_key: SecretStr = SecretStr("")
    api_keys: SecretStr = SecretStr("")
    api_host: str = "127.0.0.1"
    api_port: int = 8099

    @property
    def approval_required_set(self) -> set[str]:
        return {a.strip() for a in self.approval_required_action_types.split(",") if a.strip()}

    @property
    def webhook_event_set(self) -> set[str]:
        return {e.strip() for e in self.webhook_events.split(",") if e.strip()}

    @property
    def api_key_map(self) -> dict[str, str]:
        """actor -> key, merging the legacy ``api_key`` (actor "operator") with ``api_keys``.

        Unwraps ``SecretStr`` here, at the one point the raw value is actually needed (building
        the lookup table ``_authenticate`` compares against) — everywhere else the field stays
        wrapped, so a ``repr(settings)``, log line, or traceback can't print a live credential.
        """
        keys: dict[str, str] = {}
        api_key = self.api_key.get_secret_value()
        if api_key:
            keys["operator"] = api_key
        for pair in self.api_keys.get_secret_value().split(","):
            pair = pair.strip()
            if not pair or ":" not in pair:
                continue
            actor, _, rest = pair.partition(":")
            key = rest.partition(":")[0]  # drop an optional third :role field, role_map reads it
            actor, key = actor.strip(), key.strip()
            if actor and key:
                keys[actor] = key
        return keys

    @property
    def role_map(self) -> dict[str, str]:
        """actor -> role (D-093), from an optional third ``actor:key:role`` field. Missing role
        (including the legacy single ``api_key``, always actor "operator") defaults to
        ``"admin"`` — every existing deployment's current full-access behavior, unchanged, with no
        config edit required. Same "simplest defensible default, documented" pattern as D-057's
        provider default: an underspecified role for an already-configured actor should never
        silently downgrade that actor's access on upgrade.
        """
        roles: dict[str, str] = {}
        if self.api_key.get_secret_value():
            roles["operator"] = "admin"
        for pair in self.api_keys.get_secret_value().split(","):
            pair = pair.strip()
            if not pair or ":" not in pair:
                continue
            actor, _, rest = pair.partition(":")
            _key, _, role = rest.partition(":")
            actor = actor.strip()
            if actor:
                roles[actor] = role.strip() or "admin"
        return roles

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
            f"user={self.postgres_user} password={self.postgres_password.get_secret_value()} "
            f"dbname={self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings singleton (cached)."""
    return Settings()
