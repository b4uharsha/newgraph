"""Configuration management for Graph OLAP SDK."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Config:
    """SDK configuration.

    Configuration can be provided explicitly or auto-discovered from
    environment variables.

    Environment Variables:
        GRAPH_OLAP_API_URL: Base URL for the control plane API
        GRAPH_OLAP_USERNAME: Username for X-Username header (required by server)
        GRAPH_OLAP_USE_CASE_ID: Use case ID for X-Use-Case-Id header (ADR-102)
        GRAPH_OLAP_PROXY: HTTP proxy URL
        GRAPH_OLAP_SSL_VERIFY: Whether to verify SSL certificates (default: true)

    Identity (ADR-104/105):
        The server trusts X-Username set by the edge proxy. The SDK always
        sends X-Username. Authorization is handled by the control plane.

    Example:
        >>> config = Config(
        ...     api_url="http://localhost:8000",
        ...     username="test-user@example.com",
        ... )

        >>> # Auto-discover from environment
        >>> config = Config.from_env()
    """

    api_url: str
    username: str | None = None
    use_case_id: str | None = None
    proxy: str | None = None
    verify: bool = True
    timeout: float = 30.0
    max_retries: int = 3

    @classmethod
    def from_env(
        cls,
        api_url: str | None = None,
        username: str | None = None,
        **kwargs,
    ) -> Config:
        """Create configuration from environment variables.

        ``api_url`` must come from an explicit argument or the
        ``GRAPH_OLAP_API_URL`` environment variable — there is no
        baked-in default (see ADR-126 update and commit history for
        context on why the silent GKE London fallback was removed).

        Args:
            api_url: Override GRAPH_OLAP_API_URL
            username: Override GRAPH_OLAP_USERNAME
            **kwargs: Additional config options

        Returns:
            Config instance

        Raises:
            RuntimeError: If neither ``api_url`` nor the
                ``GRAPH_OLAP_API_URL`` environment variable is set.
        """
        url = api_url or os.environ.get("GRAPH_OLAP_API_URL")
        if not url:
            raise RuntimeError(
                "GRAPH_OLAP_API_URL is not set. Pass api_url=... to "
                "Config.from_env(), or set the GRAPH_OLAP_API_URL "
                "environment variable to your control-plane URL — for "
                "example http://control-plane-svc.graph-olap-platform"
                ".svc.cluster.local:8080 for in-cluster access, or the "
                "ingress hostname for external access."
            )

        user = username or os.environ.get("GRAPH_OLAP_USERNAME")
        use_case_id = os.environ.get("GRAPH_OLAP_USE_CASE_ID", "e2e_test_role")
        proxy = os.environ.get("GRAPH_OLAP_PROXY") or os.environ.get("https_proxy")
        verify_str = (
            os.environ.get("GRAPH_OLAP_SSL_VERIFY")
            or os.environ.get("GRAPH_OLAP_VERIFY_SSL")
            or "true"
        )
        verify = verify_str.lower() not in ("false", "0", "no")

        return cls(
            api_url=url,
            username=user,
            use_case_id=use_case_id,
            proxy=proxy,
            verify=verify,
            **kwargs,
        )
