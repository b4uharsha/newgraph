"""Main Graph OLAP SDK client.

The primary entry point for interacting with the Graph OLAP Platform.
The ``GraphOLAPClient`` constructor requires only a ``username``; all other
parameters have sensible defaults that can be overridden via environment
variables or keyword arguments.

Example::

    from graph_olap import GraphOLAPClient
    client = GraphOLAPClient(username="alice@hsbc.co.uk")
"""

from __future__ import annotations

import os
from typing import Any

from graph_olap_schemas import WrapperType

from graph_olap.config import Config
from graph_olap.http import HTTPClient
from graph_olap.identity import DEFAULT_USERNAME
from graph_olap.resources.admin import AdminResource
from graph_olap.resources.favorites import FavoriteResource
from graph_olap.resources.health import HealthResource
from graph_olap.resources.instances import InstanceResource
from graph_olap.resources.mappings import MappingResource
from graph_olap.resources.ops import OpsResource
from graph_olap.resources.schema import SchemaResource
from graph_olap.resources.users import UserResource

DEFAULT_USE_CASE_ID = "e2e_test_role"

# =============================================================================
# SNAPSHOT FUNCTIONALITY DISABLED
# Snapshots are now created implicitly when instances are created from mappings.
# =============================================================================
# from graph_olap.resources.snapshots import SnapshotResource  # noqa: ERA001


class GraphOLAPClient:
    """Main client for Graph OLAP Platform.

    Provides access to all control plane operations:
    - Mappings: Graph schema definitions
    - Snapshots: Point-in-time data exports
    - Instances: Running graph databases
    - Favorites: Bookmarked resources
    - Schema: Browse Starburst schema metadata (catalogs, schemas, tables, columns)
    - Ops: Configuration and cluster management (Ops role)
    - Admin: Privileged operations (Admin role)
    - Health: Health and readiness checks

    Identity (ADR-104/105):
        The SDK sends X-Username on every request. The server trusts this header
        (set by the edge proxy in production) and reads the user's role from the
        database. No JWT or API key authentication.

    Configuration resolution (ADR-126):
        ``username`` and ``api_url`` are both required.  ``api_url`` must
        be supplied as a keyword argument or via the ``GRAPH_OLAP_API_URL``
        environment variable.  ``use_case_id`` has a baked-in default.

        +----------------+-----------------------------+----------------------------+
        | Parameter      | Environment variable        | Default                    |
        +================+=============================+============================+
        | ``api_url``    | ``GRAPH_OLAP_API_URL``      | *(required — no default)*  |
        +----------------+-----------------------------+----------------------------+
        | ``use_case_id``| ``GRAPH_OLAP_USE_CASE_ID``  | ``e2e_test_role``          |
        +----------------+-----------------------------+----------------------------+

    Example:
        >>> # Minimal — api_url comes from GRAPH_OLAP_API_URL env var
        >>> client = GraphOLAPClient(username="alice@hsbc.co.uk")

        >>> # Explicit URL (overrides env var)
        >>> client = GraphOLAPClient(
        ...     username="alice@hsbc.co.uk",
        ...     api_url="http://control-plane-svc.graph-olap-platform.svc.cluster.local:8080",
        ... )

        >>> # Or auto-discover from environment
        >>> client = GraphOLAPClient.from_env()

        >>> # List mappings
        >>> mappings = client.mappings.list()

        >>> # Create instance and connect
        >>> instance = client.instances.create_and_wait(
        ...     snapshot_id=snapshot.id,
        ...     name="Analysis Instance",
        ... )
        >>> conn = client.instances.connect(instance.id)

        >>> # Query
        >>> result = conn.query("MATCH (n:Customer) RETURN n LIMIT 10")
        >>> df = result.to_polars()

        >>> # Clean up
        >>> client.instances.terminate(instance.id)
        >>> client.close()

    Using context manager:
        >>> with GraphOLAPClient.from_env() as client:
        ...     mappings = client.mappings.list()
    """

    def __init__(
        self,
        username: str,
        *,
        api_url: str | None = None,
        use_case_id: str | None = None,
        proxy: str | None = None,
        verify: bool | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """Initialize Graph OLAP client.

        Args:
            username: Username for X-Username header (required).  The
                sentinel value ``"_FILL_ME_IN_"`` is rejected immediately
                with a clear error message.  If ``None`` is somehow passed,
                falls back to ``DEFAULT_USERNAME`` from
                :mod:`graph_olap.identity`.
            api_url: Base URL for the control plane API.  Required —
                must be supplied either as this argument or via the
                ``GRAPH_OLAP_API_URL`` environment variable.  No baked-in
                default: a missing URL raises :class:`RuntimeError` at
                construction time, because silently falling back to a
                hard-coded dev host has caused data-leak risks and
                confusing DNS failures on air-gapped deployments.
            use_case_id: Use case ID for X-Use-Case-Id header (ADR-102).
                Resolved from ``GRAPH_OLAP_USE_CASE_ID`` env var, then
                ``DEFAULT_USE_CASE_ID``.
            proxy: HTTP proxy URL.  Resolved from
                ``GRAPH_OLAP_PROXY`` env var if not provided.
            verify: Whether to verify SSL certificates.  Resolved from
                ``GRAPH_OLAP_SSL_VERIFY`` env var (``"false"`` to disable)
                if not explicitly set.  Defaults to ``True``.
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts for transient failures

        Raises:
            ValueError: If *username* is the ``"_FILL_ME_IN_"`` sentinel.
            RuntimeError: If neither *api_url* nor the
                ``GRAPH_OLAP_API_URL`` environment variable is set.
        """
        if username == "_FILL_ME_IN_":
            raise ValueError(
                "Set USERNAME to your email before running. "
                "Example: USERNAME = 'alice@hsbc.co.uk'"
            )

        resolved_username = username or DEFAULT_USERNAME
        resolved_api_url = api_url or os.environ.get("GRAPH_OLAP_API_URL")
        if not resolved_api_url:
            raise RuntimeError(
                "GRAPH_OLAP_API_URL is not set. Pass api_url=... to "
                "GraphOLAPClient(), or set the GRAPH_OLAP_API_URL "
                "environment variable to your control-plane URL — for "
                "example http://control-plane-svc.graph-olap-platform"
                ".svc.cluster.local:8080 for in-cluster access, or the "
                "ingress hostname for external access."
            )
        resolved_use_case_id = use_case_id or os.environ.get("GRAPH_OLAP_USE_CASE_ID", DEFAULT_USE_CASE_ID)
        resolved_proxy = proxy or os.environ.get("GRAPH_OLAP_PROXY")
        if verify is None:
            env_verify = os.environ.get("GRAPH_OLAP_SSL_VERIFY", "").lower()
            resolved_verify = env_verify not in ("false", "0", "no") if env_verify else True
        else:
            resolved_verify = verify

        self._config = Config(
            api_url=resolved_api_url,
            username=resolved_username,
            use_case_id=resolved_use_case_id,
            proxy=resolved_proxy,
            verify=resolved_verify,
            timeout=timeout,
            max_retries=max_retries,
        )

        self._http = HTTPClient(
            base_url=resolved_api_url,
            username=resolved_username,
            use_case_id=resolved_use_case_id,
            proxy=resolved_proxy,
            verify=resolved_verify,
            timeout=timeout,
            max_retries=max_retries,
        )

        # Resource managers
        self.mappings = MappingResource(self._http)
        # SNAPSHOT FUNCTIONALITY DISABLED - snapshots created implicitly from mappings
        # self.snapshots = SnapshotResource(self._http)  # noqa: ERA001
        self.instances = InstanceResource(self._http, self._config)
        self.favorites = FavoriteResource(self._http)
        self.schema = SchemaResource(self._http)
        self.ops = OpsResource(self._http)
        self.admin = AdminResource(self._http)
        self.health = HealthResource(self._http)
        self.users = UserResource(self._http)

    @property
    def username(self) -> str:
        """The username sent as X-Username on every request."""
        return self._http.username

    @username.setter
    def username(self, value: str) -> None:
        """Change the username for all subsequent API calls.

        Updates the X-Username header on the underlying HTTP client so that
        all future requests are made as this user.

        Args:
            value: New username.

        Example:
            >>> client = GraphOLAPClient(username="alice@example.com")
            >>> client.username = "bob@example.com"
            >>> # All subsequent calls use X-Username: bob@example.com
        """
        self._config.username = value
        self._http.set_username(value)

    @classmethod
    def from_env(
        cls,
        api_url: str | None = None,
        username: str | None = None,
        **kwargs: Any,
    ) -> GraphOLAPClient:
        """Create client from environment variables.

        Environment Variables:
            GRAPH_OLAP_API_URL: Base URL for the control plane API
                (required — no default; see class docstring).
            GRAPH_OLAP_USERNAME: Username for X-Username header
            GRAPH_OLAP_USE_CASE_ID: Use case ID for X-Use-Case-Id header
                (default: ``DEFAULT_USE_CASE_ID``)
            GRAPH_OLAP_PROXY: HTTP proxy URL
            GRAPH_OLAP_SSL_VERIFY: Whether to verify SSL certificates

        Raises:
            RuntimeError: If neither *api_url* nor the
                ``GRAPH_OLAP_API_URL`` environment variable is set
                (propagated from :meth:`Config.from_env`).

        Args:
            api_url: Override GRAPH_OLAP_API_URL
            username: Override GRAPH_OLAP_USERNAME
            **kwargs: Additional config options (timeout, max_retries)

        Returns:
            Configured GraphOLAPClient

        Example:
            >>> # Uses environment variables
            >>> client = GraphOLAPClient.from_env()

            >>> # Override specific values
            >>> client = GraphOLAPClient.from_env(timeout=60.0)
        """
        config = Config.from_env(api_url=api_url, username=username, **kwargs)
        return cls(
            username=config.username or DEFAULT_USERNAME,
            api_url=config.api_url,
            use_case_id=config.use_case_id,
            proxy=config.proxy,
            verify=config.verify,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    def close(self) -> None:
        """Close the client and release resources."""
        self._http.close()

    def __enter__(self) -> GraphOLAPClient:
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()

    def quick_start(
        self,
        mapping_id: int,
        wrapper_type: WrapperType,
        *,
        instance_name: str | None = None,
        wait_timeout: int = 900,
    ) -> Any:
        """Quick start: create instance from mapping and connect in one call.

        Convenience method for the common workflow of going from a mapping
        to a connected instance ready for queries. Snapshots are created
        implicitly by the control plane during instance creation.

        Args:
            mapping_id: Mapping ID to use
            wrapper_type: Graph database wrapper type (ryugraph or falkordb)
            instance_name: Name for instance (defaults to "Quick Instance")
            wait_timeout: Max time to wait for instance creation

        Returns:
            InstanceConnection ready for queries

        Example:
            >>> conn = client.quick_start(mapping_id=1, wrapper_type=WrapperType.RYUGRAPH)
            >>> result = conn.query("MATCH (n) RETURN count(n)")
            >>> # Remember to terminate the instance when done!
        """
        instance = self.instances.create_and_wait(
            mapping_id=mapping_id,
            name=instance_name or "Quick Instance",
            wrapper_type=wrapper_type,
            timeout=wait_timeout,
        )

        return self.instances.connect(instance.id)
