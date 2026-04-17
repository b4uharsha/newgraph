"""Instance connection for queries and algorithms."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from graph_olap.exceptions import (
    exception_from_response,
)
from graph_olap.instance.algorithms import AlgorithmManager, NetworkXManager
from graph_olap.models.common import QueryResult, Schema
from graph_olap.models.instance import LockStatus


class InstanceConnection:
    """Connection to a running graph instance.

    Provides methods for:
    - Cypher query execution with multiple return formats
    - Native Ryugraph algorithms (pagerank, connected_components, etc.)
    - NetworkX algorithms (any of 500+ algorithms)
    - Schema inspection
    - Lock status monitoring

    Example:
        >>> conn = client.instances.connect(instance_id)

        >>> # Query with DataFrame result
        >>> df = conn.query_df("MATCH (n:Customer) RETURN n.name, n.age LIMIT 100")

        >>> # Query with auto-visualization
        >>> result = conn.query("MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 50")
        >>> result.show()

        >>> # Run PageRank algorithm
        >>> conn.algo.pagerank(node_label="Customer", property_name="pr_score")

        >>> # Run any NetworkX algorithm
        >>> conn.networkx.run("betweenness_centrality", node_label="Customer")
    """

    def __init__(
        self,
        instance_url: str,
        instance_id: int | None = None,
        username: str = "analyst_alice@e2e.local",
        timeout: float = 60.0,
        name: str | None = None,
        status: str | None = None,
        snapshot_id: int | None = None,
        use_case_id: str | None = None,
        proxy: str | None = None,
        verify: bool = True,
    ):
        """Initialize instance connection.

        Args:
            instance_url: URL of the running instance (wrapper service)
            instance_id: Instance ID for reference
            username: Username for X-Username header
            timeout: Query timeout in seconds
            name: Instance name (optional, for reference)
            status: Instance status (optional, for reference)
            snapshot_id: Snapshot ID (optional, for reference)
            use_case_id: Use case ID for X-Use-Case-Id header (ADR-102)
            proxy: HTTP proxy URL
            verify: Whether to verify SSL certificates
        """
        self.instance_url = instance_url.rstrip("/")
        self.instance_id = instance_id
        self._instance_name = name
        self._instance_status = status
        self._instance_snapshot_id = snapshot_id
        self._timeout = timeout

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Username": username,
        }
        if use_case_id:
            headers["X-Use-Case-Id"] = use_case_id

        client_kwargs: dict = {
            "base_url": self.instance_url,
            "headers": headers,
            "timeout": httpx.Timeout(timeout),
            "verify": verify,
        }
        if proxy:
            client_kwargs["proxy"] = proxy

        self._client = httpx.Client(**client_kwargs)

        # Algorithm managers
        self.algo = AlgorithmManager(self._client)
        self.networkx = NetworkXManager(self._client)

    @property
    def id(self) -> int | None:
        """Get instance ID.

        Returns:
            Instance ID or None if not set
        """
        return self.instance_id

    @property
    def name(self) -> str | None:
        """Get instance name.

        Returns:
            Instance name or None if not set
        """
        return self._instance_name

    @property
    def snapshot_id(self) -> int | None:
        """Get snapshot ID.

        Returns:
            Snapshot ID or None if not set
        """
        return self._instance_snapshot_id

    @property
    def current_status(self) -> str | None:
        """Get cached instance status string.

        Returns:
            Cached status string (e.g., "running", "starting") or None if not set

        Note:
            For live status and resource usage, call the status() method instead.
        """
        return self._instance_status

    def close(self) -> None:
        """Close the connection."""
        self._client.close()

    def __enter__(self) -> InstanceConnection:
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()

    def query(
        self,
        cypher: str,
        parameters: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
        coerce_types: bool = True,
    ) -> QueryResult:
        """Execute a Cypher query.

        Args:
            cypher: Cypher query string
            parameters: Query parameters
            timeout: Override default timeout (seconds)
            coerce_types: Convert DATE/TIMESTAMP to Python types

        Returns:
            QueryResult with multiple format options

        Raises:
            RyugraphError: If query fails
            QueryTimeoutError: If query times out

        Example:
            >>> result = conn.query("MATCH (n:Customer) RETURN n.name, n.age")
            >>> df = result.to_polars()
            >>> for row in result:
            ...     print(row["name"])
        """
        body: dict[str, Any] = {"query": cypher}
        if parameters:
            body["parameters"] = parameters
        if timeout:
            body["timeout_ms"] = int(timeout * 1000)  # Convert to milliseconds

        response = self._request("POST", "/query", json=body)
        # Wrapper API returns QueryResponse directly (no 'data' wrapper)
        return QueryResult.from_api_response(response, coerce_types=coerce_types)

    def query_df(
        self,
        cypher: str,
        parameters: dict[str, Any] | None = None,
        *,
        backend: str = "polars",
    ) -> Any:
        """Execute query and return DataFrame directly.

        Args:
            cypher: Cypher query string
            parameters: Query parameters
            backend: DataFrame backend ("polars" or "pandas")

        Returns:
            polars.DataFrame or pandas.DataFrame

        Example:
            >>> df = conn.query_df("MATCH (n) RETURN n.name, n.value")
            >>> df.filter(pl.col("value") > 100)
        """
        result = self.query(cypher, parameters)
        if backend == "pandas":
            return result.to_pandas()
        return result.to_polars()

    def query_scalar(
        self,
        cypher: str,
        parameters: dict[str, Any] | None = None,
    ) -> Any:
        """Execute query and return single scalar value.

        Args:
            cypher: Cypher query returning single value
            parameters: Query parameters

        Returns:
            Single value (int, float, str, etc.)

        Raises:
            ValueError: If query returns multiple rows/columns

        Example:
            >>> count = conn.query_scalar("MATCH (n:Customer) RETURN count(n)")
        """
        result = self.query(cypher, parameters)
        return result.scalar()

    def query_one(
        self,
        cypher: str,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Execute query and return single row as dict.

        Args:
            cypher: Cypher query returning single row
            parameters: Query parameters

        Returns:
            Dict of column->value, or None if no results

        Example:
            >>> customer = conn.query_one(
            ...     "MATCH (c:Customer {id: $id}) RETURN c.*",
            ...     {"id": "C001"}
            ... )
        """
        result = self.query(cypher, parameters)
        if result.row_count == 0:
            return None
        return dict(zip(result.columns, result.rows[0], strict=True))

    def get_schema(self) -> Schema:
        """Get graph schema (node labels, relationship types, properties).

        Returns:
            Schema object with node_labels and relationship_types

        Example:
            >>> schema = conn.get_schema()
            >>> print(schema.node_labels)
            >>> for label, props in schema.node_labels.items():
            ...     print(f"{label}: {props}")
        """
        response = self._request("GET", "/schema")
        # Wrapper API returns SchemaResponse directly (no 'data' wrapper)
        return Schema.from_api_response(response)

    def get_lock(self) -> LockStatus:
        """Get current lock status.

        Returns:
            LockStatus with lock information

        Example:
            >>> lock = conn.get_lock()
            >>> if lock.locked:
            ...     print(f"Locked by {lock.holder_name} running {lock.algorithm}")
        """
        response = self._request("GET", "/lock")
        # Wrapper API returns LockStatusResponse with 'lock' field directly
        return LockStatus.from_api_response(response.get("lock", response))

    def status(self) -> dict[str, Any]:
        """Get instance status and resource usage.

        Returns:
            Dict with memory_usage, disk_usage, uptime, lock_status
        """
        response = self._request("GET", "/status")
        # Wrapper API returns StatusResponse directly (no 'data' wrapper)
        return response

    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.ReadTimeout)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make HTTP request to instance (with automatic retry).

        Retries on transient network errors (max 3 attempts with exponential backoff):
        - Connection refused (pod restarting during reconciliation)
        - Read timeout (slow network, pod startup delays)

        Args:
            method: HTTP method
            path: Request path
            **kwargs: Additional request arguments

        Returns:
            Response JSON

        Raises:
            GraphOLAPError: On error response
            httpx.ConnectError: After 3 failed connection attempts
            httpx.ReadTimeout: After 3 timeout attempts
        """
        response = self._client.request(method, path, **kwargs)

        if response.status_code in (200, 201, 202):
            return response.json()

        # Handle error - try multiple response formats
        error_code = None
        message = None
        details = {}

        try:
            error_data = response.json()

            # Format 1: {"error": {"code": ..., "message": ..., "details": ...}}
            if "error" in error_data and isinstance(error_data["error"], dict):
                error_code = error_data["error"].get("code")
                message = error_data["error"].get("message")
                details = error_data["error"].get("details", {})

            # Format 2: FastAPI HTTPException {"detail": "..."}
            elif "detail" in error_data:
                detail = error_data["detail"]
                if isinstance(detail, str):
                    message = detail
                elif isinstance(detail, dict):
                    error_code = detail.get("code")
                    message = detail.get("message") or str(detail)
                else:
                    message = str(detail)

            # Format 3: {"message": "..."} or {"error": "..."}
            elif "message" in error_data:
                message = error_data["message"]
            elif "error" in error_data and isinstance(error_data["error"], str):
                message = error_data["error"]

            # Fallback: stringify the entire response
            if not message:
                message = str(error_data)

        except Exception:
            # JSON parsing failed - use raw response text
            message = response.text or f"HTTP {response.status_code}"

        # Always include status code in message for context
        if message and not message.startswith(f"HTTP {response.status_code}"):
            message = f"HTTP {response.status_code}: {message}"

        raise exception_from_response(
            status_code=response.status_code,
            error_code=error_code,
            message=message,
            details=details,
        )
