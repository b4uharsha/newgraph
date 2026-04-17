"""Shared notebook setup -- provides clients and resource tracking.

Every notebook (tutorial, E2E, reference, UAT) should start with:

    from graph_olap.notebook_setup import setup
    ctx = setup()
    client = ctx.client          # analyst (Alice)

And end with:

    ctx.teardown()

For E2E tests (ADR-124 unified pattern):

    from graph_olap.notebook_setup import setup
    from graph_olap.personas import Persona

    ctx = setup(prefix="AlgoTest", persona=Persona.ANALYST_ALICE)
    client = ctx.client
    mapping = ctx.mapping(node_definitions=[...])
    instance = ctx.instance(mapping)
    conn = ctx.connect(instance)
    ctx.track('graph_properties', conn, {...})
    # ... test body ...
    ctx.teardown()

Usernames are namespaced by JUPYTERHUB_USER to isolate concurrent users:

    analyst_alice@e2e.{hub_user}.local
    admin_carol@e2e.{hub_user}.local
    ops_dave@e2e.{hub_user}.local

Environment Variables:
    GRAPH_OLAP_API_URL:    Control plane URL (required)
    JUPYTERHUB_USER:       JupyterHub user for namespace isolation (default: "local")
    GRAPH_OLAP_USERNAME_*: Per-persona usernames for E2E tests (optional)
"""

from __future__ import annotations

import atexit
import logging
import os
import signal
import uuid
from typing import TYPE_CHECKING, Any

from graph_olap.client import GraphOLAPClient
from graph_olap.exceptions import NotFoundError
from graph_olap.personas import Persona

if TYPE_CHECKING:
    from graph_olap.instance.connection import InstanceConnection
    from graph_olap.models import Instance, Mapping, Snapshot

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Safe in-cluster default for GRAPH_OLAP_API_URL
# ---------------------------------------------------------------------------
#
# Runs at module import (triggered by `from graph_olap import ...` via
# graph_olap/__init__.py), BEFORE any GraphOLAPClient is constructed.
#
# Uses ``setdefault`` so any caller that already set GRAPH_OLAP_API_URL wins:
#   * CI sourcing tests/e2e/clusters/*.env
#   * JupyterHub singleuser.extraEnv
#   * Explicit %env magic in a notebook cell
#
# The baked default is the Kubernetes ClusterIP service URL. It only resolves
# INSIDE a cluster that hosts the ``graph-olap-control-plane`` service in the
# ``hsbc-graph`` namespace -- which means:
#   * HSBC's cluster: resolves to HSBC's control plane.
#   * Our GKE London cluster: resolves to our control plane (same service name).
#   * Anywhere else (laptop, external network): fails to resolve cleanly, no
#     cross-environment routing, no data-leak path.
#
# ``make hsbc``'s build-repos.sh sed rule rewrites this URL on the rendered
# SDK for the HSBC bundle. Source tree stays as-is.
os.environ.setdefault(
    "GRAPH_OLAP_API_URL",
    "https://control-plane-graph-olap-platform.hsbc-12636856-udlhk-dev.dev.gcp.cloud.hk.hsbc",
)


# ---------------------------------------------------------------------------
# Username helpers
# ---------------------------------------------------------------------------


def _get_hub_user() -> str:
    """Get JupyterHub username, defaulting to ``'local'`` for dev."""
    return os.environ.get("JUPYTERHUB_USER", "local")


def _make_username(persona_name: str) -> str:
    """Build a namespaced username for the given persona.

    Args:
        persona_name: Short persona identifier (e.g. ``"analyst_alice"``).

    Returns:
        Fully-qualified username like ``"analyst_alice@e2e.local"``
        (dev/CI) or ``"analyst_alice@e2e.henrik.local"`` (JupyterHub).
    """
    hub_user = _get_hub_user()
    if hub_user == "local":
        # Dev machine or CI — no namespace needed
        return f"{persona_name}@e2e.local"
    # JupyterHub — namespace by hub username for isolation
    return f"{persona_name}@e2e.{hub_user}.local"


def _get_api_url(api_url: str | None = None) -> str:
    """Resolve the API URL from an explicit argument or the environment.

    Args:
        api_url: Explicit URL, or ``None`` to read ``GRAPH_OLAP_API_URL``.

    Returns:
        The resolved API URL.

    Raises:
        RuntimeError: If neither ``api_url`` nor the ``GRAPH_OLAP_API_URL``
            environment variable is set. The previous behaviour — silently
            defaulting to the GKE London dev host
            (``https://control-plane-graph-olap-platform.hsbc-12636856-udlhk-dev.dev.gcp.cloud.hk.hsbc``) — has been removed
            because it silently routed HSBC workloads to our dev cluster
            whenever HSBC's Jupyter spawner forgot to inject the env var.
            If egress ever opened up, that default would have been an
            actual data-leak. Callers must now be explicit.
    """
    url = api_url or os.environ.get("GRAPH_OLAP_API_URL")
    if not url:
        raise RuntimeError(
            "GRAPH_OLAP_API_URL is not set. Pass api_url=... explicitly to "
            "setup()/provision(), or set the GRAPH_OLAP_API_URL environment "
            "variable to your control-plane URL — for example "
            "http://control-plane-svc.graph-olap-platform.svc.cluster.local:8080 "
            "for in-cluster access, or the ingress hostname for external access."
        )
    return url


def _make_client(api_url: str, username: str) -> GraphOLAPClient:
    """Create a GraphOLAPClient with use_case_id from environment."""
    return GraphOLAPClient(
        username=username,
        api_url=api_url,
        use_case_id=os.environ.get("GRAPH_OLAP_USE_CASE_ID"),
    )


# ---------------------------------------------------------------------------
# NotebookContext
# ---------------------------------------------------------------------------


class NotebookContext:
    """Pre-authenticated clients and resource tracker for notebook sessions.

    Created by :func:`setup`.  In **tutorial mode** (no ``prefix``),
    provides three pre-built clients (:attr:`client`, :attr:`admin`,
    :attr:`ops`).  In **E2E test mode** (with ``prefix``), provides a
    single primary client for the specified persona, with additional
    personas available via :meth:`with_persona`.

    Attributes:
        api_url:  The control plane base URL.
        hub_user: The resolved JupyterHub username (or ``"local"``).
        prefix:   Test name prefix for auto-naming (E2E mode only).
        run_id:   Unique 8-char hex ID for this test run (E2E mode only).
        client:   :class:`~graph_olap.GraphOLAPClient` for the primary persona.
        admin:    :class:`~graph_olap.GraphOLAPClient` for ``admin_carol``
                  (tutorial mode only; ``None`` in E2E mode).
        ops:      :class:`~graph_olap.GraphOLAPClient` for ``ops_dave``
                  (tutorial mode only; ``None`` in E2E mode).
    """

    def __init__(
        self,
        api_url: str,
        hub_user: str,
        *,
        prefix: str | None = None,
        persona: Persona | None = None,
    ) -> None:
        self.api_url = api_url
        self.hub_user = hub_user
        self.prefix = prefix
        self.run_id = uuid.uuid4().hex[:8] if prefix else None
        self._persona = persona

        # Backward-compat tracking (used by tutorial notebooks via
        # create_mapping / create_instance)
        self._tracked_instances: list[int] = []
        self._tracked_mappings: list[int] = []

        # Unified resource tracking: (type, id_or_obj, name_or_meta)
        # Types: "mapping", "snapshot", "instance", "graph_properties"
        self._resources: list[tuple[str, Any, Any]] = []
        self._cleaned_up = False

        # Persona client cache (E2E mode)
        self._persona_clients: dict[Persona, GraphOLAPClient] = {}

        if prefix and persona:
            # E2E test mode: primary client is the specified persona
            self.client = self._create_persona_client(persona)
            self._persona_clients[persona] = self.client
            self.admin = None
            self.ops = None
        else:
            # Tutorial mode: pre-create all three clients
            self.client = _make_client(api_url, _make_username("analyst_alice"))
            self.admin = _make_client(api_url, _make_username("admin_carol"))
            self.ops = _make_client(api_url, _make_username("ops_dave"))

        # Register cleanup for crash/interrupt safety
        atexit.register(self._atexit_cleanup)

        # Handle SIGTERM (kubernetes pod termination) and SIGINT (Ctrl+C)
        self._original_sigterm = signal.getsignal(signal.SIGTERM)
        self._original_sigint = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    # -- persona helpers -----------------------------------------------------

    def _create_persona_client(self, persona: Persona) -> GraphOLAPClient:
        """Create a client for a specific persona.

        In E2E mode (``prefix`` set), resolves username from the persona's
        environment variable with fallback to ``{name}@e2e.local``.
        In tutorial mode, constructs from ``JUPYTERHUB_USER``.
        """
        config = persona.value
        if self.prefix:
            # E2E mode: env var first, then fallback (matches conftest.py)
            username = os.environ.get(config.env_var) or f"{config.name}@e2e.local"
        else:
            # Tutorial mode: construct from hub_user
            username = _make_username(config.name)
        return _make_client(self.api_url, username)

    def with_persona(self, persona: Persona) -> GraphOLAPClient:
        """Get a client authenticated as a different persona.

        Clients are cached -- calling this multiple times with the same
        persona returns the same client. All persona clients are closed
        in :meth:`teardown`.

        Args:
            persona: The persona to authenticate as.

        Returns:
            A :class:`~graph_olap.GraphOLAPClient` for the requested persona.

        Example::

            ctx = setup(prefix="AuthTest", persona=Persona.ANALYST_ALICE)
            bob = ctx.with_persona(Persona.ANALYST_BOB)
            admin = ctx.with_persona(Persona.ADMIN_CAROL)
        """
        if persona not in self._persona_clients:
            self._persona_clients[persona] = self._create_persona_client(persona)
        return self._persona_clients[persona]

    # -- resource tracking ---------------------------------------------------

    def track(self, resource_type: str, resource_id: Any, name: Any) -> None:
        """Track a resource for cleanup on :meth:`teardown`.

        Args:
            resource_type: One of ``"mapping"``, ``"snapshot"``,
                ``"instance"``, ``"graph_properties"``.
            resource_id: Resource ID (int) or connection object
                (for ``graph_properties``).
            name: Resource name (str) or metadata dict
                (for ``graph_properties``).
        """
        self._resources.append((resource_type, resource_id, name))
        logger.info("Tracking %s %s (%s)", resource_type, resource_id, name)

    # Keep _track as alias for backward compat during transition
    _track = track

    # -- convenience accessors ------------------------------------------------

    def connect(self, instance_id: int | Instance) -> InstanceConnection:
        """Connect to a graph instance.

        Args:
            instance_id: Instance ID (int) or an Instance object.

        Returns:
            An :class:`~graph_olap.instance.connection.InstanceConnection`.

        Raises:
            ValueError: If *instance_id* is not provided.
        """
        # Handle Instance objects (E2E pattern: ctx.connect(instance))
        if hasattr(instance_id, "id"):
            return self.client.instances.connect(instance_id.id)

        return self.client.instances.connect(instance_id)

    # -- tracked resource creation (legacy) -----------------------------------

    def create_mapping(self, **kwargs: Any) -> Mapping:
        """Create a mapping and track it for cleanup on :meth:`teardown`.

        Args:
            **kwargs: Forwarded to
                :meth:`~graph_olap.resources.mappings.MappingResource.create`.

        Returns:
            The created :class:`~graph_olap.models.Mapping`.
        """
        mapping = self.client.mappings.create(**kwargs)
        self._tracked_mappings.append(mapping.id)
        return mapping

    def create_instance(self, **kwargs: Any) -> Instance:
        """Create an instance (and wait) and track it for cleanup on :meth:`teardown`.

        Args:
            **kwargs: Forwarded to
                :meth:`~graph_olap.resources.instances.InstanceResource.create_and_wait`.

        Returns:
            The created :class:`~graph_olap.models.Instance`.
        """
        instance = self.client.instances.create_and_wait(**kwargs)
        self._tracked_instances.append(instance.id)
        return instance

    # -- auto-named resource creation (E2E) -----------------------------------

    def mapping(
        self,
        *,
        name: str | None = None,
        node_definitions: list[dict[str, Any]] | None = None,
        edge_definitions: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Mapping:
        """Create a mapping with auto-naming and auto-tracking.

        When :attr:`prefix` is set, generates a name like
        ``"{prefix}-Mapping-{run_id}"``. The mapping is automatically
        tracked for cleanup.

        Args:
            name: Optional custom name (defaults to auto-generated).
            node_definitions: Node definition dicts.
            edge_definitions: Edge definition dicts.
            **kwargs: Additional arguments for ``mappings.create()``.

        Returns:
            The created :class:`~graph_olap.models.Mapping`.
        """
        if name is None and self.prefix:
            name = f"{self.prefix}-Mapping-{self.run_id}"
        mapping = self.client.mappings.create(
            name=name,
            node_definitions=node_definitions or [],
            edge_definitions=edge_definitions or [],
            **kwargs,
        )
        self.track("mapping", mapping.id, mapping.name)
        return mapping

    def instance(
        self,
        mapping: Mapping | int,
        *,
        name: str | None = None,
        wrapper_type: str = "ryugraph",
        timeout: int = 300,
        **kwargs: Any,
    ) -> Instance:
        """Create an instance from a mapping and wait for running.

        Auto-names as ``"{prefix}-Instance-{run_id}"`` when :attr:`prefix`
        is set. The instance is automatically tracked for cleanup.

        Args:
            mapping: Mapping object or mapping ID.
            name: Optional custom name.
            wrapper_type: Graph database wrapper (``"ryugraph"`` or
                ``"falkordb"``).
            timeout: Max seconds to wait for instance to be running.
            **kwargs: Additional arguments for ``instances.create_and_wait()``.

        Returns:
            The created :class:`~graph_olap.models.Instance` (in RUNNING state).
        """
        mapping_id = mapping.id if hasattr(mapping, "id") else mapping
        if name is None and self.prefix:
            name = f"{self.prefix}-Instance-{self.run_id}"
        instance = self.client.instances.create_and_wait(
            mapping_id=mapping_id,
            name=name,
            wrapper_type=wrapper_type,
            timeout=timeout,
            **kwargs,
        )
        self.track("instance", instance.id, instance.name)
        return instance

    def snapshot(
        self,
        mapping: Mapping | int,
        *,
        name: str | None = None,
        timeout: int = 300,
        **kwargs: Any,
    ) -> Snapshot:
        """Create a snapshot and wait for ready.

        Auto-names as ``"{prefix}-Snapshot-{run_id}"`` when :attr:`prefix`
        is set. The snapshot is automatically tracked for cleanup.

        Args:
            mapping: Mapping object or mapping ID.
            name: Optional custom name.
            timeout: Max seconds to wait.
            **kwargs: Additional arguments for ``snapshots.create_and_wait()``.

        Returns:
            The created :class:`~graph_olap.models.Snapshot` (in READY state).
        """
        mapping_id = mapping.id if hasattr(mapping, "id") else mapping
        if name is None and self.prefix:
            name = f"{self.prefix}-Snapshot-{self.run_id}"
        snapshot = self.client.snapshots.create_and_wait(
            mapping_id=mapping_id,
            name=name,
            timeout=timeout,
            **kwargs,
        )
        self.track("snapshot", snapshot.id, snapshot.name)
        return snapshot

    def cleanup(self) -> dict[str, int]:
        """Manually trigger cleanup of all tracked resources.

        Alias for :meth:`teardown` that returns cleanup counts.
        Safe to call multiple times (idempotent).

        Returns:
            Dict with counts: ``{"instances": n, "snapshots": n,
            "mappings": n, "graph_properties": n}``
        """
        return self.teardown()

    # -- crash/signal safety ---------------------------------------------------

    def _atexit_cleanup(self) -> None:
        """Called by atexit -- clean up if teardown() was never called."""
        if not self._cleaned_up:
            logger.info("atexit: teardown() was not called, cleaning up now")
            self.teardown()

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle SIGTERM/SIGINT -- clean up before exit."""
        logger.info("Signal %d received, cleaning up", signum)
        self.teardown()
        # Re-raise to allow default disposition or chained handlers
        if signum == signal.SIGTERM:
            if self._original_sigterm not in (signal.SIG_DFL, signal.SIG_IGN, None):
                self._original_sigterm(signum, frame)
        elif signum == signal.SIGINT:
            if self._original_sigint not in (signal.SIG_DFL, signal.SIG_IGN, None):
                self._original_sigint(signum, frame)
            else:
                raise KeyboardInterrupt

    # -- teardown -------------------------------------------------------------

    def teardown(self) -> dict[str, int]:
        """Terminate tracked resources and close clients.

        Cleans up in dependency order:
        ``graph_properties`` -> ``instances`` -> ``snapshots`` -> ``mappings``.

        Graph properties must be cleaned BEFORE instances because the
        cleanup query needs a running instance and live connection.

        Safe to call multiple times.  Errors during cleanup are logged
        but never raised, so notebooks always exit cleanly.

        Returns:
            Dict with counts of cleaned up resources.
        """
        if self._cleaned_up:
            return {"instances": 0, "snapshots": 0, "mappings": 0, "graph_properties": 0}
        self._cleaned_up = True

        results = {"instances": 0, "snapshots": 0, "mappings": 0, "graph_properties": 0}

        # --- Unified resource cleanup (E2E mode) ---
        if self._resources:
            logger.info("Cleaning up %d tracked resource(s)...", len(self._resources))

            # Group by type for ordered cleanup
            graph_props = [(id_, name) for t, id_, name in self._resources if t == "graph_properties"]
            instances = [(id_, name) for t, id_, name in self._resources if t == "instance"]
            snapshots = [(id_, name) for t, id_, name in self._resources if t == "snapshot"]
            mappings = [(id_, name) for t, id_, name in self._resources if t == "mapping"]

            # 1. Clean graph properties FIRST (needs running instance + live connection)
            for conn_obj, meta in graph_props:
                try:
                    node_label = meta.get("node_label", "Customer") if isinstance(meta, dict) else "Customer"
                    prop_names = meta.get("property_names", []) if isinstance(meta, dict) else []
                    if prop_names:
                        remove_clause = ", ".join(f"n.{p}" for p in prop_names)
                        conn_obj.query_scalar(
                            f"MATCH (n:{node_label}) REMOVE {remove_clause} RETURN count(n)"
                        )
                        logger.info(
                            "Cleaned %d graph properties from %s nodes",
                            len(prop_names),
                            node_label,
                        )
                        results["graph_properties"] += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Could not clean graph properties: %s", exc)

            # 2. Terminate instances (reverse creation order)
            for instance_id, name in reversed(instances):
                try:
                    self.client.instances.terminate(instance_id)
                    logger.info("Teardown: terminated instance %d (%s)", instance_id, name)
                    results["instances"] += 1
                except NotFoundError:
                    logger.debug("Instance %d already deleted", instance_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Teardown: failed to terminate instance %d: %s", instance_id, exc)

            # 3. Delete snapshots
            for snapshot_id, name in reversed(snapshots):
                try:
                    self.client.snapshots.delete(snapshot_id)
                    logger.info("Teardown: deleted snapshot %d (%s)", snapshot_id, name)
                    results["snapshots"] += 1
                except NotFoundError:
                    logger.debug("Snapshot %d already deleted", snapshot_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Teardown: failed to delete snapshot %d: %s", snapshot_id, exc)

            # 4. Delete mappings
            for mapping_id, name in reversed(mappings):
                try:
                    self.client.mappings.delete(mapping_id)
                    logger.info("Teardown: deleted mapping %d (%s)", mapping_id, name)
                    results["mappings"] += 1
                except NotFoundError:
                    logger.debug("Mapping %d already deleted", mapping_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Teardown: failed to delete mapping %d: %s", mapping_id, exc)

        # --- Legacy tracking cleanup (tutorial mode) ---
        for iid in self._tracked_instances:
            try:
                self.client.instances.terminate(iid)
                logger.info("Teardown: terminated instance %d", iid)
                results["instances"] += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Teardown: failed to terminate instance %d: %s", iid, exc)

        for mid in self._tracked_mappings:
            try:
                self.client.mappings.delete(mid)
                logger.info("Teardown: deleted mapping %d", mid)
                results["mappings"] += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Teardown: failed to delete mapping %d: %s", mid, exc)

        self._tracked_instances.clear()
        self._tracked_mappings.clear()
        self._resources.clear()

        # Close all clients
        for name_label, client_obj in [
            ("client", self.client),
            ("admin", self.admin),
            ("ops", self.ops),
        ]:
            if client_obj is not None:
                try:
                    client_obj.close()
                except Exception:  # noqa: BLE001
                    pass

        # Close persona clients (E2E mode)
        for persona, client_obj in self._persona_clients.items():
            if client_obj is not self.client:  # Don't double-close primary
                try:
                    client_obj.close()
                except Exception:  # noqa: BLE001
                    pass

        logger.info(
            "Teardown complete: %d graph_properties, %d instances, "
            "%d snapshots, %d mappings",
            results["graph_properties"],
            results["instances"],
            results["snapshots"],
            results["mappings"],
        )

        return results

    # -- dunder helpers -------------------------------------------------------

    def __enter__(self) -> NotebookContext:
        """Support ``with setup() as ctx:`` usage."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Call :meth:`teardown` on context-manager exit."""
        self.teardown()

    def __repr__(self) -> str:
        parts = [
            f"NotebookContext(api_url={self.api_url!r}",
            f"hub_user={self.hub_user!r}",
        ]
        if self.prefix:
            parts.append(f"prefix={self.prefix!r}")
            parts.append(f"run_id={self.run_id!r}")
        resource_count = len(self._resources) + len(self._tracked_instances) + len(self._tracked_mappings)
        parts.append(f"resources={resource_count}")
        return ", ".join(parts) + ")"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def setup(
    api_url: str | None = None,
    *,
    prefix: str | None = None,
    persona: Persona | None = None,
) -> NotebookContext:
    """Set up the notebook environment.

    This is the main entry point for every notebook.

    **Tutorial mode** (no ``prefix``):
        Returns a context with three pre-built clients (alice, carol,
        dave). Users are expected to exist already (provisioned by
        conftest or per-group notebook_setup).

    **E2E test mode** (with ``prefix`` and ``persona``):
        Returns a context with a single primary client for the specified
        persona. Use :meth:`~NotebookContext.with_persona` for additional
        personas.

    Args:
        api_url: Explicit control-plane URL.  If ``None``, reads
            ``GRAPH_OLAP_API_URL`` from the environment.
        prefix: Test name prefix for auto-naming resources. Setting this
            activates E2E test mode.
        persona: The persona running this test (required when ``prefix``
            is set).

    Returns:
        A :class:`NotebookContext` ready for use.

    Raises:
        ValueError: If no API URL can be determined, or if ``prefix``
            is set without ``persona``.

    Example (tutorial)::

        from graph_olap.notebook_setup import setup
        ctx = setup()
        client = ctx.client
        # instance_id provided by per-group notebook_setup
        conn = ctx.connect(instance_id)
        ctx.teardown()

    Example (E2E test)::

        from graph_olap.notebook_setup import setup
        from graph_olap.personas import Persona

        ctx = setup(prefix="AlgoTest", persona=Persona.ANALYST_ALICE)
        mapping = ctx.mapping(node_definitions=[...])
        instance = ctx.instance(mapping)
        conn = ctx.connect(instance)
        ctx.teardown()
    """
    if prefix and not persona:
        raise ValueError("persona is required when prefix is set (E2E test mode)")

    resolved_url = _get_api_url(api_url)
    hub_user = _get_hub_user()

    if prefix:
        logger.info(
            "notebook_setup: E2E mode prefix=%s, persona=%s",
            prefix,
            persona.value.name,
        )
    else:
        logger.info(
            "notebook_setup: api_url=%s, hub_user=%s", resolved_url, hub_user
        )

    return NotebookContext(
        api_url=resolved_url,
        hub_user=hub_user,
        prefix=prefix,
        persona=persona,
    )
