"""Integration tests for OpsResource and HealthResource with mocked API."""

from __future__ import annotations

import httpx
import pytest
import respx

from graph_olap import GraphOLAPClient
from graph_olap.models.ops import (
    ClusterHealth,
    ClusterInstances,
    ConcurrencyConfig,
    ExportConfig,
    HealthStatus,
    LifecycleConfig,
    MaintenanceMode,
)


class TestHealthWorkflow:
    """Integration tests for health check workflow."""

    @respx.mock
    def test_health_check(self):
        """Test basic health check returns status."""
        respx.get("https://api.example.com/health").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "ok",
                    "version": "1.2.3",
                },
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            result = client.health.check()

            assert isinstance(result, HealthStatus)
            assert result.status == "ok"
            assert result.version == "1.2.3"

    @respx.mock
    def test_ready_check(self):
        """Test readiness check returns status with database."""
        respx.get("https://api.example.com/ready").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "ok",
                    "version": "1.2.3",
                    "database": "connected",
                },
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            result = client.health.ready()

            assert isinstance(result, HealthStatus)
            assert result.status == "ok"
            assert result.database == "connected"

    @respx.mock
    def test_ready_check_unhealthy(self):
        """Test readiness check when service is unhealthy."""
        respx.get("https://api.example.com/ready").mock(
            return_value=httpx.Response(
                503,
                json={
                    "status": "unhealthy",
                    "database": "disconnected",
                },
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            # Should raise an error for 503
            with pytest.raises(Exception):
                client.health.ready()


class TestOpsLifecycleConfigWorkflow:
    """Integration tests for lifecycle config workflow."""

    @respx.mock
    def test_get_lifecycle_config(self):
        """Test getting lifecycle configuration."""
        respx.get("https://api.example.com/api/config/lifecycle").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
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
                },
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            result = client.ops.get_lifecycle_config()

            assert isinstance(result, LifecycleConfig)
            assert result.mapping.default_ttl == "P30D"
            assert result.snapshot.default_ttl == "P14D"
            assert result.instance.default_ttl == "PT24H"

    @respx.mock
    def test_update_lifecycle_config(self):
        """Test updating lifecycle configuration."""
        respx.put("https://api.example.com/api/config/lifecycle").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"updated": True}},
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            result = client.ops.update_lifecycle_config(
                instance={"default_ttl": "PT48H", "default_inactivity": "PT12H"}
            )

            assert result is True


class TestOpsConcurrencyConfigWorkflow:
    """Integration tests for concurrency config workflow."""

    @respx.mock
    def test_get_concurrency_config(self):
        """Test getting concurrency configuration."""
        respx.get("https://api.example.com/api/config/concurrency").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "per_analyst": 5,
                        "cluster_total": 100,
                        "updated_at": "2025-01-15T10:30:00Z",
                    }
                },
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            result = client.ops.get_concurrency_config()

            assert isinstance(result, ConcurrencyConfig)
            assert result.per_analyst == 5
            assert result.cluster_total == 100

    @respx.mock
    def test_update_concurrency_config(self):
        """Test updating concurrency configuration."""
        respx.put("https://api.example.com/api/config/concurrency").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "per_analyst": 10,
                        "cluster_total": 200,
                        "updated_at": "2025-01-15T11:00:00Z",
                    }
                },
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            result = client.ops.update_concurrency_config(
                per_analyst=10,
                cluster_total=200,
            )

            assert isinstance(result, ConcurrencyConfig)
            assert result.per_analyst == 10
            assert result.cluster_total == 200


class TestOpsMaintenanceModeWorkflow:
    """Integration tests for maintenance mode workflow."""

    @respx.mock
    def test_get_maintenance_mode(self):
        """Test getting maintenance mode status."""
        respx.get("https://api.example.com/api/config/maintenance").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "enabled": False,
                        "message": "",
                    }
                },
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            result = client.ops.get_maintenance_mode()

            assert isinstance(result, MaintenanceMode)
            assert result.enabled is False

    @respx.mock
    def test_enable_maintenance_mode(self):
        """Test enabling maintenance mode."""
        respx.put("https://api.example.com/api/config/maintenance").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "enabled": True,
                        "message": "Scheduled maintenance",
                        "updated_at": "2025-01-15T10:30:00Z",
                        "updated_by": "ops-user",
                    }
                },
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            result = client.ops.set_maintenance_mode(
                enabled=True,
                message="Scheduled maintenance",
            )

            assert isinstance(result, MaintenanceMode)
            assert result.enabled is True
            assert result.message == "Scheduled maintenance"

    @respx.mock
    def test_disable_maintenance_mode(self):
        """Test disabling maintenance mode."""
        respx.put("https://api.example.com/api/config/maintenance").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "enabled": False,
                        "message": "",
                    }
                },
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            result = client.ops.set_maintenance_mode(enabled=False)

            assert result.enabled is False


class TestOpsExportConfigWorkflow:
    """Integration tests for export config workflow."""

    @respx.mock
    def test_get_export_config(self):
        """Test getting export configuration."""
        respx.get("https://api.example.com/api/config/export").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "max_duration_seconds": 3600,
                        "updated_at": "2025-01-15T10:30:00Z",
                    }
                },
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            result = client.ops.get_export_config()

            assert isinstance(result, ExportConfig)
            assert result.max_duration_seconds == 3600

    @respx.mock
    def test_update_export_config(self):
        """Test updating export configuration."""
        respx.put("https://api.example.com/api/config/export").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "max_duration_seconds": 7200,
                        "updated_at": "2025-01-15T11:00:00Z",
                    }
                },
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            result = client.ops.update_export_config(max_duration_seconds=7200)

            assert isinstance(result, ExportConfig)
            assert result.max_duration_seconds == 7200


class TestOpsClusterWorkflow:
    """Integration tests for cluster status workflow."""

    @respx.mock
    def test_get_cluster_health(self):
        """Test getting cluster health status."""
        respx.get("https://api.example.com/api/cluster/health").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "status": "healthy",
                        "components": {
                            "database": {"status": "healthy", "latency_ms": 5},
                            "kubernetes": {"status": "healthy", "latency_ms": 20},
                            "starburst": {"status": "healthy", "latency_ms": 50},
                        },
                        "checked_at": "2025-01-15T10:30:00Z",
                    }
                },
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            result = client.ops.get_cluster_health()

            assert isinstance(result, ClusterHealth)
            assert result.status == "healthy"
            assert len(result.components) == 3
            assert result.components["database"].status == "healthy"

    @respx.mock
    def test_get_cluster_health_degraded(self):
        """Test getting degraded cluster health."""
        respx.get("https://api.example.com/api/cluster/health").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "status": "degraded",
                        "components": {
                            "database": {"status": "healthy", "latency_ms": 5},
                            "starburst": {
                                "status": "unhealthy",
                                "error": "Connection timeout",
                            },
                        },
                        "checked_at": "2025-01-15T10:30:00Z",
                    }
                },
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            result = client.ops.get_cluster_health()

            assert result.status == "degraded"
            assert result.components["starburst"].status == "unhealthy"
            assert result.components["starburst"].error == "Connection timeout"

    @respx.mock
    def test_get_cluster_instances(self):
        """Test getting cluster instance summary."""
        respx.get("https://api.example.com/api/cluster/instances").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "total": 42,
                        "by_status": {
                            "running": 35,
                            "starting": 5,
                            "stopping": 2,
                        },
                        "by_owner": [
                            {"owner_username": "analyst-alice", "count": 10},
                            {"owner_username": "analyst-bob", "count": 8},
                            {"owner_username": "analyst-charlie", "count": 24},
                        ],
                        "limits": {
                            "per_analyst": 5,
                            "cluster_total": 100,
                            "cluster_used": 42,
                            "cluster_available": 58,
                        },
                    }
                },
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            result = client.ops.get_cluster_instances()

            assert isinstance(result, ClusterInstances)
            assert result.total == 42
            assert result.by_status["running"] == 35
            assert len(result.by_owner) == 3
            assert result.limits.cluster_available == 58


class TestOpsMetricsWorkflow:
    """Integration tests for metrics endpoint workflow."""

    @respx.mock
    def test_get_metrics_returns_prometheus_text(self):
        """Test getting Prometheus metrics as text."""
        sample_metrics = """# HELP background_job_execution_total Total number of background job executions
# TYPE background_job_execution_total counter
background_job_execution_total{job_name="reconciliation",status="success"} 42.0
background_job_execution_total{job_name="lifecycle",status="success"} 38.0
# HELP reconciliation_passes_total Total reconciliation passes
# TYPE reconciliation_passes_total counter
reconciliation_passes_total 42.0
# HELP lifecycle_passes_total Total lifecycle passes
# TYPE lifecycle_passes_total counter
lifecycle_passes_total 38.0
"""
        respx.get("https://api.example.com/metrics").mock(
            return_value=httpx.Response(
                200,
                content=sample_metrics.encode('utf-8'),
                headers={"Content-Type": "text/plain; charset=utf-8"},
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            result = client.ops.get_metrics()

            assert isinstance(result, str)
            assert "background_job_execution_total" in result
            assert 'job_name="reconciliation"' in result
            assert 'job_name="lifecycle"' in result
            assert "reconciliation_passes_total" in result
            assert "lifecycle_passes_total" in result

    @respx.mock
    def test_get_metrics_checks_all_background_jobs(self):
        """Test metrics contain all expected background jobs."""
        sample_metrics = """background_job_execution_total{job_name="reconciliation",status="success"} 42.0
background_job_execution_total{job_name="lifecycle",status="success"} 38.0
background_job_execution_total{job_name="export_reconciliation",status="success"} 25.0
background_job_execution_total{job_name="schema_cache",status="success"} 10.0
"""
        respx.get("https://api.example.com/metrics").mock(
            return_value=httpx.Response(
                200,
                content=sample_metrics.encode('utf-8'),
                headers={"Content-Type": "text/plain"},
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            metrics = client.ops.get_metrics()

            # Verify all background jobs are present
            assert 'job_name="reconciliation"' in metrics
            assert 'job_name="lifecycle"' in metrics
            assert 'job_name="export_reconciliation"' in metrics
            assert 'job_name="schema_cache"' in metrics


class TestOpsAuthorizationErrors:
    """Integration tests for ops authorization errors."""

    @respx.mock
    def test_unauthorized_user_cannot_access_config(self):
        """Test non-ops user gets 403 on config endpoints."""
        from graph_olap.exceptions import ForbiddenError

        respx.get("https://api.example.com/api/config/lifecycle").mock(
            return_value=httpx.Response(
                403,
                json={
                    "error": {
                        "code": "FORBIDDEN",
                        "message": "Ops role required",
                    }
                },
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            with pytest.raises(ForbiddenError):
                client.ops.get_lifecycle_config()

    @respx.mock
    def test_unauthorized_user_cannot_access_metrics(self):
        """Test non-ops user gets 403 on metrics endpoint."""
        from graph_olap.exceptions import ForbiddenError

        respx.get("https://api.example.com/metrics").mock(
            return_value=httpx.Response(
                403,
                json={
                    "error": {
                        "code": "FORBIDDEN",
                        "message": "Ops role required",
                    }
                },
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            with pytest.raises(ForbiddenError):
                client.ops.get_metrics()

    @respx.mock
    def test_unauthorized_user_cannot_modify_config(self):
        """Test non-ops user gets 403 on config modification."""
        from graph_olap.exceptions import ForbiddenError

        respx.put("https://api.example.com/api/config/concurrency").mock(
            return_value=httpx.Response(
                403,
                json={
                    "error": {
                        "code": "FORBIDDEN",
                        "message": "Ops role required",
                    }
                },
            )
        )

        with GraphOLAPClient(api_url="https://api.example.com") as client:
            with pytest.raises(ForbiddenError):
                client.ops.update_concurrency_config(per_analyst=10, cluster_total=100)
