"""Ops-related models for config and cluster endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class ResourceLifecycleConfig:
    """Lifecycle configuration for a resource type."""

    default_ttl: str | None = None
    default_inactivity: str | None = None
    max_ttl: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> ResourceLifecycleConfig:
        """Create from API response."""
        return cls(
            default_ttl=data.get("default_ttl"),
            default_inactivity=data.get("default_inactivity"),
            max_ttl=data.get("max_ttl"),
        )


@dataclass
class LifecycleConfig:
    """Full lifecycle configuration for all resource types."""

    mapping: ResourceLifecycleConfig
    snapshot: ResourceLifecycleConfig
    instance: ResourceLifecycleConfig

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> LifecycleConfig:
        """Create from API response."""
        return cls(
            mapping=ResourceLifecycleConfig.from_api_response(data.get("mapping", {})),
            snapshot=ResourceLifecycleConfig.from_api_response(data.get("snapshot", {})),
            instance=ResourceLifecycleConfig.from_api_response(data.get("instance", {})),
        )


@dataclass
class ConcurrencyConfig:
    """Concurrency limits configuration."""

    per_analyst: int
    cluster_total: int
    updated_at: datetime | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> ConcurrencyConfig:
        """Create from API response."""
        updated_at = None
        if data.get("updated_at"):
            updated_at = datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00"))
        return cls(
            per_analyst=data["per_analyst"],
            cluster_total=data["cluster_total"],
            updated_at=updated_at,
        )


@dataclass
class MaintenanceMode:
    """Maintenance mode status."""

    enabled: bool
    message: str
    updated_at: datetime | None = None
    updated_by: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> MaintenanceMode:
        """Create from API response."""
        updated_at = None
        if data.get("updated_at"):
            updated_at = datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00"))
        return cls(
            enabled=data["enabled"],
            message=data.get("message", ""),
            updated_at=updated_at,
            updated_by=data.get("updated_by"),
        )


@dataclass
class ExportConfig:
    """Export configuration."""

    max_duration_seconds: int
    updated_at: datetime | None = None
    updated_by: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> ExportConfig:
        """Create from API response."""
        updated_at = None
        if data.get("updated_at"):
            updated_at = datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00"))
        return cls(
            max_duration_seconds=data["max_duration_seconds"],
            updated_at=updated_at,
            updated_by=data.get("updated_by"),
        )


@dataclass
class ComponentHealth:
    """Health status of a single component."""

    status: str
    latency_ms: int | None = None
    error: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> ComponentHealth:
        """Create from API response."""
        return cls(
            status=data["status"],
            latency_ms=data.get("latency_ms"),
            error=data.get("error"),
        )


@dataclass
class ClusterHealth:
    """Cluster health status."""

    status: str  # healthy, degraded, unhealthy
    components: dict[str, ComponentHealth]
    checked_at: datetime

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> ClusterHealth:
        """Create from API response."""
        checked_at = datetime.fromisoformat(data["checked_at"].replace("Z", "+00:00"))
        components = {
            name: ComponentHealth.from_api_response(comp)
            for name, comp in data.get("components", {}).items()
        }
        return cls(
            status=data["status"],
            components=components,
            checked_at=checked_at,
        )


@dataclass
class OwnerInstanceCount:
    """Instance count by owner."""

    owner_username: str
    count: int

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> OwnerInstanceCount:
        """Create from API response."""
        return cls(
            owner_username=data["owner_username"],
            count=data["count"],
        )


@dataclass
class InstanceLimits:
    """Instance limits."""

    per_analyst: int
    cluster_total: int
    cluster_used: int
    cluster_available: int

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> InstanceLimits:
        """Create from API response."""
        return cls(
            per_analyst=data["per_analyst"],
            cluster_total=data["cluster_total"],
            cluster_used=data["cluster_used"],
            cluster_available=data["cluster_available"],
        )


@dataclass
class ClusterInstances:
    """Cluster-wide instance summary."""

    total: int
    by_status: dict[str, int]
    by_owner: list[OwnerInstanceCount]
    limits: InstanceLimits

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> ClusterInstances:
        """Create from API response."""
        return cls(
            total=data["total"],
            by_status=data.get("by_status", {}),
            by_owner=[
                OwnerInstanceCount.from_api_response(o) for o in data.get("by_owner", [])
            ],
            limits=InstanceLimits.from_api_response(data["limits"]),
        )


@dataclass
class HealthStatus:
    """Simple health status response."""

    status: str
    version: str | None = None
    database: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> HealthStatus:
        """Create from API response."""
        return cls(
            status=data["status"],
            version=data.get("version"),
            database=data.get("database"),
        )
