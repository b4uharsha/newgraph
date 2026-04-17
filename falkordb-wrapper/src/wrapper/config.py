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


class FalkorDBConfig(BaseSettings):
    """FalkorDB database configuration."""

    model_config = SettingsConfigDict(
        env_prefix="FALKORDB_",
        env_file=".env",
        extra="ignore",
    )

    # Database paths
    database_path: Path = Field(
        default=Path("/data/db"),
        description="Path to FalkorDB database directory",
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
    format: Literal["json", "human"] = Field(
        default="json",
        description="Log format (json for production, human for development)",
    )


class Settings(BaseSettings):
    """Root settings object combining all config sections."""

    wrapper: WrapperConfig
    auth: InternalAuthConfig = InternalAuthConfig()
    falkordb: FalkorDBConfig = FalkorDBConfig()
    metrics: MetricsConfig = MetricsConfig()
    logging: LoggingConfig = LoggingConfig()

    # Environment
    environment: Literal["dev", "staging", "production"] = Field(
        default="production",
        description="Deployment environment",
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings(wrapper=WrapperConfig())
