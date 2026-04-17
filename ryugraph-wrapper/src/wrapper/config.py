"""Configuration management using pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WrapperConfig(BaseSettings):
    """Core wrapper configuration."""

    model_config = SettingsConfigDict(
        env_prefix="WRAPPER_",
        env_file=".env",
        extra="ignore",
    )

    # Instance identification (empty = standalone/canary mode — no control-plane registration)
    instance_id: str = Field(default="", description="Unique instance identifier (UUID)")
    url_slug: str = Field(default="", description="URL slug for external routing (used by authorize)")
    snapshot_id: str = Field(default="", description="Source snapshot identifier (UUID)")
    mapping_id: str = Field(default="", description="Parent mapping identifier (UUID)")
    owner_id: str = Field(default="", description="Instance owner user identifier")
    owner_username: str = Field(default="unknown", description="Instance owner username")

    # Kubernetes pod identification (set via Downward API)
    pod_name: str | None = Field(default=None, description="Kubernetes pod name")
    pod_ip: str | None = Field(default=None, description="Kubernetes pod IP address")

    # Instance URL (set by control plane when spawning dynamic instances)
    instance_url: str | None = Field(default=None, description="URL for SDK to reach this instance")

    # Networking
    host: str = Field(default="0.0.0.0", description="Host to bind to")
    port: int = Field(default=8000, ge=1, le=65535, description="Port to bind to")

    # Control Plane
    control_plane_url: str = Field(description="Control Plane API base URL")
    control_plane_timeout: float = Field(default=30.0, ge=1.0, description="HTTP timeout seconds")

    # GCS (empty = standalone/canary mode)
    gcs_base_path: str = Field(default="", description="GCS path to snapshot Parquet files")

    @field_validator("gcs_base_path")
    @classmethod
    def validate_gcs_path(cls, v: str) -> str:
        """Ensure GCS path starts with gs:// (skip validation in standalone mode)."""
        if not v:
            return v
        if not v.startswith("gs://"):
            raise ValueError("gcs_base_path must start with 'gs://'")
        return v.rstrip("/")


class InternalAuthConfig(BaseSettings):
    """Internal service authentication configuration."""

    model_config = SettingsConfigDict(
        env_prefix="GRAPH_OLAP_",
        env_file=".env",
        extra="ignore",
    )

    internal_api_key: str | None = Field(
        default=None,
        description="API key for internal service-to-service auth (X-Internal-API-Key header)",
    )


class RyugraphConfig(BaseSettings):
    """Ryugraph database configuration."""

    model_config = SettingsConfigDict(
        env_prefix="RYUGRAPH_",
        env_file=".env",
        extra="ignore",
    )

    # Database paths
    # Canonical default per ADR-149 Tier-B.10: wrapper_factory.py spawn-time
    # defaults are the source of truth. The actual spawn path (set by
    # k8s_service._build_wrapper_pod_spec in the RYUGRAPH_DATABASE_PATH env var)
    # is /data/db. The Dockerfile and README also use /data/db. Keeping this
    # in sync avoids silent path divergence in standalone/canary mode.
    database_path: Path = Field(
        default=Path("/data/db"),
        description="Path to Ryugraph database directory",
    )

    # Performance tuning (see ryugraph-performance.reference.md)
    buffer_pool_size: int = Field(
        default=2_147_483_648,  # 2GB
        ge=134_217_728,  # 128MB minimum
        description="Buffer pool size in bytes",
    )
    max_threads: int = Field(
        default=16,  # 4x CPU for I/O-bound GCS reads
        ge=1,
        le=64,
        description="Maximum threads for parallel operations",
    )

    # Timeouts
    query_timeout_ms: int = Field(
        default=60_000,  # 60 seconds
        ge=1_000,
        description="Default query timeout in milliseconds",
    )
    algorithm_timeout_ms: int = Field(
        default=1_800_000,  # 30 minutes
        ge=60_000,
        description="Default algorithm timeout in milliseconds",
    )


class MetricsConfig(BaseSettings):
    """Metrics reporting configuration."""

    model_config = SettingsConfigDict(
        env_prefix="METRICS_",
        env_file=".env",
        extra="ignore",
    )

    # Reporting intervals
    report_interval_seconds: int = Field(
        default=60,
        ge=10,
        description="How often to report metrics to Control Plane",
    )
    enabled: bool = Field(default=True, description="Enable metrics reporting")


class LoggingConfig(BaseSettings):
    """Logging configuration."""

    model_config = SettingsConfigDict(
        env_prefix="LOG_",
        env_file=".env",
        extra="ignore",
    )

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Log level",
    )
    format: Literal["json", "console"] = Field(
        default="json",
        description="Log format (json for production, console for local dev)",
    )
    include_timestamps: bool = Field(
        default=True,
        description="Include timestamps in log output",
    )


class Settings(BaseSettings):
    """Aggregated settings for the wrapper."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    wrapper: WrapperConfig = Field(default_factory=WrapperConfig)
    ryugraph: RyugraphConfig = Field(default_factory=RyugraphConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    internal_auth: InternalAuthConfig = Field(default_factory=InternalAuthConfig)

    # Environment
    environment: Literal["local", "dev", "staging", "prod"] = Field(
        default="local",
        description="Deployment environment",
    )
    debug: bool = Field(default=False, description="Enable debug mode")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings singleton.

    Returns:
        Settings: Application settings loaded from environment.
    """
    return Settings()
