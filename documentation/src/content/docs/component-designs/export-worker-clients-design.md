---
title: "Export Worker Clients Design"
scope: hsbc
---

# Export Worker Clients Design

External client implementations for the Export Worker including Starburst (with resource group integration), GCS, and Control Plane claim/poll integrations.

## Prerequisites

- [export-worker.design.md](-/export-worker.design.md) - Core export worker architecture and flow
- [api.internal.spec.md](--/system-design/api/api.internal.spec.md) - Internal API for Control Plane communication
- [data-pipeline.reference.md](--/reference/data-pipeline.reference.md) - Starburst UNLOAD syntax and Parquet format

## Related Components

- [control-plane.services.design.md](-/control-plane.services.design.md) - Receives status updates from export worker
- [system.architecture.design.md](--/system-design/system.architecture.design.md) - Overall data flow

---

## Starburst Client

The Starburst client is split into two operations: `submit_unload` (used by Submitter) and `poll_query` (used by Poller).

```python
# src/export_worker/clients/starburst.py
from __future__ import annotations

from dataclasses import dataclass

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from export_worker.exceptions import StarburstError


@dataclass
class StarburstConfig:
    url: str
    user: str
    password: str
    schema: str = "public"


class StarburstClient:
    def __init__(self, config: StarburstConfig):
        self.url = config.url
        self.auth = (config.user, config.password)
        self.schema = config.schema

    @classmethod
    def from_config(cls, config: StarburstConfig) -> StarburstClient:
        return cls(config)

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
    )
    def submit_unload(
        self,
        sql: str,
        columns: list[str],
        destination: str,
        catalog: str,
        client_tags: list[str] | None = None,
    ) -> tuple[str, str]:
        """
        Submit an UNLOAD query to Starburst (fire-and-forget).

        Uses client_tags to route queries to the appropriate Starburst resource group.
        The 'graph-olap-export' tag routes to a dedicated resource group that limits
        concurrent exports server-side. See ADR-025 for architecture details.

        Args:
            sql: The SELECT query to export
            columns: Column names for the Parquet output
            destination: GCS path for Parquet files
            catalog: Starburst catalog name
            client_tags: Tags for resource group routing (default: ['graph-olap-export'])

        Returns:
            Tuple of (query_id, next_uri) for subsequent polling.

        Raises:
            StarburstError: If submission fails.
        """
        unload_query = self._build_unload_query(sql, columns, destination)
        tags = client_tags or ["graph-olap-export"]

        with httpx.Client(auth=self.auth, timeout=30.0) as client:
            response = client.post(
                f"{self.url}/v1/statement",
                content=unload_query,
                headers={
                    "X-Trino-Catalog": catalog,
                    "X-Trino-Schema": self.schema,
                    "X-Trino-Client-Tags": ",".join(tags),  # Resource group routing
                },
            )
            response.raise_for_status()
            result = response.json()

            query_id = result.get("id")
            next_uri = result.get("nextUri")

            if not query_id or not next_uri:
                raise StarburstError(f"Invalid response from Starburst: {result}")

            return query_id, next_uri

    def poll_query(self, next_uri: str) -> tuple[str, str | None, str | None]:
        """
        Poll a running Starburst query for status.

        Args:
            next_uri: The nextUri from previous response.

        Returns:
            Tuple of (state, next_uri, error_message).
            - state: 'RUNNING', 'FINISHED', or 'FAILED'
            - next_uri: URI for next poll (if still running)
            - error_message: Error details (if failed)
        """
        with httpx.Client(auth=self.auth, timeout=10.0) as client:
            response = client.get(next_uri)
            result = response.json()

            # Check for error in response
            if "error" in result:
                error_msg = result["error"].get("message", "Unknown error")
                return "FAILED", None, error_msg

            state = result.get("stats", {}).get("state", "UNKNOWN")
            new_next_uri = result.get("nextUri")

            if state == "FINISHED":
                return "FINISHED", None, None
            elif state == "FAILED":
                error_msg = result.get("error", {}).get("message", "Query failed")
                return "FAILED", None, error_msg
            else:
                # QUEUED, PLANNING, STARTING, RUNNING, FINISHING
                return "RUNNING", new_next_uri, None

    def _build_unload_query(self, sql: str, columns: list[str], destination: str) -> str:
        """Build the UNLOAD table function query."""
        column_list = ", ".join(columns)

        return f"""
            SELECT * FROM TABLE(
                io.unload(
                    input => TABLE(
                        SELECT {column_list}
                        FROM ({sql})
                    ),
                    location => '{destination}',
                    format => 'PARQUET',
                    compression => 'SNAPPY'
                )
            )
        """
```

---

## GCS Client

```python
# src/export_worker/clients/gcs.py
from google.api_core import exceptions as gcp_exceptions
from google.cloud import storage
from pyarrow import fs
import pyarrow.parquet as pq
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from export_worker.exceptions import GCSError


class GCSClient:
    def __init__(self, project: str):
        self.client = storage.Client(project=project)

    @retry(
        retry=retry_if_exception_type((gcp_exceptions.GoogleAPIError,)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
    )
    def calculate_size(self, gcs_path: str) -> int:
        """Calculate total size of all files under a GCS path."""
        bucket_name, prefix = self._parse_gcs_path(gcs_path)
        bucket = self.client.bucket(bucket_name)
        blobs = bucket.list_blobs(prefix=prefix)
        return sum(blob.size for blob in blobs)

    @retry(
        retry=retry_if_exception_type((gcp_exceptions.GoogleAPIError,)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
    )
    def count_parquet_rows(self, gcs_path: str) -> int:
        """Count total rows across all Parquet files at path."""
        bucket_name, prefix = self._parse_gcs_path(gcs_path)
        gcs_fs = fs.GcsFileSystem()
        path = f"{bucket_name}/{prefix}"

        total_rows = 0
        try:
            file_info = gcs_fs.get_file_info(fs.FileSelector(path, recursive=True))

            for info in file_info:
                if info.path.endswith(".parquet"):
                    metadata = pq.read_metadata(info.path, filesystem=gcs_fs)
                    total_rows += metadata.num_rows
        except Exception as e:
            raise GCSError(f"Failed to count rows at {gcs_path}: {e}") from e

        return total_rows

    def _parse_gcs_path(self, gcs_path: str) -> tuple[str, str]:
        """Parse gs://bucket/prefix into (bucket, prefix)."""
        if not gcs_path.startswith("gs://"):
            raise ValueError(f"Invalid GCS path: {gcs_path}")

        path = gcs_path[5:]  # Remove "gs://"
        parts = path.split("/", 1)
        bucket = parts[0]
        prefix = parts[1] if len(parts) > 1 else ""
        return bucket, prefix
```

---

## Control Plane Client

Handles job claiming, status updates, and poll scheduling for the stateless export workers. See [ADR-25](--/process/adr/system-design/adr-025-export-worker-architecture-simplification.md) for architecture details.

```python
# src/export_worker/clients/control_plane.py
from __future__ import annotations

import httpx
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from export_worker.exceptions import ControlPlaneError
from export_worker.models import ExportJob


class ControlPlaneClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._token: str | None = None

    def _get_token(self) -> str:
        """Get ID token for service-to-service auth."""
        if self._token is None:
            self._token = id_token.fetch_id_token(Request(), self.base_url)
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "X-Component": "worker",
            "Content-Type": "application/json",
        }

    # --- Snapshot Operations ---

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        stop=stop_after_attempt(5),
        wait=wait_fixed(1),
    )
    def update_snapshot_status(
        self,
        snapshot_id: str,
        status: str,
        size_bytes: int | None = None,
        node_counts: dict | None = None,
        edge_counts: dict | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update snapshot status in Control Plane."""
        url = f"{self.base_url}/api/internal/snapshots/{snapshot_id}/status"

        body = {"status": status}
        if size_bytes is not None:
            body["size_bytes"] = size_bytes
        if node_counts is not None:
            body["node_counts"] = node_counts
        if edge_counts is not None:
            body["edge_counts"] = edge_counts
        if error_message is not None:
            body["error_message"] = error_message

        with httpx.Client() as client:
            response = client.put(url, json=body, headers=self._headers())

            if response.status_code != 200:
                raise ControlPlaneError(
                    f"Failed to update snapshot: {response.status_code} {response.text}"
                )

    # --- Export Job Claiming ---

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        stop=stop_after_attempt(5),
        wait=wait_fixed(1),
    )
    def claim_jobs(self, worker_id: str, limit: int = 10) -> list[ExportJob]:
        """
        Atomically claim pending export jobs for this worker.

        The Control Plane uses SELECT ... FOR UPDATE SKIP LOCKED to prevent
        race conditions between multiple workers.

        Args:
            worker_id: Unique identifier for this worker (pod name)
            limit: Maximum number of jobs to claim (default: 10)

        Returns:
            List of claimed jobs with SQL, columns, and GCS path
        """
        url = f"{self.base_url}/api/internal/export-jobs/claim"

        body = {"worker_id": worker_id, "limit": limit}

        with httpx.Client() as client:
            response = client.post(url, json=body, headers=self._headers())

            if response.status_code != 200:
                raise ControlPlaneError(
                    f"Failed to claim jobs: {response.status_code} {response.text}"
                )

            return [ExportJob.from_dict(j) for j in response.json()["data"]["jobs"]]

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
    )
    def get_pollable_jobs(self) -> list[ExportJob]:
        """
        Get submitted jobs that are ready to poll.

        Returns jobs where status='submitted' and next_poll_at <= now.
        Used for stateless polling - worker doesn't track state in memory.
        """
        url = f"{self.base_url}/api/internal/export-jobs/pollable"

        with httpx.Client() as client:
            response = client.get(url, headers=self._headers())

            if response.status_code != 200:
                raise ControlPlaneError(
                    f"Failed to get pollable jobs: {response.status_code} {response.text}"
                )

            return [ExportJob.from_dict(j) for j in response.json()["data"]["jobs"]]

    # --- Export Job Status Updates ---

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
    )
    def get_export_jobs(
        self,
        snapshot_id: str,
        status: str | None = None,
    ) -> list[ExportJob]:
        """Get export jobs for a snapshot, optionally filtered by status."""
        url = f"{self.base_url}/api/internal/snapshots/{snapshot_id}/export-jobs"
        params = {}
        if status:
            params["status"] = status

        with httpx.Client() as client:
            response = client.get(url, params=params, headers=self._headers())

            if response.status_code != 200:
                raise ControlPlaneError(
                    f"Failed to get export jobs: {response.status_code} {response.text}"
                )

            return [ExportJob.from_dict(j) for j in response.json()["data"]["jobs"]]

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        stop=stop_after_attempt(5),
        wait=wait_fixed(1),
    )
    def update_export_job(
        self,
        job_id: int,
        status: str | None = None,
        next_uri: str | None = None,
        row_count: int | None = None,
        size_bytes: int | None = None,
        completed_at: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update an export job record."""
        url = f"{self.base_url}/api/internal/export-jobs/{job_id}"

        body = {}
        if status is not None:
            body["status"] = status
        if next_uri is not None:
            body["next_uri"] = next_uri
        if row_count is not None:
            body["row_count"] = row_count
        if size_bytes is not None:
            body["size_bytes"] = size_bytes
        if completed_at is not None:
            body["completed_at"] = completed_at
        if error_message is not None:
            body["error_message"] = error_message

        with httpx.Client() as client:
            response = client.patch(url, json=body, headers=self._headers())

            if response.status_code != 200:
                raise ControlPlaneError(
                    f"Failed to update export job: {response.status_code} {response.text}"
                )
```

---

## Error Handling

### Exception Hierarchy

```python
# src/exceptions.py

class ExportWorkerError(Exception):
    """Base exception for export worker."""
    pass


class RetryableError(ExportWorkerError):
    """Error that should trigger a retry (transient failures)."""
    pass


class PermanentError(ExportWorkerError):
    """Error that should NOT be retried (snapshot marked as failed)."""
    pass


class StarburstError(PermanentError):
    """Starburst query or connection error."""
    pass


class GCSError(PermanentError):
    """GCS operation error."""
    pass


class ControlPlaneError(RetryableError):
    """Control Plane API error (typically transient)."""
    pass
```

### Error Handling Strategy

| Error Type | Action | Worker Behavior |
|------------|--------|-----------------|
| `RetryableError` | Raise exception | APScheduler retries on next loop iteration |
| `PermanentError` | Update status to failed, return normally | No retry (job marked failed) |
| Unexpected | Raise exception | APScheduler retries on next loop iteration |

### Retry Configuration

From [architectural.guardrails.md](--/foundation/architectural.guardrails.md):

| Operation | Max Retries | Backoff |
|-----------|-------------|---------|
| Starburst query submission | 3 | Exponential (1s, 2s, 4s) |
| Export polling | Unlimited | Fibonacci (2s→90s cap) |
| Status update to CP | 5 | Fixed (1s) |
| GCS operations | 3 | Exponential (500ms, 1s, 2s) |

---

## Observability

### Structured Logging

```python
import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)

logger = structlog.get_logger()

# Usage
logger.info(
    "Processing snapshot",
    snapshot_id="123",
    mapping_id="45",
    node_count=3,
    edge_count=2,
)
```

### Metrics

The export worker (Kubernetes Deployment) emits custom metrics via Prometheus / Cloud Monitoring:

```python
from google.cloud import monitoring_v3

# Export duration histogram
# Node/edge export counts
# Error counts by type
```

### Alerting

| Condition | Severity | Action |
|-----------|----------|--------|
| Error rate > 10% in 5 min | Critical | Page on-call |
| Execution time > 50 min | Warning | Review query performance |
| Failed job count > 0 | Warning | Investigate failed exports |
