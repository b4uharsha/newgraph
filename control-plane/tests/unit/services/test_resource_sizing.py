"""Unit tests for dynamic resource sizing."""

import pytest
from unittest.mock import AsyncMock, patch

from graph_olap_schemas import WrapperType

from control_plane.services.instance_service import InstanceService


def _make_service() -> InstanceService:
    """Create InstanceService with mock dependencies."""
    return InstanceService(
        instance_repo=AsyncMock(),
        snapshot_repo=AsyncMock(),
        config_repo=AsyncMock(),
        favorites_repo=AsyncMock(),
    )


class TestCalculateResources:
    """Tests for _calculate_resources()."""

    def test_falkordb_small_snapshot(self):
        """500MB snapshot -> minimum 2Gi memory (after headroom ~3Gi)."""
        service = _make_service()
        result = service._calculate_resources(
            snapshot_size_bytes=500 * 1024**2,  # 500MB
            wrapper_type=WrapperType.FALKORDB,
        )
        # 0.49GB * 2.0 + 1 = ~1.98 -> max(2.0, 1.98) = 2.0 -> * 1.5 = 3.0 -> ceil = 3Gi
        assert result["memory_request"] == "3Gi"
        assert result["memory_limit"] == "3Gi"
        assert result["cpu_request"] == "2"
        assert result["cpu_limit"] == "4"
        assert result["disk_size"] == "10Gi"  # min 10

    def test_falkordb_large_snapshot(self):
        """10GB snapshot -> large memory allocation."""
        service = _make_service()
        result = service._calculate_resources(
            snapshot_size_bytes=10 * 1024**3,  # 10GB
            wrapper_type=WrapperType.FALKORDB,
        )
        # 10 * 2.0 + 1 = 21 -> * 1.5 = 31.5 -> ceil = 32Gi (at cap)
        assert result["memory_request"] == "32Gi"
        assert result["memory_limit"] == "32Gi"

    def test_ryugraph_small_snapshot(self):
        """500MB snapshot -> minimum memory for ryugraph."""
        service = _make_service()
        result = service._calculate_resources(
            snapshot_size_bytes=500 * 1024**2,  # 500MB
            wrapper_type=WrapperType.RYUGRAPH,
        )
        # 0.49 * 1.2 + 0.5 = ~1.09 -> max(2.0, 1.09) = 2.0 -> * 1.5 = 3.0 -> 3Gi
        assert result["memory_request"] == "3Gi"
        assert result["memory_limit"] == "3Gi"

    def test_ryugraph_large_snapshot(self):
        """10GB snapshot -> sized memory for ryugraph."""
        service = _make_service()
        result = service._calculate_resources(
            snapshot_size_bytes=10 * 1024**3,  # 10GB
            wrapper_type=WrapperType.RYUGRAPH,
        )
        # 10 * 1.2 + 0.5 = 12.5 -> * 1.5 = 18.75 -> ceil = 19Gi
        assert result["memory_request"] == "19Gi"
        assert result["memory_limit"] == "19Gi"

    def test_no_snapshot_size(self):
        """None size_bytes -> minimum defaults."""
        service = _make_service()
        result = service._calculate_resources(
            snapshot_size_bytes=None,
            wrapper_type=WrapperType.FALKORDB,
        )
        # 0 * 2.0 + 1 = 1 -> max(2.0, 1) = 2.0 -> * 1.5 = 3.0 -> 3Gi
        assert result["memory_request"] == "3Gi"
        assert result["memory_limit"] == "3Gi"
        assert result["disk_size"] == "10Gi"

    def test_max_cap(self):
        """Very large snapshot capped at 32Gi."""
        service = _make_service()
        result = service._calculate_resources(
            snapshot_size_bytes=50 * 1024**3,  # 50GB
            wrapper_type=WrapperType.FALKORDB,
        )
        # 50 * 2.0 + 1 = 101 -> * 1.5 = 151.5 -> min(151.5, 32) = 32Gi
        assert result["memory_request"] == "32Gi"
        assert result["memory_limit"] == "32Gi"

    def test_disk_sizing(self):
        """Disk = max(10, int(size_gb * 1.2) + 5)."""
        service = _make_service()
        result = service._calculate_resources(
            snapshot_size_bytes=20 * 1024**3,  # 20GB
            wrapper_type=WrapperType.RYUGRAPH,
        )
        # disk: max(10, int(20 * 1.2) + 5) = max(10, 29) = 29Gi
        assert result["disk_size"] == "29Gi"

    def test_cpu_default(self):
        """Default cpu_cores=2 -> request=2, limit=4."""
        service = _make_service()
        result = service._calculate_resources(
            snapshot_size_bytes=0,
            wrapper_type=WrapperType.RYUGRAPH,
        )
        assert result["cpu_request"] == "2"
        assert result["cpu_limit"] == "4"

    def test_cpu_override(self):
        """cpu_cores=4 -> request=4, limit=8."""
        service = _make_service()
        result = service._calculate_resources(
            snapshot_size_bytes=0,
            wrapper_type=WrapperType.RYUGRAPH,
            cpu_cores=4,
        )
        assert result["cpu_request"] == "4"
        assert result["cpu_limit"] == "8"

    def test_guaranteed_qos(self):
        """Memory request == limit for Guaranteed QoS class."""
        service = _make_service()
        result = service._calculate_resources(
            snapshot_size_bytes=5 * 1024**3,
            wrapper_type=WrapperType.FALKORDB,
        )
        assert result["memory_request"] == result["memory_limit"]
