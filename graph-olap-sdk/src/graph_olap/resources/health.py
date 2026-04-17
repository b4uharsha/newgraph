"""Health check resource."""

from __future__ import annotations

from typing import TYPE_CHECKING

from graph_olap.models.ops import HealthStatus

if TYPE_CHECKING:
    from graph_olap.http import HTTPClient


class HealthResource:
    """Health check operations.

    Provides access to basic health and readiness endpoints.
    These endpoints do not require authentication.

    Example:
        >>> client = GraphOLAPClient(api_url=api_url, username="user@example.com")

        >>> # Basic health check
        >>> health = client.health.check()
        >>> print(health.status)

        >>> # Readiness check (includes database)
        >>> ready = client.health.ready()
        >>> print(f"Status: {ready.status}, DB: {ready.database}")
    """

    def __init__(self, http: HTTPClient):
        """Initialize health resource.

        Args:
            http: HTTP client for API requests
        """
        self._http = http

    def check(self) -> HealthStatus:
        """Basic health check.

        Returns simple health status without checking dependencies.
        No authentication required.

        Returns:
            HealthStatus with status and version
        """
        response = self._http.get("/health")
        return HealthStatus.from_api_response(response)

    def ready(self) -> HealthStatus:
        """Readiness check with database connectivity.

        Checks database connectivity in addition to basic health.
        No authentication required.

        Returns:
            HealthStatus with status, version, and database status
        """
        response = self._http.get("/ready")
        return HealthStatus.from_api_response(response)
