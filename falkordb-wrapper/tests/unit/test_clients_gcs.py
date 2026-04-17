"""Unit tests for the GCS client.

Tests cover:
- GCS path parsing
- File download
- File listing
- Error handling
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wrapper.exceptions import GCSDownloadError


class TestGCSPathParsing:
    """Tests for GCS path parsing logic."""

    def test_parse_gcs_path_valid(self):
        """Valid GCS path is parsed correctly."""
        # Test path parsing logic directly
        gcs_path = "gs://my-bucket/path/to/file.parquet"
        path_parts = gcs_path[5:].split("/", 1)

        assert path_parts[0] == "my-bucket"
        assert path_parts[1] == "path/to/file.parquet"

    def test_parse_gcs_path_bucket_only(self):
        """GCS path with only bucket name."""
        gcs_path = "gs://my-bucket"
        path_parts = gcs_path[5:].split("/", 1)

        assert path_parts[0] == "my-bucket"
        assert len(path_parts) == 1

    def test_parse_gcs_path_nested(self):
        """GCS path with deeply nested directory."""
        gcs_path = "gs://bucket/a/b/c/d/file.csv"
        path_parts = gcs_path[5:].split("/", 1)

        assert path_parts[0] == "bucket"
        assert path_parts[1] == "a/b/c/d/file.csv"


class TestGCSClientDownload:
    """Tests for GCS client download functionality."""

    @pytest.mark.asyncio
    async def test_download_file_invalid_path_no_gs_prefix(self):
        """Download fails for path without gs:// prefix."""
        with patch("wrapper.clients.gcs.storage"):
            from wrapper.clients.gcs import GCSClient

            client = GCSClient()

            with pytest.raises(ValueError, match="Invalid GCS path"):
                await client.download_file(
                    gcs_path="s3://bucket/file.txt",
                    local_path=Path("/tmp/test.txt"),
                )

    @pytest.mark.asyncio
    async def test_download_file_invalid_path_format(self):
        """Download fails for invalid GCS path format."""
        with patch("wrapper.clients.gcs.storage"):
            from wrapper.clients.gcs import GCSClient

            client = GCSClient()

            with pytest.raises(ValueError, match="Invalid GCS path format"):
                await client.download_file(
                    gcs_path="gs://bucketonly",  # No blob path
                    local_path=Path("/tmp/test.txt"),
                )

    @pytest.mark.asyncio
    async def test_download_file_success(self, tmp_path):
        """Download file successfully creates local file."""
        mock_storage = MagicMock()
        mock_blob = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_storage.Client.return_value.bucket.return_value = mock_bucket

        # Mock the download to create an actual file
        local_path = tmp_path / "downloaded.parquet"

        def mock_download(path):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_bytes(b"test content")

        mock_blob.download_to_filename.side_effect = mock_download

        with patch("wrapper.clients.gcs.storage", mock_storage):
            from wrapper.clients.gcs import GCSClient

            client = GCSClient()

            await client.download_file(
                gcs_path="gs://test-bucket/data/file.parquet",
                local_path=local_path,
            )

            # Verify blob was accessed with correct path
            mock_bucket.blob.assert_called_once_with("data/file.parquet")
            mock_blob.download_to_filename.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_file_creates_parent_dirs(self, tmp_path):
        """Download creates parent directories if they don't exist."""
        mock_storage = MagicMock()
        mock_blob = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_storage.Client.return_value.bucket.return_value = mock_bucket

        # Target path with non-existent parent
        local_path = tmp_path / "nested" / "dir" / "file.parquet"

        def mock_download(path):
            # Parent should already be created by the client
            Path(path).write_bytes(b"test content")

        mock_blob.download_to_filename.side_effect = mock_download

        with patch("wrapper.clients.gcs.storage", mock_storage):
            from wrapper.clients.gcs import GCSClient

            client = GCSClient()

            await client.download_file(
                gcs_path="gs://bucket/file.parquet",
                local_path=local_path,
            )

            # Parent dir should have been created
            assert local_path.parent.exists()


class TestGCSClientListFiles:
    """Tests for GCS client file listing."""

    @pytest.mark.asyncio
    async def test_list_files_invalid_prefix(self):
        """List fails for invalid GCS prefix."""
        with patch("wrapper.clients.gcs.storage"):
            from wrapper.clients.gcs import GCSClient

            client = GCSClient()

            with pytest.raises(ValueError, match="Invalid GCS prefix"):
                await client.list_files("http://bucket/path/")

    @pytest.mark.asyncio
    async def test_list_files_success(self):
        """List files returns GCS paths."""
        mock_storage = MagicMock()
        mock_bucket = MagicMock()
        mock_storage.Client.return_value.bucket.return_value = mock_bucket

        # Create mock blobs
        mock_blob1 = MagicMock()
        mock_blob1.name = "data/file1.parquet"
        mock_blob2 = MagicMock()
        mock_blob2.name = "data/file2.parquet"

        mock_bucket.list_blobs.return_value = [mock_blob1, mock_blob2]

        with patch("wrapper.clients.gcs.storage", mock_storage):
            from wrapper.clients.gcs import GCSClient

            client = GCSClient()

            result = await client.list_files("gs://test-bucket/data/")

            assert len(result) == 2
            assert "gs://test-bucket/data/file1.parquet" in result
            assert "gs://test-bucket/data/file2.parquet" in result

    @pytest.mark.asyncio
    async def test_list_files_empty(self):
        """List files returns empty list when no files found."""
        mock_storage = MagicMock()
        mock_bucket = MagicMock()
        mock_storage.Client.return_value.bucket.return_value = mock_bucket
        mock_bucket.list_blobs.return_value = []

        with patch("wrapper.clients.gcs.storage", mock_storage):
            from wrapper.clients.gcs import GCSClient

            client = GCSClient()

            result = await client.list_files("gs://test-bucket/empty/")

            assert result == []


# =============================================================================
# SNAPSHOT TESTS DISABLED
# These tests are commented out as snapshot functionality has been disabled.
# =============================================================================
# class TestGCSClientDownloadSnapshot:
#     """Tests for snapshot data download."""
#
#     @pytest.mark.asyncio
#     async def test_download_snapshot_data_success(self, tmp_path):
#         """Download snapshot data successfully."""
#         mock_storage = MagicMock()
#         mock_bucket = MagicMock()
#         mock_blob = MagicMock()
#         mock_bucket.blob.return_value = mock_blob
#         mock_storage.Client.return_value.bucket.return_value = mock_bucket
#
#         # Mock list_blobs
#         mock_blob1 = MagicMock()
#         mock_blob1.name = "snapshot-123/nodes.parquet"
#         mock_blob2 = MagicMock()
#         mock_blob2.name = "snapshot-123/edges.parquet"
#         mock_bucket.list_blobs.return_value = [mock_blob1, mock_blob2]
#
#         # Mock download
#         def mock_download(path):
#             Path(path).write_bytes(b"test content")
#
#         mock_blob.download_to_filename.side_effect = mock_download
#
#         with patch("wrapper.clients.gcs.storage", mock_storage):
#             from wrapper.clients.gcs import GCSClient
#
#             client = GCSClient()
#
#             result = await client.download_snapshot_data(
#                 "gs://test-bucket/snapshot-123"
#             )
#
#             assert len(result) == 2
#
#     @pytest.mark.asyncio
#     async def test_download_snapshot_data_raises_on_error(self):
#         """Download snapshot data raises GCSDownloadError on failure."""
#         mock_storage = MagicMock()
#         mock_storage.Client.return_value.bucket.side_effect = Exception("Network error")
#
#         with patch("wrapper.clients.gcs.storage", mock_storage):
#             from wrapper.clients.gcs import GCSClient
#
#             client = GCSClient()
#
#             with pytest.raises(GCSDownloadError) as exc_info:
#                 await client.download_snapshot_data("gs://test-bucket/snapshot")
#
#             assert "Network error" in str(exc_info.value)
