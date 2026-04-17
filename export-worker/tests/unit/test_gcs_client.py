"""Unit tests for GCSClient."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from google.api_core import exceptions as gcp_exceptions

from export_worker.clients import GCSClient
from export_worker.exceptions import GCSError


class TestGCSClient:
    """Tests for GCSClient."""

    @pytest.fixture
    def mock_storage_client(self) -> MagicMock:
        """Mock Google Cloud Storage client."""
        return MagicMock()

    @pytest.fixture
    def mock_arrow_fs(self) -> MagicMock:
        """Mock PyArrow GCS filesystem."""
        return MagicMock()

    @pytest.fixture
    def client(
        self,
        mock_storage_client: MagicMock,
        mock_arrow_fs: MagicMock,
    ) -> GCSClient:
        """Create GCS client with mocked dependencies."""
        with (
            patch("export_worker.clients.gcs.storage.Client") as mock_client_class,
            patch("export_worker.clients.gcs.arrow_fs.GcsFileSystem") as mock_fs_class,
        ):
            mock_client_class.return_value = mock_storage_client
            mock_fs_class.return_value = mock_arrow_fs
            return GCSClient(project="test-project")

    def test_calculate_total_size_success(
        self,
        client: GCSClient,
        mock_storage_client: MagicMock,
    ) -> None:
        """Test calculating total size of files."""
        # Setup mock blobs
        mock_blob1 = MagicMock()
        mock_blob1.size = 1024
        mock_blob2 = MagicMock()
        mock_blob2.size = 2048
        mock_blob3 = MagicMock()
        mock_blob3.size = 512

        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob1, mock_blob2, mock_blob3]
        mock_storage_client.bucket.return_value = mock_bucket

        # Inject mock
        client._storage_client = mock_storage_client

        total_size = client.calculate_total_size("gs://test-bucket/path/to/data/")

        assert total_size == 3584  # 1024 + 2048 + 512
        mock_storage_client.bucket.assert_called_once_with("test-bucket")
        mock_bucket.list_blobs.assert_called_once()

    def test_calculate_total_size_empty_path(
        self,
        client: GCSClient,
        mock_storage_client: MagicMock,
    ) -> None:
        """Test calculating size of empty path."""
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = []
        mock_storage_client.bucket.return_value = mock_bucket

        client._storage_client = mock_storage_client

        total_size = client.calculate_total_size("gs://test-bucket/empty/")

        assert total_size == 0

    def test_calculate_total_size_gcs_error(
        self,
        client: GCSClient,
        mock_storage_client: MagicMock,
    ) -> None:
        """Test handling GCS error during size calculation."""
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.side_effect = gcp_exceptions.NotFound("Bucket not found")
        mock_storage_client.bucket.return_value = mock_bucket

        client._storage_client = mock_storage_client

        with pytest.raises(GCSError) as exc_info:
            client.calculate_total_size("gs://nonexistent-bucket/path/")

        assert "Bucket not found" in str(exc_info.value)

    def test_count_parquet_rows_success(
        self,
        client: GCSClient,
        mock_storage_client: MagicMock,
        mock_arrow_fs: MagicMock,
    ) -> None:
        """Test counting rows in Parquet files."""
        # Setup mock blobs (Parquet files)
        mock_blob1 = MagicMock()
        mock_blob1.name = "data/file1.parquet"
        mock_blob1.size = 1024
        mock_blob2 = MagicMock()
        mock_blob2.name = "data/file2.parquet"
        mock_blob2.size = 2048

        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob1, mock_blob2]
        mock_storage_client.bucket.return_value = mock_bucket

        client._storage_client = mock_storage_client

        # Setup mock Parquet metadata
        with patch("export_worker.clients.gcs.pq.read_metadata") as mock_read_metadata:
            mock_metadata1 = MagicMock()
            mock_metadata1.num_rows = 1000
            mock_metadata2 = MagicMock()
            mock_metadata2.num_rows = 500

            mock_read_metadata.side_effect = [mock_metadata1, mock_metadata2]

            row_count, size_bytes = client.count_parquet_rows("gs://test-bucket/data/")

            assert row_count == 1500
            assert size_bytes == 3072  # 1024 + 2048
            assert mock_read_metadata.call_count == 2

    def test_count_parquet_rows_no_files(
        self,
        client: GCSClient,
        mock_storage_client: MagicMock,
    ) -> None:
        """Test counting rows when no Parquet files exist."""
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = []
        mock_storage_client.bucket.return_value = mock_bucket

        client._storage_client = mock_storage_client

        row_count, size_bytes = client.count_parquet_rows("gs://test-bucket/empty/")

        assert row_count == 0
        assert size_bytes == 0

    def test_count_parquet_rows_filters_non_parquet(
        self,
        client: GCSClient,
        mock_storage_client: MagicMock,
    ) -> None:
        """Test that non-Parquet files are filtered out."""
        mock_blob1 = MagicMock()
        mock_blob1.name = "data/file1.parquet"
        mock_blob1.size = 1024
        mock_blob2 = MagicMock()
        mock_blob2.name = "data/file2.csv"  # Not Parquet
        mock_blob2.size = 512
        mock_blob3 = MagicMock()
        mock_blob3.name = "data/_SUCCESS"  # Not Parquet
        mock_blob3.size = 0

        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob1, mock_blob2, mock_blob3]
        mock_storage_client.bucket.return_value = mock_bucket

        client._storage_client = mock_storage_client

        with patch("export_worker.clients.gcs.pq.read_metadata") as mock_read_metadata:
            mock_metadata = MagicMock()
            mock_metadata.num_rows = 1000
            mock_read_metadata.return_value = mock_metadata

            row_count, size_bytes = client.count_parquet_rows("gs://test-bucket/data/")

            assert row_count == 1000
            assert size_bytes == 1024  # Only Parquet files
            # Only called once for the .parquet file
            assert mock_read_metadata.call_count == 1

    def test_count_parquet_rows_metadata_error(
        self,
        client: GCSClient,
        mock_storage_client: MagicMock,
    ) -> None:
        """Test handling error reading Parquet metadata."""
        mock_blob = MagicMock()
        mock_blob.name = "data/corrupted.parquet"
        mock_blob.size = 1024

        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob]
        mock_storage_client.bucket.return_value = mock_bucket

        client._storage_client = mock_storage_client

        with patch("export_worker.clients.gcs.pq.read_metadata") as mock_read_metadata:
            mock_read_metadata.side_effect = Exception("Invalid Parquet file")

            with pytest.raises(GCSError) as exc_info:
                client.count_parquet_rows("gs://test-bucket/data/")

            assert "Failed to read Parquet file" in str(exc_info.value)

    def test_list_files(
        self,
        client: GCSClient,
        mock_storage_client: MagicMock,
    ) -> None:
        """Test listing files at a path."""
        mock_blob1 = MagicMock()
        mock_blob1.name = "data/file1.parquet"
        mock_blob2 = MagicMock()
        mock_blob2.name = "data/file2.parquet"

        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob1, mock_blob2]
        mock_storage_client.bucket.return_value = mock_bucket

        client._storage_client = mock_storage_client

        files = client.list_files("gs://test-bucket/data/")

        assert len(files) == 2
        assert "gs://test-bucket/data/file1.parquet" in files
        assert "gs://test-bucket/data/file2.parquet" in files

    def test_delete_path(
        self,
        client: GCSClient,
        mock_storage_client: MagicMock,
    ) -> None:
        """Test deleting files at a path."""
        mock_blob1 = MagicMock()
        mock_blob2 = MagicMock()

        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [mock_blob1, mock_blob2]
        mock_storage_client.bucket.return_value = mock_bucket

        client._storage_client = mock_storage_client

        deleted_count = client.delete_path("gs://test-bucket/data/")

        assert deleted_count == 2
        mock_blob1.delete.assert_called_once()
        mock_blob2.delete.assert_called_once()


class TestParseGCSPath:
    """Tests for _parse_gcs_path static method."""

    def test_parse_valid_path(self) -> None:
        """Test parsing a valid GCS path."""
        bucket, prefix = GCSClient._parse_gcs_path("gs://my-bucket/path/to/data/")

        assert bucket == "my-bucket"
        assert prefix == "path/to/data/"

    def test_parse_path_no_trailing_slash(self) -> None:
        """Test parsing path without trailing slash."""
        bucket, prefix = GCSClient._parse_gcs_path("gs://my-bucket/path/to/data")

        assert bucket == "my-bucket"
        # Should add trailing slash for listing
        assert prefix == "path/to/data/"

    def test_parse_bucket_only(self) -> None:
        """Test parsing bucket-only path."""
        bucket, prefix = GCSClient._parse_gcs_path("gs://my-bucket/")

        assert bucket == "my-bucket"
        assert prefix == ""

    def test_parse_bucket_no_slash(self) -> None:
        """Test parsing bucket without trailing slash."""
        bucket, prefix = GCSClient._parse_gcs_path("gs://my-bucket")

        assert bucket == "my-bucket"
        assert prefix == ""

    def test_parse_invalid_path(self) -> None:
        """Test parsing invalid path (missing gs://)."""
        with pytest.raises(ValueError) as exc_info:
            GCSClient._parse_gcs_path("/bucket/path")

        assert "must start with gs://" in str(exc_info.value)

    def test_parse_http_path(self) -> None:
        """Test parsing HTTP path (invalid)."""
        with pytest.raises(ValueError):
            GCSClient._parse_gcs_path("https://storage.googleapis.com/bucket/path")


class TestGCSClientFromConfig:
    """Tests for GCSClient.from_config()."""

    def test_from_config_creates_client(self, mock_env: None) -> None:
        """Test that from_config creates properly configured client."""
        from export_worker.config import GCSConfig

        with (
            patch("export_worker.clients.gcs.storage.Client"),
            patch("export_worker.clients.gcs.arrow_fs.GcsFileSystem"),
        ):
            config = GCSConfig()
            client = GCSClient.from_config(config)

            assert client.project == "test-project"
