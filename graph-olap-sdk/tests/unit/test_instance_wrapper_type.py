"""Unit tests for Instance wrapper_type support."""

from __future__ import annotations

import pytest
from graph_olap_schemas import WrapperType

from graph_olap.models.instance import Instance


class TestInstanceWrapperType:
    """Tests for Instance model wrapper_type field."""

    @pytest.mark.unit
    def test_instance_defaults_to_ryugraph(self):
        """Test instance wrapper_type defaults to RYUGRAPH."""
        instance = Instance(
            id=123,
            name="Test Instance",
            snapshot_id=456,
            mapping_id=789,
            owner_id=1,
            owner_username="test-user",
            status="running",
            wrapper_type=WrapperType.RYUGRAPH,
        )

        assert instance.wrapper_type == WrapperType.RYUGRAPH

    @pytest.mark.unit
    def test_instance_can_be_falkordb(self):
        """Test instance can be created with FALKORDB wrapper type."""
        instance = Instance(
            id=123,
            name="Test FalkorDB Instance",
            snapshot_id=456,
            mapping_id=789,
            owner_id=1,
            owner_username="test-user",
            status="running",
            wrapper_type=WrapperType.FALKORDB,
        )

        assert instance.wrapper_type == WrapperType.FALKORDB

    @pytest.mark.unit
    def test_wrapper_type_serialization(self):
        """Test wrapper_type is serialized correctly."""
        instance = Instance(
            id=123,
            name="Test Instance",
            snapshot_id=456,
            mapping_id=789,
            owner_id=1,
            owner_username="test-user",
            status="running",
            wrapper_type=WrapperType.FALKORDB,
        )

        # Convert to dict
        data = instance.model_dump()

        assert data["wrapper_type"] == "falkordb"

    @pytest.mark.unit
    def test_wrapper_type_deserialization(self):
        """Test wrapper_type can be deserialized from string."""
        data = {
            "id": 123,
            "name": "Test Instance",
            "snapshot_id": 456,
            "mapping_id": 789,
            "owner_id": 1,
            "owner_username": "test-user",
            "status": "running",
            "wrapper_type": "falkordb",
        }

        instance = Instance(**data)

        assert instance.wrapper_type == WrapperType.FALKORDB
