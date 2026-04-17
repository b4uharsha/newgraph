"""GCS client for downloading Parquet files."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import structlog
from google.cloud import storage
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from wrapper.exceptions import GCSDownloadError

logger = structlog.get_logger(__name__)


class GCSClient:
    """Client for Google Cloud Storage operations.

    Handles downloading Parquet files from GCS with retry logic and
    proper error handling.
    """

    def __init__(self) -> None:
        """Initialize GCS client."""
        self._client = storage.Client()
        logger.info("gcs_client_initialized")

    @retry(
        retry=retry_if_exception_type((Exception,)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def download_file(
        self,
        gcs_path: str,
        local_path: Path,
    ) -> None:
        """Download a file from GCS to local filesystem.

        Args:
            gcs_path: GCS path (gs://bucket/path/to/file)
            local_path: Local destination path

        Raises:
            ValueError: If GCS path is invalid
            Exception: If download fails after retries
        """
        if not gcs_path.startswith("gs://"):
            raise ValueError(f"Invalid GCS path: {gcs_path}")

        # Parse GCS path
        path_parts = gcs_path[5:].split("/", 1)
        if len(path_parts) != 2:
            raise ValueError(f"Invalid GCS path format: {gcs_path}")

        bucket_name, blob_name = path_parts

        logger.info(
            "downloading_from_gcs",
            bucket=bucket_name,
            blob=blob_name,
            local_path=str(local_path),
        )

        # Ensure parent directory exists
        local_path.parent.mkdir(parents=True, exist_ok=True)

        # Download in thread pool (GCS client is synchronous)
        await asyncio.to_thread(
            self._download_blob,
            bucket_name,
            blob_name,
            local_path,
        )

        logger.info(
            "download_complete",
            gcs_path=gcs_path,
            size_bytes=local_path.stat().st_size,
        )

    def _download_blob(
        self,
        bucket_name: str,
        blob_name: str,
        local_path: Path,
    ) -> None:
        """Download blob (synchronous, runs in thread pool)."""
        bucket = self._client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.download_to_filename(str(local_path))

    async def list_files(
        self,
        gcs_prefix: str,
    ) -> list[str]:
        """List files in GCS with given prefix.

        Args:
            gcs_prefix: GCS prefix (gs://bucket/path/to/dir/)

        Returns:
            List of GCS paths
        """
        if not gcs_prefix.startswith("gs://"):
            raise ValueError(f"Invalid GCS prefix: {gcs_prefix}")

        # Parse GCS prefix
        path_parts = gcs_prefix[5:].split("/", 1)
        bucket_name = path_parts[0]
        prefix = path_parts[1] if len(path_parts) > 1 else ""

        logger.info("listing_gcs_files", bucket=bucket_name, prefix=prefix)

        # List blobs in thread pool
        blobs = await asyncio.to_thread(
            self._list_blobs,
            bucket_name,
            prefix,
        )

        gcs_paths = [f"gs://{bucket_name}/{blob.name}" for blob in blobs]

        logger.info("gcs_files_listed", count=len(gcs_paths))

        return gcs_paths

    def _list_blobs(self, bucket_name: str, prefix: str) -> list[Any]:
        """List blobs (synchronous, runs in thread pool)."""
        bucket = self._client.bucket(bucket_name)
        return list(bucket.list_blobs(prefix=prefix))

    async def download_snapshot_data(
        self,
        gcs_base_path: str,
    ) -> list[Path]:
        """Download all snapshot data files (nodes and edges).

        Args:
            gcs_base_path: GCS base path to snapshot data (gs://bucket/snapshot-123)

        Returns:
            List of local file paths to downloaded Parquet files

        Raises:
            GCSDownloadError: If download fails
        """
        logger.info("downloading_snapshot_data", gcs_path=gcs_base_path)

        try:
            # List all files in the snapshot
            all_files = await self.list_files(gcs_base_path)

            # Download each file
            local_files: list[Path] = []
            for gcs_path in all_files:
                # Extract filename from GCS path
                filename = Path(gcs_path).name
                local_path = Path(f"/tmp/{filename}")

                # Download file
                await self.download_file(gcs_path, local_path)
                local_files.append(local_path)

            logger.info(
                "snapshot_data_downloaded",
                file_count=len(local_files),
            )

            return local_files

        except Exception as e:
            logger.error(
                "snapshot_download_failed",
                error=str(e),
                gcs_path=gcs_base_path,
            )
            raise GCSDownloadError(
                gcs_path=gcs_base_path,
                error=str(e),
            ) from e
