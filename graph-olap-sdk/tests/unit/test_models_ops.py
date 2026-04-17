"""Unit tests for ops-related models."""

from __future__ import annotations

from graph_olap.models.ops import (
    ClusterHealth,
    ClusterInstances,
    ComponentHealth,
    ConcurrencyConfig,
    ExportConfig,
    HealthStatus,
    InstanceLimits,
    LifecycleConfig,
    MaintenanceMode,
    OwnerInstanceCount,
    ResourceLifecycleConfig,
)


class TestResourceLifecycleConfig:
    """Tests for ResourceLifecycleConfig model."""

    def test_from_api_response_full(self):
        """Test creating from complete API response."""
        data = {
            "default_ttl": "P7D",
            "default_inactivity": "PT24H",
            "max_ttl": "P30D",
        }

        config = ResourceLifecycleConfig.from_api_response(data)

        assert config.default_ttl == "P7D"
        assert config.default_inactivity == "PT24H"
        assert config.max_ttl == "P30D"

    def test_from_api_response_partial(self):
        """Test creating with missing optional fields."""
        data = {"default_ttl": "P7D"}

        config = ResourceLifecycleConfig.from_api_response(data)

        assert config.default_ttl == "P7D"
        assert config.default_inactivity is None
        assert config.max_ttl is None

    def test_from_api_response_empty(self):
        """Test creating from empty dict."""
        config = ResourceLifecycleConfig.from_api_response({})

        assert config.default_ttl is None
        assert config.default_inactivity is None
        assert config.max_ttl is None


class TestLifecycleConfig:
    """Tests for LifecycleConfig model."""

    def test_from_api_response_full(self):
        """Test creating from complete API response."""
        data = {
            "mapping": {
                "default_ttl": "P30D",
                "default_inactivity": "P7D",
                "max_ttl": "P90D",
            },
            "snapshot": {
                "default_ttl": "P14D",
                "default_inactivity": "P3D",
                "max_ttl": "P60D",
            },
            "instance": {
                "default_ttl": "PT24H",
                "default_inactivity": "PT8H",
                "max_ttl": "P7D",
            },
        }

        config = LifecycleConfig.from_api_response(data)

        assert config.mapping.default_ttl == "P30D"
        assert config.snapshot.default_ttl == "P14D"
        assert config.instance.default_ttl == "PT24H"

    def test_from_api_response_partial(self):
        """Test creating with some resource types missing."""
        data = {
            "instance": {
                "default_ttl": "PT24H",
            },
        }

        config = LifecycleConfig.from_api_response(data)

        assert config.mapping.default_ttl is None
        assert config.snapshot.default_ttl is None
        assert config.instance.default_ttl == "PT24H"


class TestConcurrencyConfig:
    """Tests for ConcurrencyConfig model."""

    def test_from_api_response_full(self):
        """Test creating from complete API response."""
        data = {
            "per_analyst": 5,
            "cluster_total": 100,
            "updated_at": "2025-01-15T10:30:00Z",
        }

        config = ConcurrencyConfig.from_api_response(data)

        assert config.per_analyst == 5
        assert config.cluster_total == 100
        assert config.updated_at is not None
        assert config.updated_at.year == 2025

    def test_from_api_response_without_timestamp(self):
        """Test creating without updated_at."""
        data = {
            "per_analyst": 3,
            "cluster_total": 50,
        }

        config = ConcurrencyConfig.from_api_response(data)

        assert config.per_analyst == 3
        assert config.cluster_total == 50
        assert config.updated_at is None


class TestMaintenanceMode:
    """Tests for MaintenanceMode model."""

    def test_from_api_response_enabled(self):
        """Test creating when maintenance is enabled."""
        data = {
            "enabled": True,
            "message": "Scheduled maintenance in progress",
            "updated_at": "2025-01-15T10:30:00Z",
            "updated_by": "ops-user",
        }

        mode = MaintenanceMode.from_api_response(data)

        assert mode.enabled is True
        assert mode.message == "Scheduled maintenance in progress"
        assert mode.updated_by == "ops-user"
        assert mode.updated_at is not None

    def test_from_api_response_disabled(self):
        """Test creating when maintenance is disabled."""
        data = {
            "enabled": False,
            "message": "",
        }

        mode = MaintenanceMode.from_api_response(data)

        assert mode.enabled is False
        assert mode.message == ""
        assert mode.updated_at is None
        assert mode.updated_by is None

    def test_from_api_response_missing_message(self):
        """Test creating with missing message defaults to empty string."""
        data = {"enabled": False}

        mode = MaintenanceMode.from_api_response(data)

        assert mode.message == ""


class TestExportConfig:
    """Tests for ExportConfig model."""

    def test_from_api_response_full(self):
        """Test creating from complete API response."""
        data = {
            "max_duration_seconds": 3600,
            "updated_at": "2025-01-15T10:30:00Z",
            "updated_by": "admin-user",
        }

        config = ExportConfig.from_api_response(data)

        assert config.max_duration_seconds == 3600
        assert config.updated_at is not None
        assert config.updated_by == "admin-user"

    def test_from_api_response_minimal(self):
        """Test creating with only required fields."""
        data = {"max_duration_seconds": 1800}

        config = ExportConfig.from_api_response(data)

        assert config.max_duration_seconds == 1800
        assert config.updated_at is None
        assert config.updated_by is None


class TestComponentHealth:
    """Tests for ComponentHealth model."""

    def test_from_api_response_healthy(self):
        """Test creating healthy component."""
        data = {
            "status": "healthy",
            "latency_ms": 15,
        }

        health = ComponentHealth.from_api_response(data)

        assert health.status == "healthy"
        assert health.latency_ms == 15
        assert health.error is None

    def test_from_api_response_unhealthy(self):
        """Test creating unhealthy component with error."""
        data = {
            "status": "unhealthy",
            "latency_ms": None,
            "error": "Connection refused",
        }

        health = ComponentHealth.from_api_response(data)

        assert health.status == "unhealthy"
        assert health.latency_ms is None
        assert health.error == "Connection refused"


class TestClusterHealth:
    """Tests for ClusterHealth model."""

    def test_from_api_response_healthy(self):
        """Test creating healthy cluster."""
        data = {
            "status": "healthy",
            "components": {
                "database": {"status": "healthy", "latency_ms": 5},
                "kubernetes": {"status": "healthy", "latency_ms": 20},
                "starburst": {"status": "healthy", "latency_ms": 50},
            },
            "checked_at": "2025-01-15T10:30:00Z",
        }

        health = ClusterHealth.from_api_response(data)

        assert health.status == "healthy"
        assert len(health.components) == 3
        assert health.components["database"].status == "healthy"
        assert health.components["database"].latency_ms == 5
        assert health.checked_at.year == 2025

    def test_from_api_response_degraded(self):
        """Test creating degraded cluster with one unhealthy component."""
        data = {
            "status": "degraded",
            "components": {
                "database": {"status": "healthy", "latency_ms": 5},
                "starburst": {"status": "unhealthy", "error": "Connection timeout"},
            },
            "checked_at": "2025-01-15T10:30:00Z",
        }

        health = ClusterHealth.from_api_response(data)

        assert health.status == "degraded"
        assert health.components["starburst"].status == "unhealthy"
        assert health.components["starburst"].error == "Connection timeout"

    def test_from_api_response_empty_components(self):
        """Test creating with no components."""
        data = {
            "status": "healthy",
            "checked_at": "2025-01-15T10:30:00Z",
        }

        health = ClusterHealth.from_api_response(data)

        assert health.status == "healthy"
        assert health.components == {}


class TestOwnerInstanceCount:
    """Tests for OwnerInstanceCount model."""

    def test_from_api_response(self):
        """Test creating from API response."""
        data = {
            "owner_username": "analyst-user",
            "count": 3,
        }

        count = OwnerInstanceCount.from_api_response(data)

        assert count.owner_username == "analyst-user"
        assert count.count == 3


class TestInstanceLimits:
    """Tests for InstanceLimits model."""

    def test_from_api_response(self):
        """Test creating from API response."""
        data = {
            "per_analyst": 5,
            "cluster_total": 100,
            "cluster_used": 42,
            "cluster_available": 58,
        }

        limits = InstanceLimits.from_api_response(data)

        assert limits.per_analyst == 5
        assert limits.cluster_total == 100
        assert limits.cluster_used == 42
        assert limits.cluster_available == 58


class TestClusterInstances:
    """Tests for ClusterInstances model."""

    def test_from_api_response_full(self):
        """Test creating from complete API response."""
        data = {
            "total": 42,
            "by_status": {
                "running": 35,
                "starting": 5,
                "stopping": 2,
            },
            "by_owner": [
                {"owner_username": "analyst-alice", "count": 10},
                {"owner_username": "analyst-bob", "count": 8},
            ],
            "limits": {
                "per_analyst": 5,
                "cluster_total": 100,
                "cluster_used": 42,
                "cluster_available": 58,
            },
        }

        instances = ClusterInstances.from_api_response(data)

        assert instances.total == 42
        assert instances.by_status["running"] == 35
        assert len(instances.by_owner) == 2
        assert instances.by_owner[0].owner_username == "analyst-alice"
        assert instances.limits.cluster_available == 58

    def test_from_api_response_empty(self):
        """Test creating with empty counts."""
        data = {
            "total": 0,
            "by_status": {},
            "by_owner": [],
            "limits": {
                "per_analyst": 5,
                "cluster_total": 100,
                "cluster_used": 0,
                "cluster_available": 100,
            },
        }

        instances = ClusterInstances.from_api_response(data)

        assert instances.total == 0
        assert instances.by_status == {}
        assert instances.by_owner == []


class TestHealthStatus:
    """Tests for HealthStatus model."""

    def test_from_api_response_health_endpoint(self):
        """Test creating from /health endpoint response."""
        data = {
            "status": "ok",
            "version": "1.2.3",
        }

        health = HealthStatus.from_api_response(data)

        assert health.status == "ok"
        assert health.version == "1.2.3"
        assert health.database is None

    def test_from_api_response_ready_endpoint(self):
        """Test creating from /ready endpoint response."""
        data = {
            "status": "ok",
            "version": "1.2.3",
            "database": "connected",
        }

        health = HealthStatus.from_api_response(data)

        assert health.status == "ok"
        assert health.version == "1.2.3"
        assert health.database == "connected"

    def test_from_api_response_minimal(self):
        """Test creating with only status."""
        data = {"status": "ok"}

        health = HealthStatus.from_api_response(data)

        assert health.status == "ok"
        assert health.version is None
        assert health.database is None
