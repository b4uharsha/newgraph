"""Application configuration using Pydantic Settings."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="GRAPH_OLAP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False
    shutdown_timeout_seconds: int = 30

    # Database (PostgreSQL required - no SQLite support)
    # Must be set via GRAPH_OLAP_DATABASE_URL environment variable
    # Format: postgresql+asyncpg://user:pass@host:port/dbname
    database_url: str = ""
    db_pool_size: int = 25
    db_max_overflow: int = 5
    db_echo: bool = False

    # Kubernetes (optional for testing)
    k8s_namespace: str = "graph-instances"
    k8s_in_cluster: bool = True
    # Wrapper image must include explicit tag - no "latest" allowed for reproducibility
    # Example: "ryugraph-wrapper:sha-53f3800" or "gcr.io/graph-olap/ryugraph-wrapper:v1.2.3"
    wrapper_image: str = "ryugraph-wrapper:dev"  # Must be overridden in production
    # FalkorDB wrapper image - must include explicit tag for reproducibility
    falkordb_wrapper_image: str = "falkordb-wrapper:dev"  # Must be overridden in production
    # Image pull policy for wrapper pods: "IfNotPresent" (default/cloud), "Always", or "Never" (local E2E)
    wrapper_image_pull_policy: str = "IfNotPresent"
    storage_class: str = "standard"
    storage_emulator_host: str = ""  # For E2E tests with fake-gcs-server
    wrapper_service_account: str = ""  # K8s service account for wrapper pods (for Workload Identity)
    wrapper_gcp_secret: str = ""  # K8s secret name containing GCP credentials (for local dev, alternative to Workload Identity)

    # External access for wrapper instances
    # Base URL for external access to wrapper instances via Ingress
    # e.g., "http://localhost:8080" for k3d or "https://wrappers.example.com" for production
    wrapper_external_base_url: str = ""

    # Wrapper resource configuration
    # These can be overridden for different environments (local dev, demo, production)
    # Ryugraph wrapper resources (graph database with buffer pool)
    # These are defaults - override via GRAPH_OLAP_RYUGRAPH_* env vars or Helm values
    ryugraph_memory_request: str = "2Gi"
    ryugraph_memory_limit: str = "4Gi"
    ryugraph_cpu_request: str = "1"
    ryugraph_cpu_limit: str = "2"
    ryugraph_buffer_pool_size: str = "1073741824"  # 1GB

    # FalkorDB wrapper resources (in-memory graph database)
    # These are defaults - override via GRAPH_OLAP_FALKORDB_* env vars or Helm values
    falkordb_memory_request: str = "2Gi"
    falkordb_memory_limit: str = "4Gi"
    falkordb_cpu_request: str = "1"
    falkordb_cpu_limit: str = "2"

    # Dynamic resource sizing (auto-calculates memory/disk from snapshot size)
    sizing_enabled: bool = True
    sizing_falkordb_memory_multiplier: float = 2.0  # parquet_size * multiplier for in-memory graph
    sizing_ryugraph_memory_multiplier: float = 1.2  # parquet_size * multiplier for disk-based graph
    sizing_memory_headroom: float = 1.5  # additional headroom multiplier
    sizing_min_memory_gb: float = 2.0
    sizing_max_memory_gb: float = 32.0
    sizing_disk_multiplier: float = 1.2
    sizing_min_disk_gb: int = 10
    # Resource governance
    sizing_per_user_max_memory_gb: float = 64.0  # total memory across all user instances
    sizing_cluster_memory_soft_limit_gb: float = 256.0  # warn/block when total exceeds this
    sizing_max_resize_steps: int = 3  # max auto-upgrades per instance
    sizing_resize_cooldown_seconds: int = 300  # min time between resizes
    sizing_default_cpu_cores: int = 1  # default CPU cores (request=N, limit=N*2)

    # Concurrency limits (seeded to global_config on startup)
    concurrency_per_analyst: int = 10  # max instances per analyst
    concurrency_cluster_total: int = 50  # max instances cluster-wide

    # E2E Test Configuration - stored as comma-separated string
    # Env var: GRAPH_OLAP_E2E_TEST_USER_EMAILS_CSV
    e2e_test_user_emails_csv: str = Field(
        default="",
        description="Comma-separated email addresses of E2E test users for bulk cleanup",
    )

    @property
    def e2e_test_user_emails(self) -> list[str]:
        """Get E2E test user emails as list."""
        if not self.e2e_test_user_emails_csv:
            return []
        return [email.strip() for email in self.e2e_test_user_emails_csv.split(",") if email.strip()]

    # Starburst (optional for testing)
    starburst_url: str = ""
    starburst_catalog: str = "hsbc-244552-hkibishk-dev"  # Default for Starburst Galaxy BigQuery connector
    starburst_user: str = "admin"
    starburst_password: SecretStr = SecretStr("changeme")
    starburst_timeout_seconds: int = 60  # Default for Starburst Galaxy BigQuery connector
    starburst_role: str = ""  # Use case ID for SET ROLE (ADR-102)

    # GCS (optional for testing)
    gcp_project: str = ""  # GCP project ID for GCS operations
    gcs_bucket: str = ""
    gcs_emulator_host: str = ""

    # Background Jobs
    lifecycle_job_interval_seconds: int = 300
    reconciliation_job_interval_seconds: int = 300
    instance_orchestration_job_interval_seconds: int = 5
    schema_cache_job_interval_seconds: int = 86400

    # Internal API key removed (ADR-104/105). Internal endpoints are
    # protected by network policy, not by a shared secret.

    @property
    def async_database_url(self) -> str:
        """Get async-compatible database URL.

        Converts postgresql:// or postgresql+psycopg2:// to postgresql+asyncpg://.
        SQLite is not supported - PostgreSQL is required everywhere.
        """
        if not self.database_url:
            raise ValueError(
                "GRAPH_OLAP_DATABASE_URL environment variable is required. "
                "PostgreSQL is required - SQLite is not supported."
            )
        url = self.database_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql+psycopg2://"):
            return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
        if not url.startswith("postgresql+asyncpg://"):
            raise ValueError(
                f"Invalid database URL: {url}. "
                "Only PostgreSQL is supported (postgresql://, postgresql+asyncpg://, or postgresql+psycopg2://)"
            )
        return url


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
