---
title: "Export Worker Clients Design"
scope: hsbc
---

<!-- Verified against worker code on 2026-04-20 -->

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

The Starburst client is split into two operations: `submit_unload` (used by the submit phase) and `poll_query` (used by the poll phase). It also offers a **direct-export** pathway (`submit_unload_async`, `execute_and_export_async` + `_write_parquet_to_gcs`) that bypasses Starburst's `system.unload` entirely and writes Parquet to GCS client-side via PyArrow (ADR-071, default in production).

Results are returned as dataclasses (`QuerySubmissionResult`, `QueryPollResult`) — NOT tuples. Split HTTP timeouts per ADR-122 are module-level constants in `starburst.py:28-30` and take priority over any per-request `request_timeout` inside `submit_unload`/`poll_query`.

```python
# src/export_worker/clients/starburst.py
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
from google.cloud import storage
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from export_worker.exceptions import StarburstError

# ADR-122 split timeouts (module-level, override any config.request_timeout)
SUBMIT_TIMEOUT = httpx.Timeout(connect=60, read=300, write=60, pool=60)
POLL_TIMEOUT = httpx.Timeout(connect=10, read=60, write=10, pool=10)


@dataclass
class QuerySubmissionResult:
    query_id: str
    next_uri: str


@dataclass
class QueryPollResult:
    state: str  # RUNNING | FINISHED | FAILED
    next_uri: str | None  # None once FINISHED/FAILED
    error_message: str | None


class StarburstClient:
    def __init__(
        self,
        url: str,
        user: str,
        password: str = "",
        catalog: str = "bigquery",
        schema: str = "public",
        request_timeout: int = 30,
        client_tags: list[str] | None = None,
        source: str = "graph-olap-export-worker",
        gcp_project: str | None = None,
        role: str | None = None,
        ssl_verify: bool = True,
    ) -> None:
        """Initialize Starburst client with explicit kwargs (no single config object).

        Constructor takes 11+ explicit kwargs — callers that previously passed
        a single ``config`` object should use ``StarburstClient.from_config``
        instead (see ``starburst.py:74-114``).
        """
        self.url = url.rstrip("/")
        self.user = user
        self.role = role  # Usually None; per-job role passed to submit/execute methods
        self.ssl_verify = ssl_verify
        self.auth = (user, password) if password else None
        self.catalog = catalog
        self.schema = schema
        self.request_timeout = request_timeout
        self.client_tags = client_tags or ["graph-olap-export"]
        self.source = source
        self.gcp_project = gcp_project

    @classmethod
    def from_config(cls, config, gcp_project: str | None = None) -> "StarburstClient":
        """Build client from pydantic-settings ``StarburstConfig``."""
        client_tags = [tag.strip() for tag in config.client_tags.split(",")]
        return cls(
            url=config.url,
            user=config.user,
            password=config.password.get_secret_value() if config.password else "",
            catalog=config.catalog,
            schema=config.schema_name,
            request_timeout=config.request_timeout_seconds,
            client_tags=client_tags,
            source=config.source,
            gcp_project=gcp_project,
            role=config.role,
            ssl_verify=config.ssl_verify,
        )

    # ---- Sync two-phase API (used by poll-loop fallback) --------------------

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
        catalog: str | None = None,
    ) -> QuerySubmissionResult:
        """Submit a Starburst ``system.unload`` query (fire-and-forget).

        Returns ``QuerySubmissionResult`` (NOT a tuple).
        """
        unload_query = self._build_unload_query(sql, columns, destination)
        effective_catalog = catalog or self.catalog

        with httpx.Client(
            auth=self.auth, timeout=SUBMIT_TIMEOUT, verify=self.ssl_verify
        ) as client:
            response = client.post(
                f"{self.url}/v1/statement",
                content=unload_query,
                headers=self._get_headers(effective_catalog),
            )
            response.raise_for_status()
            result = response.json()
            query_id = result.get("id")
            next_uri = result.get("nextUri")
            if not query_id or not next_uri:
                raise StarburstError("Invalid response from Starburst: missing id/nextUri")
            return QuerySubmissionResult(query_id=query_id, next_uri=next_uri)

    def poll_query(self, next_uri: str) -> QueryPollResult:
        """Poll a running query. Returns ``QueryPollResult`` (NOT a tuple)."""
        with httpx.Client(
            auth=self.auth, timeout=POLL_TIMEOUT, verify=self.ssl_verify
        ) as client:
            response = client.get(next_uri)
            result = response.json()
            if "error" in result:
                return QueryPollResult(
                    state="FAILED",
                    next_uri=None,
                    error_message=result["error"].get("message", "Unknown error"),
                )
            state = result.get("stats", {}).get("state", "UNKNOWN")
            new_next_uri = result.get("nextUri")
            if state in ("FINISHED", "FAILED"):
                return QueryPollResult(
                    state=state,
                    next_uri=None,
                    error_message=(
                        result.get("error", {}).get("message", "Query failed")
                        if state == "FAILED"
                        else None
                    ),
                )
            return QueryPollResult(state="RUNNING", next_uri=new_next_uri, error_message=None)

    # ---- Async API (used by K8s worker) -------------------------------------

    async def submit_unload_async(
        self,
        sql: str,
        columns: list[str],
        destination: str,
        catalog: str | None = None,
        *,
        role: str | None = None,
    ) -> QuerySubmissionResult:
        """Async ``system.unload`` submission — same return type as sync path."""

    async def poll_query_async(self, next_uri: str) -> QueryPollResult:
        """Async poll — same return type as sync path."""

    # ---- Direct export (ADR-071 default) ------------------------------------

    async def execute_and_export_async(
        self,
        sql: str,
        columns: list[str],
        destination: str,
        catalog: str | None = None,
        *,
        role: str | None = None,
    ) -> tuple[int, int]:
        """Execute query synchronously and stream results to GCS as Parquet.

        Default pathway in production (``DIRECT_EXPORT=true``). Issues a
        ``SELECT <quoted cols> FROM (<sql>)`` against Starburst, paginates
        through ``nextUri`` pages, builds a PyArrow table, and calls
        ``_write_parquet_to_gcs`` which writes the table to a local temp
        file with ``compression='snappy'`` and uploads it to GCS via the
        ``google-cloud-storage`` client. Returns ``(row_count, size_bytes)``.
        Temp file is always cleaned up in a ``finally``.
        """

    def _build_unload_query(
        self, sql: str, columns: list[str], destination: str
    ) -> str:
        """Build the ``system.unload`` table-function query.

        NOTE: Uses ``system.unload`` (NOT ``io.unload``) and wraps the source
        query in ``SELECT DISTINCT <quoted-cols>`` to handle reserved words
        in column names — see ``starburst.py:732-758``.
        """
        column_list = ", ".join(f'"{col}"' for col in columns)
        return f"""
SELECT * FROM TABLE(
    system.unload(
        input => TABLE(
            SELECT DISTINCT {column_list}
            FROM ({sql})
        ),
        location => '{destination}',
        format => 'PARQUET',
        compression => 'SNAPPY'
    )
)
""".strip()

    def _get_headers(self, catalog: str) -> dict[str, str]:
        return {
            "X-Trino-User": self.user,
            "X-Trino-Catalog": catalog,
            "X-Trino-Schema": self.schema,
            "X-Trino-Client-Tags": ",".join(self.client_tags),
            "X-Trino-Source": self.source,
            "Content-Type": "text/plain",
        }
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
    def __init__(self, project: str, emulator_host: str | None = None):
        """Initialize GCS client.

        Args:
            project: GCP project ID.
            emulator_host: Optional emulator endpoint (``STORAGE_EMULATOR_HOST``)
                for local/E2E tests using fake-gcs-server. When set, uses
                ``AnonymousCredentials`` and wires PyArrow's ``GcsFileSystem``
                with ``endpoint_override=<host:port>, scheme='http'``.
        """
        if emulator_host:
            # Emulator mode: anonymous credentials + arrow fs endpoint override
            endpoint = (
                emulator_host
                if emulator_host.startswith(("http://", "https://"))
                else f"http://{emulator_host}"
            )
            host_port = endpoint.replace("http://", "").replace("https://", "")
            self.client = storage.Client(
                project=project,
                credentials=AnonymousCredentials(),
                client_options={"api_endpoint": endpoint},
            )
            self._arrow_fs = fs.GcsFileSystem(
                endpoint_override=host_port, scheme="http", anonymous=True
            )
        else:
            self.client = storage.Client(project=project)
            self._arrow_fs = fs.GcsFileSystem()

    @classmethod
    def from_config(cls, config) -> "GCSClient":
        return cls(project=config.project, emulator_host=config.emulator_host)

    @retry(
        retry=retry_if_exception_type((gcp_exceptions.GoogleAPIError,)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
    )
    def calculate_total_size(self, gcs_path: str) -> int:
        """Calculate total size of all files under a GCS path.

        (Renamed from ``calculate_size`` — see ``gcs.py:96``.)
        """
        bucket_name, prefix = self._parse_gcs_path(gcs_path)
        bucket = self.client.bucket(bucket_name)
        blobs = bucket.list_blobs(prefix=prefix)
        return sum(blob.size for blob in blobs)

    @retry(
        retry=retry_if_exception_type((gcp_exceptions.GoogleAPIError,)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
    )
    def count_parquet_rows(self, gcs_path: str) -> tuple[int, int]:
        """Count rows and sum sizes across all Parquet files at a path.

        Returns ``(row_count, size_bytes)`` — NOT just row_count.
        Accepts both ``.parquet`` files and extensionless Trino CTAS output,
        and rejects directory markers / zero-byte blobs. Uses the instance's
        configured ``_arrow_fs`` (which handles the emulator case).
        """
        bucket_name, prefix = self._parse_gcs_path(gcs_path)
        bucket = self.client.bucket(bucket_name)
        blobs = [
            b for b in bucket.list_blobs(prefix=prefix)
            if not b.name.endswith("/") and b.size > 0
        ]
        if not blobs:
            return (0, 0)
        total_size = sum(b.size for b in blobs)
        total_rows = 0
        for blob in blobs:
            metadata = pq.read_metadata(
                f"{bucket_name}/{blob.name}", filesystem=self._arrow_fs
            )
            total_rows += metadata.num_rows
        return (total_rows, total_size)

    def _parse_gcs_path(self, gcs_path: str) -> tuple[str, str]:
        """Parse ``gs://bucket/prefix`` → ``(bucket, prefix)``."""
        if not gcs_path.startswith("gs://"):
            raise ValueError(f"Invalid GCS path: {gcs_path}")
        parts = gcs_path[5:].split("/", 1)
        bucket = parts[0]
        prefix = parts[1] if len(parts) > 1 else ""
        return bucket, prefix
```

### GCS emulator support

The export worker supports the GCS emulator (fake-gcs-server) used in local development and E2E tests. When the `STORAGE_EMULATOR_HOST` environment variable is set (picked up via `GCSConfig.emulator_host` in `config.py:60-64`), `GCSClient.__init__`:

- Instantiates `storage.Client` with `AnonymousCredentials` and `client_options={"api_endpoint": endpoint}`.
- Wires PyArrow's `GcsFileSystem(endpoint_override=<host:port>, scheme="http", anonymous=True)` so that `pq.read_metadata(...)` calls route to the emulator instead of production GCS.

This is the single load path for production, local dev, and E2E — there is no production-only code branch.

---

## Control Plane Client

Handles job claiming, status updates, and poll scheduling for the stateless export workers. See [ADR-25](--/process/adr/system-design/adr-025-export-worker-architecture-simplification.md) for architecture details.

Per ADR-104 there is NO `google.oauth2.id_token` or `Authorization: Bearer …` — service-to-service calls within the cluster use plain HTTP with a single `X-Component: worker` header. All methods are **synchronous** (no `async`/`await`).

```python
# src/export_worker/clients/control_plane.py
from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from export_worker.exceptions import ControlPlaneError
from export_worker.models import ExportJob, SnapshotJobsResult


class ControlPlaneClient:
    def __init__(self, base_url: str, timeout: int = 30, max_retries: int = 5) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    @classmethod
    def from_config(cls, config) -> "ControlPlaneClient":
        return cls(
            base_url=config.url,
            timeout=config.timeout_seconds,
            max_retries=config.max_retries,
        )

    def _get_headers(self) -> dict[str, str]:
        # ADR-104: plain HTTP within cluster, no bearer token
        return {"Content-Type": "application/json", "X-Component": "worker"}

    # --- Snapshot Operations ---

    def update_snapshot_status(
        self,
        snapshot_id: int,
        status: str,
        *,
        progress=None,
        size_bytes: int | None = None,
        node_counts: dict[str, int] | None = None,
        edge_counts: dict[str, int] | None = None,
        error_message: str | None = None,
        failed_step: str | None = None,
    ) -> None:
        """PATCH ``/api/internal/snapshots/{id}/status`` — full field set."""

    def update_snapshot_status_if_pending(
        self, snapshot_id: int, status: str
    ) -> None:
        """Compare-and-swap: only updates if current status is ``pending``.

        Used by the submit phase to idempotently promote the parent
        snapshot to ``creating`` on the first job of the batch.
        """

    def finalize_snapshot(
        self,
        snapshot_id: int,
        *,
        success: bool,
        node_counts: dict[str, int] | None = None,
        edge_counts: dict[str, int] | None = None,
        size_bytes: int | None = None,
        error_message: str | None = None,
    ) -> None:
        """Mark snapshot as ``ready`` / ``failed`` with aggregated counts."""

    # --- Export Job Claiming (ADR-025) ---

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        stop=stop_after_attempt(5),
        wait=wait_fixed(1),
    )
    def claim_export_jobs(self, worker_id: str, limit: int = 10) -> list[ExportJob]:
        """Atomically claim pending export jobs for this worker.

        (Renamed from ``claim_jobs`` — see ``control_plane.py:610``.)
        Server uses ``SELECT ... FOR UPDATE SKIP LOCKED`` to avoid races.
        """

    def get_pollable_export_jobs(self, limit: int = 10) -> list[ExportJob]:
        """Get submitted jobs where ``next_poll_at <= now``.

        (Renamed from ``get_pollable_jobs`` — see ``control_plane.py:669``.)
        Takes a ``limit`` parameter (default 10) to control batch size.
        """

    # --- Export Job Status Updates ---

    def update_export_job(
        self,
        job_id: int,
        *,
        status: str | None = None,
        next_uri: str | None = None,
        row_count: int | None = None,
        size_bytes: int | None = None,
        completed_at: str | None = None,
        error_message: str | None = None,
        starburst_query_id: str | None = None,
        next_poll_at: str | None = None,
        poll_count: int | None = None,
        submitted_at: str | None = None,
    ) -> None:
        """PATCH ``/api/internal/export-jobs/{id}`` with any subset of fields."""

    # --- Snapshot aggregation (race-safe) ---

    def get_snapshot_jobs_result(
        self,
        snapshot_id: int,
        updated_job: ExportJob | None = None,
    ) -> SnapshotJobsResult:
        """Check status of all export jobs for a snapshot.

        If ``updated_job`` is passed, its state overrides whatever the
        server returned for that same job ID — this avoids a classic race
        where the just-completed job appears stale in the aggregated fetch
        (see ``control_plane.py:721-786``).
        """
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
| `RetryableError` | Raise exception | The main asyncio loop in `worker.py` (a `while not self._shutdown_event.is_set():` polling loop) retries on the next iteration after the configured sleep interval. There is no APScheduler dependency. |
| `PermanentError` | Update status to failed, return normally | No retry (job marked failed) |
| Unexpected | Raise exception | The main asyncio loop in `worker.py` (a `while not self._shutdown_event.is_set():` polling loop) retries on the next iteration after the configured sleep interval. There is no APScheduler dependency. |

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
