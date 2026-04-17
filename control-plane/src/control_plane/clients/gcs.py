"""Google Cloud Storage client for snapshot cleanup operations.

This client handles deletion of GCS paths when snapshots are deleted.
"""

from __future__ import annotations

import structlog
from google.api_core import exceptions as gcp_exceptions
from google.cloud import storage
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger()


class GCSClient:
    """Client for GCS deletion operations."""

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
            if emulator_host.startswith("http://") or emulator_host.startswith("https://"):
                endpoint = emulator_host
            else:
                endpoint = f"http://{emulator_host}"

            self._storage_client = storage.Client(
                project=project,
                credentials=AnonymousCredentials(),
                client_options={"api_endpoint": endpoint},
            )
            self._logger.info("Using GCS emulator", endpoint=endpoint)
        else:
            self._storage_client = storage.Client(project=project)

    @retry(
        retry=retry_if_exception_type((gcp_exceptions.GoogleAPIError,)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
    )
    def delete_path(self, gcs_path: str) -> tuple[int, int]:
        """Delete all files under a GCS path.

        Args:
            gcs_path: GCS path (gs://bucket/prefix/)

        Returns:
            Tuple of (files_deleted, bytes_deleted)

        Raises:
            Exception: If deletion fails after retries
        """
        bucket_name, prefix = self._parse_gcs_path(gcs_path)

        self._logger.info("Deleting GCS path", gcs_path=gcs_path)

        try:
            bucket = self._storage_client.bucket(bucket_name)
            blobs = list(bucket.list_blobs(prefix=prefix))

            files_deleted = 0
            bytes_deleted = 0

            for blob in blobs:
                bytes_deleted += blob.size
                blob.delete()
                files_deleted += 1

            self._logger.info(
                "Deleted GCS path",
                gcs_path=gcs_path,
                files_deleted=files_deleted,
                bytes_deleted=bytes_deleted,
            )
            return files_deleted, bytes_deleted

        except gcp_exceptions.GoogleAPIError as e:
            self._logger.error(
                "Failed to delete GCS path",
                gcs_path=gcs_path,
                error=str(e),
            )
            raise

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

        # Ensure prefix has trailing slash for directory deletion
        if prefix and not prefix.endswith("/"):
            prefix = prefix + "/"

        return bucket, prefix


def build_gcs_client_from_settings(settings) -> GCSClient | None:
    """Construct a GCSClient from application settings.

    Returns None when GCS is not configured (either ``gcp_project`` or
    ``gcs_bucket`` is unset) — this is the expected state for unit tests
    and minimal local runs.

    Returns None and logs a WARN when GCS *is* configured but the client
    cannot be constructed (e.g. Workload Identity not wired, GSA missing
    storage.objectAdmin on the bucket, metadata server unreachable). The
    earlier behavior here was to raise RuntimeError, which propagated up
    through every FastAPI dependency that called this helper and turned
    every instance API request into a 500 — including wrapper-create. In
    HSBC's environment we cannot verify or fix the underlying credential
    chain from code, so making this fatal locked the entire control-plane
    out of service. Returning None instead lets the cascade-delete and
    lifecycle TTL paths handle the missing client gracefully (they each
    log ``cascade_snapshot_gcs_delete_skipped_no_client`` /
    ``lifecycle_snapshot_gcs_delete_skipped_no_client`` and proceed with
    the DB delete) and unblocks the rest of the API.

    The cost: GCS objects orphaned by cascade or TTL deletes will not be
    cleaned up until either (a) the credential chain is fixed and this
    helper starts returning a real client again, or (b) the bucket-level
    lifecycle rule reaps them. Operators should treat
    ``build_gcs_client_failed`` log entries as a real defect to chase
    down — it means application-level GCS cleanup is silently disabled.
    """
    if not (settings.gcs_bucket and settings.gcp_project):
        return None
    try:
        return GCSClient(
            project=settings.gcp_project,
            emulator_host=settings.gcs_emulator_host or None,
        )
    except Exception as e:
        logger.warning(
            "build_gcs_client_failed",
            gcp_project=settings.gcp_project,
            gcs_bucket=settings.gcs_bucket,
            error_type=type(e).__name__,
            error=str(e),
            consequence="cascade and TTL snapshot deletes will skip GCS cleanup; "
                        "DB rows still removed; bucket lifecycle is the only backstop",
        )
        return None
