"""Google Cloud Storage client for Parquet operations.

This client handles:
- Counting rows in Parquet files (via metadata, no full read)
- Calculating total size of exported files
- Listing files at a path
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyarrow.parquet as pq
import structlog
from google.api_core import exceptions as gcp_exceptions
from google.cloud import storage
from pyarrow import fs as arrow_fs
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from export_worker.exceptions import GCSError

if TYPE_CHECKING:
    from export_worker.config import GCSConfig

logger = structlog.get_logger()


class GCSClient:
    """Client for GCS operations related to Parquet files."""

    def __init__(self, project: str, emulator_host: str | None = None) -> None:
        """Initialize GCS client.

        Args:
            project: GCP project ID
            emulator_host: GCS emulator endpoint (for testing), e.g. "http://localhost:4443"
        """
        self.project = project
        self._emulator_host = emulator_host
        self._logger = logger.bind(component="gcs")

        if emulator_host:
            # Configure for emulator
            from google.auth import credentials as auth_credentials

            class AnonymousCredentials(auth_credentials.AnonymousCredentials):
                """Anonymous credentials for GCS emulator."""

                def refresh(self, request):
                    pass

            # Parse emulator host to get scheme and endpoint
            # STORAGE_EMULATOR_HOST can be "http://host:port" or just "host:port"
            if emulator_host.startswith("http://") or emulator_host.startswith("https://"):
                endpoint = emulator_host
            else:
                endpoint = f"http://{emulator_host}"

            self._storage_client = storage.Client(
                project=project,
                credentials=AnonymousCredentials(),
                client_options={"api_endpoint": endpoint},
            )
            # PyArrow GcsFileSystem with emulator - use scheme='http'
            # Extract host:port from endpoint
            host_port = endpoint.replace("http://", "").replace("https://", "")
            self._arrow_fs = arrow_fs.GcsFileSystem(
                endpoint_override=host_port,
                scheme="http",
                anonymous=True,
            )
            self._logger.info(
                "Using GCS emulator",
                endpoint=endpoint,
                arrow_endpoint=host_port,
            )
        else:
            self._storage_client = storage.Client(project=project)
            self._arrow_fs = arrow_fs.GcsFileSystem()

    @classmethod
    def from_config(cls, config: GCSConfig) -> GCSClient:
        """Create client from configuration object."""
        return cls(project=config.project, emulator_host=config.emulator_host)

    @retry(
        retry=retry_if_exception_type((gcp_exceptions.GoogleAPIError,)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
    )
    def calculate_total_size(self, gcs_path: str) -> int:
        """Calculate total size of all files under a GCS path.

        Args:
            gcs_path: GCS path (gs://bucket/prefix/)

        Returns:
            Total size in bytes

        Raises:
            GCSError: If operation fails
        """
        bucket_name, prefix = self._parse_gcs_path(gcs_path)

        self._logger.debug("Calculating total size", gcs_path=gcs_path)

        try:
            bucket = self._storage_client.bucket(bucket_name)
            blobs = bucket.list_blobs(prefix=prefix)
            total_size = sum(blob.size for blob in blobs)

            self._logger.info(
                "Calculated total size",
                gcs_path=gcs_path,
                size_bytes=total_size,
            )
            return total_size

        except gcp_exceptions.GoogleAPIError as e:
            raise GCSError(
                f"Failed to calculate size: {e}",
                gcs_path=gcs_path,
            ) from e

    @retry(
        retry=retry_if_exception_type((gcp_exceptions.GoogleAPIError,)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
    )
    def count_parquet_rows(self, gcs_path: str) -> tuple[int, int]:
        """Count total rows and size across all Parquet files at path.

        Uses Parquet metadata to count rows efficiently without reading
        the actual data.

        Args:
            gcs_path: GCS path containing Parquet files (gs://bucket/prefix/)

        Returns:
            Tuple of (row_count, size_bytes)

        Raises:
            GCSError: If operation fails or no files found
        """
        bucket_name, prefix = self._parse_gcs_path(gcs_path)

        self._logger.debug("Counting Parquet rows", gcs_path=gcs_path)

        try:
            # List files in the path (with sizes)
            bucket = self._storage_client.bucket(bucket_name)
            blobs = list(bucket.list_blobs(prefix=prefix))
            # Accept both .parquet files and Trino CTAS output (no extension)
            # Filter out directory markers, empty files, and non-Parquet files
            def is_parquet_file(blob):
                if blob.name.endswith("/") or blob.size == 0:
                    return False
                # Accept .parquet files or files with no extension (Trino CTAS output)
                name_lower = blob.name.lower()
                if name_lower.endswith(".parquet"):
                    return True
                # Check if file has no extension (no dot after last slash)
                filename = blob.name.split("/")[-1]
                return "." not in filename

            parquet_blobs = [b for b in blobs if is_parquet_file(b)]

            if not parquet_blobs:
                self._logger.warning("No Parquet files found", gcs_path=gcs_path)
                return 0, 0

            # Count rows from each file's metadata and sum sizes
            total_rows = 0
            total_size = sum(blob.size for blob in parquet_blobs)

            for blob in parquet_blobs:
                # PyArrow path format: bucket/prefix/file.parquet
                arrow_path = f"{bucket_name}/{blob.name}"
                try:
                    metadata = pq.read_metadata(arrow_path, filesystem=self._arrow_fs)
                    total_rows += metadata.num_rows
                except Exception as e:
                    self._logger.warning(
                        "Failed to read Parquet metadata",
                        file_path=arrow_path,
                        error=str(e),
                    )
                    raise GCSError(
                        f"Failed to read Parquet file: {e}",
                        gcs_path=f"gs://{arrow_path}",
                    ) from e

            self._logger.info(
                "Counted Parquet rows",
                gcs_path=gcs_path,
                file_count=len(parquet_blobs),
                row_count=total_rows,
                size_bytes=total_size,
            )
            return total_rows, total_size

        except GCSError:
            raise
        except gcp_exceptions.GoogleAPIError as e:
            raise GCSError(
                f"GCS error counting rows: {e}",
                gcs_path=gcs_path,
            ) from e
        except Exception as e:
            raise GCSError(
                f"Failed to count rows: {e}",
                gcs_path=gcs_path,
            ) from e

    def _list_parquet_files(self, bucket_name: str, prefix: str) -> list[str]:
        """List all Parquet files under a prefix.

        Args:
            bucket_name: GCS bucket name
            prefix: Path prefix within bucket

        Returns:
            List of file paths (without gs:// prefix)
        """
        bucket = self._storage_client.bucket(bucket_name)
        blobs = bucket.list_blobs(prefix=prefix)

        # Accept both .parquet files and Trino CTAS output (no extension)
        return [
            blob.name for blob in blobs
            if not blob.name.endswith("/") and blob.size > 0
        ]

    def list_files(self, gcs_path: str) -> list[str]:
        """List all files under a GCS path.

        Args:
            gcs_path: GCS path (gs://bucket/prefix/)

        Returns:
            List of full GCS paths (gs://bucket/path/file)
        """
        bucket_name, prefix = self._parse_gcs_path(gcs_path)
        bucket = self._storage_client.bucket(bucket_name)
        blobs = bucket.list_blobs(prefix=prefix)

        return [f"gs://{bucket_name}/{blob.name}" for blob in blobs]

    def delete_path(self, gcs_path: str) -> int:
        """Delete all files under a GCS path.

        Args:
            gcs_path: GCS path (gs://bucket/prefix/)

        Returns:
            Number of files deleted
        """
        bucket_name, prefix = self._parse_gcs_path(gcs_path)

        self._logger.info("Deleting GCS path", gcs_path=gcs_path)

        bucket = self._storage_client.bucket(bucket_name)
        blobs = list(bucket.list_blobs(prefix=prefix))

        for blob in blobs:
            blob.delete()

        self._logger.info(
            "Deleted GCS path",
            gcs_path=gcs_path,
            files_deleted=len(blobs),
        )
        return len(blobs)

    @staticmethod
    def _parse_gcs_path(gcs_path: str) -> tuple[str, str]:
        """Parse gs://bucket/prefix into (bucket, prefix).

        Args:
            gcs_path: GCS path starting with gs://

        Returns:
            Tuple of (bucket_name, prefix)

        Raises:
            ValueError: If path doesn't start with gs://
        """
        if not gcs_path.startswith("gs://"):
            raise ValueError(f"Invalid GCS path (must start with gs://): {gcs_path}")

        path = gcs_path[5:]  # Remove "gs://"
        parts = path.split("/", 1)
        bucket = parts[0]
        prefix = parts[1] if len(parts) > 1 else ""

        # Remove trailing slash from prefix for listing
        prefix = prefix.rstrip("/")
        if prefix:
            prefix = prefix + "/"

        return bucket, prefix
