"""Tests for configuration models."""

import pytest
from pydantic import ValidationError

from wrapper.config import WrapperConfig


class TestWrapperConfig:
    """Tests for WrapperConfig."""

    def test_wrapper_config_valid_gcs_path(self):
        """Test WrapperConfig with valid GCS path."""
        config = WrapperConfig(
            instance_id="123",
            snapshot_id="456",
            mapping_id="789",
            owner_id="user-1",
            control_plane_url="http://localhost:8000",
            gcs_base_path="gs://bucket/path",
        )
        assert config.gcs_base_path == "gs://bucket/path"

    def test_wrapper_config_strips_trailing_slash(self):
        """Test WrapperConfig strips trailing slash from GCS path."""
        config = WrapperConfig(
            instance_id="123",
            snapshot_id="456",
            mapping_id="789",
            owner_id="user-1",
            control_plane_url="http://localhost:8000",
            gcs_base_path="gs://bucket/path/",
        )
        assert config.gcs_base_path == "gs://bucket/path"

    def test_wrapper_config_invalid_gcs_path(self):
        """Test WrapperConfig rejects non-GCS path."""
        with pytest.raises(ValidationError) as exc_info:
            WrapperConfig(
                instance_id="123",
                snapshot_id="456",
                mapping_id="789",
                owner_id="user-1",
                control_plane_url="http://localhost:8000",
                gcs_base_path="/local/path",
            )

        errors = exc_info.value.errors()
        assert any("gcs_base_path must start with 'gs://'" in str(e) for e in errors)

    def test_wrapper_config_s3_path_rejected(self):
        """Test WrapperConfig rejects S3 path."""
        with pytest.raises(ValidationError) as exc_info:
            WrapperConfig(
                instance_id="123",
                snapshot_id="456",
                mapping_id="789",
                owner_id="user-1",
                control_plane_url="http://localhost:8000",
                gcs_base_path="s3://bucket/path",
            )

        errors = exc_info.value.errors()
        assert any("gcs_base_path must start with 'gs://'" in str(e) for e in errors)
