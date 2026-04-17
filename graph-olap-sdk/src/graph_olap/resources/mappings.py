"""Mapping resource management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from graph_olap.models.common import PaginatedList
from graph_olap.models.mapping import (
    EdgeDefinition,
    Mapping,
    MappingDiff,
    MappingVersion,
    NodeDefinition,
)
from graph_olap.models.instance import Instance
from graph_olap.models.snapshot import Snapshot

if TYPE_CHECKING:
    from graph_olap.http import HTTPClient


class MappingResource:
    """Manage mapping definitions.

    Mappings define how Starburst SQL queries map to graph nodes and edges.
    Each mapping can have multiple versions (immutable) and multiple snapshots.

    Example:
        >>> client = GraphOLAPClient(api_url=api_url, username="user@example.com")
        >>> # List mappings
        >>> mappings = client.mappings.list()
        >>> for m in mappings:
        ...     print(m.name, m.current_version)

        >>> # Get a specific mapping
        >>> mapping = client.mappings.get(1)

        >>> # Create a new mapping
        >>> mapping = client.mappings.create(
        ...     name="Customer Graph",
        ...     description="Customer and order relationships",
        ...     node_definitions=[...],
        ...     edge_definitions=[...],
        ... )
    """

    def __init__(self, http: HTTPClient):
        """Initialize mapping resource.

        Args:
            http: HTTP client for API requests
        """
        self._http = http

    def list(
        self,
        *,
        owner: str | None = None,
        search: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        offset: int = 0,
        limit: int = 50,
    ) -> PaginatedList[Mapping]:
        """List mappings with optional filters.

        Args:
            owner: Filter by owner_id
            search: Text search on name, description
            created_after: Filter by created_at >= timestamp (ISO 8601)
            created_before: Filter by created_at <= timestamp (ISO 8601)
            sort_by: Sort field (name, created_at, current_version)
            sort_order: Sort direction (asc, desc)
            offset: Number of records to skip
            limit: Max records to return (max 100)

        Returns:
            Paginated list of Mapping objects
        """
        params: dict[str, Any] = {
            "offset": offset,
            "limit": min(limit, 100),
            "sort_by": sort_by,
            "sort_order": sort_order,
        }
        if owner:
            params["owner"] = owner
        if search:
            params["search"] = search
        if created_after:
            params["created_after"] = created_after
        if created_before:
            params["created_before"] = created_before

        response = self._http.get("/api/mappings", params=params)
        return PaginatedList(
            items=[Mapping.from_api_response(m) for m in response["data"]],
            total=response["meta"]["total"],
            offset=response["meta"]["offset"],
            limit=response["meta"]["limit"],
        )

    def get(self, mapping_id: int) -> Mapping:
        """Get a mapping by ID.

        Returns the mapping with its current version details embedded.

        Args:
            mapping_id: Mapping ID

        Returns:
            Mapping object with version details

        Raises:
            NotFoundError: If mapping doesn't exist
        """
        response = self._http.get(f"/api/mappings/{mapping_id}")
        return Mapping.from_api_response(response["data"])

    def get_version(self, mapping_id: int, version: int) -> MappingVersion:
        """Get a specific version of a mapping.

        Args:
            mapping_id: Mapping ID
            version: Version number

        Returns:
            MappingVersion object with full node/edge definitions

        Raises:
            NotFoundError: If mapping or version doesn't exist
        """
        response = self._http.get(f"/api/mappings/{mapping_id}/versions/{version}")
        return MappingVersion.from_api_response(response["data"])

    def list_versions(self, mapping_id: int) -> list[MappingVersion]:
        """List all versions of a mapping.

        Args:
            mapping_id: Mapping ID

        Returns:
            List of MappingVersion objects (newest first)

        Raises:
            NotFoundError: If mapping doesn't exist
        """
        response = self._http.get(f"/api/mappings/{mapping_id}/versions")
        return [MappingVersion.from_api_response(v) for v in response["data"]]

    def diff(
        self, mapping_id: int, from_version: int, to_version: int
    ) -> MappingDiff:
        """Compare two versions of a mapping.

        Returns a semantic diff showing added, removed, and modified
        node/edge definitions between versions.

        Args:
            mapping_id: Mapping ID
            from_version: Starting version number
            to_version: Ending version number

        Returns:
            MappingDiff object with summary counts and detailed changes

        Raises:
            NotFoundError: If mapping or version doesn't exist
            ValidationError: If from_version == to_version

        Example:
            >>> diff = client.mappings.diff(mapping_id=1, from_version=1, to_version=2)
            >>> print(f"Added {diff.summary['nodes_added']} nodes")
            >>> for node in diff.nodes_added():
            ...     print(f"  + {node.label}")
            >>>
            >>> # Display in Jupyter notebook
            >>> diff  # Shows rich HTML table
        """
        from graph_olap.models.mapping import MappingDiff

        response = self._http.get(
            f"/api/mappings/{mapping_id}/versions/{from_version}/diff/{to_version}"
        )
        return MappingDiff.from_api_response(response["data"])

    def list_snapshots(
        self,
        mapping_id: int,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> PaginatedList[Snapshot]:
        """List snapshots across all versions of a mapping.

        Args:
            mapping_id: Mapping ID
            offset: Number of records to skip
            limit: Max records to return

        Returns:
            Paginated list of Snapshot objects
        """
        params = {"offset": offset, "limit": min(limit, 100)}
        response = self._http.get(f"/api/mappings/{mapping_id}/snapshots", params=params)
        return PaginatedList(
            items=[Snapshot.from_api_response(s) for s in response["data"]],
            total=response["meta"]["total"],
            offset=response["meta"]["offset"],
            limit=response["meta"]["limit"],
        )

    def list_instances(
        self,
        mapping_id: int,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> PaginatedList[Instance]:
        """List instances created from any snapshot of this mapping.

        Args:
            mapping_id: Mapping ID
            offset: Number of records to skip
            limit: Max records to return (max 100)

        Returns:
            Paginated list of Instance objects

        Example:
            >>> instances = client.mappings.list_instances(mapping_id=1)
            >>> for i in instances:
            ...     print(f"{i.name}: {i.status}")
        """
        params = {"offset": offset, "limit": min(limit, 100)}
        response = self._http.get(f"/api/mappings/{mapping_id}/instances", params=params)
        return PaginatedList(
            items=[Instance.from_api_response(i) for i in response["data"]],
            total=response["meta"]["total"],
            offset=response["meta"]["offset"],
            limit=response["meta"]["limit"],
        )

    def create(
        self,
        name: str,
        description: str | None = None,
        node_definitions: list[NodeDefinition] | list[dict[str, Any]] | None = None,
        edge_definitions: list[EdgeDefinition] | list[dict[str, Any]] | None = None,
    ) -> Mapping:
        """Create a new mapping.

        Args:
            name: Mapping name
            description: Optional description
            node_definitions: List of node definitions
            edge_definitions: List of edge definitions

        Returns:
            Created Mapping object

        Raises:
            ValidationError: If definitions are invalid
        """
        # Convert to API format
        nodes = []
        if node_definitions:
            for n in node_definitions:
                if isinstance(n, NodeDefinition):
                    nodes.append(n.to_api_dict())
                else:
                    nodes.append(n)

        edges = []
        if edge_definitions:
            for e in edge_definitions:
                if isinstance(e, EdgeDefinition):
                    edges.append(e.to_api_dict())
                else:
                    edges.append(e)

        body: dict[str, Any] = {
            "name": name,
            "node_definitions": nodes,
            "edge_definitions": edges,
        }
        if description:
            body["description"] = description

        response = self._http.post("/api/mappings", json=body)
        return Mapping.from_api_response(response["data"])

    def update(
        self,
        mapping_id: int,
        change_description: str,
        *,
        name: str | None = None,
        description: str | None = None,
        node_definitions: list[NodeDefinition] | list[dict[str, Any]] | None = None,
        edge_definitions: list[EdgeDefinition] | list[dict[str, Any]] | None = None,
    ) -> Mapping:
        """Update a mapping, creating a new version.

        Args:
            mapping_id: Mapping ID
            change_description: Description of what changed (required)
            name: New name (optional)
            description: New description (optional)
            node_definitions: New node definitions (optional)
            edge_definitions: New edge definitions (optional)

        Returns:
            Updated Mapping object with new version

        Raises:
            NotFoundError: If mapping doesn't exist
            ValidationError: If definitions are invalid
        """
        body: dict[str, Any] = {"change_description": change_description}

        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description

        if node_definitions is not None:
            nodes = []
            for n in node_definitions:
                if isinstance(n, NodeDefinition):
                    nodes.append(n.to_api_dict())
                else:
                    nodes.append(n)
            body["node_definitions"] = nodes

        if edge_definitions is not None:
            edges = []
            for e in edge_definitions:
                if isinstance(e, EdgeDefinition):
                    edges.append(e.to_api_dict())
                else:
                    edges.append(e)
            body["edge_definitions"] = edges

        response = self._http.put(f"/api/mappings/{mapping_id}", json=body)
        return Mapping.from_api_response(response["data"])

    def delete(self, mapping_id: int) -> None:
        """Delete a mapping.

        Args:
            mapping_id: Mapping ID

        Raises:
            NotFoundError: If mapping doesn't exist
            DependencyError: If mapping has snapshots
        """
        self._http.delete(f"/api/mappings/{mapping_id}")

    def copy(self, mapping_id: int, new_name: str) -> Mapping:
        """Copy a mapping to a new mapping.

        Creates a new mapping with the same definitions as the source.
        Version history is not copied (starts at v1).

        Args:
            mapping_id: Source mapping ID
            new_name: Name for the new mapping

        Returns:
            New Mapping object

        Raises:
            NotFoundError: If source mapping doesn't exist
        """
        response = self._http.post(
            f"/api/mappings/{mapping_id}/copy",
            json={"name": new_name},
        )
        return Mapping.from_api_response(response["data"])

    def set_lifecycle(
        self,
        mapping_id: int,
        *,
        ttl: str | None = None,
        inactivity_timeout: str | None = None,
    ) -> Mapping:
        """Set lifecycle parameters for a mapping.

        Args:
            mapping_id: Mapping ID
            ttl: Time-to-live (ISO 8601 duration) or None to clear
            inactivity_timeout: Inactivity timeout (ISO 8601 duration) or None to clear

        Returns:
            Updated Mapping object
        """
        body: dict[str, Any] = {}
        if ttl is not None:
            body["ttl"] = ttl
        if inactivity_timeout is not None:
            body["inactivity_timeout"] = inactivity_timeout

        response = self._http.put(f"/api/mappings/{mapping_id}/lifecycle", json=body)
        return Mapping.from_api_response(response["data"])

    def get_tree(
        self,
        mapping_id: int,
        *,
        include_instances: bool = True,
        status: str | None = None,
    ) -> dict[int, dict[str, Any]]:
        """Get full resource hierarchy for a mapping.

        Returns versions -> snapshots -> instances tree structure.

        Args:
            mapping_id: Mapping ID
            include_instances: Include instance details
            status: Filter snapshots by status

        Returns:
            Dict keyed by version number, with each version containing:
            - name: Mapping name
            - snapshots: List of snapshots for this version
            - metadata: Version metadata

        Example:
            {
                1: {"name": "My Mapping", "snapshots": [...], "change_description": "Initial version"},
                2: {"name": "My Mapping", "snapshots": [...], "change_description": "Added properties"}
            }
        """
        params: dict[str, Any] = {"include_instances": include_instances}
        if status:
            params["status"] = status

        response = self._http.get(f"/api/mappings/{mapping_id}/tree", params=params)
        raw_tree = response["data"]

        # Transform API response into version-keyed dict
        tree: dict[int, dict[str, Any]] = {}
        for version_item in raw_tree.get("versions", []):
            version_num = version_item["version"]
            tree[version_num] = {
                "name": raw_tree["name"],
                "owner_username": raw_tree["owner_username"],
                "change_description": version_item.get("change_description"),
                "created_at": version_item.get("created_at"),
                "created_by": version_item.get("created_by"),
                "snapshots": version_item.get("snapshots", []),
                "snapshot_count": version_item.get("snapshot_count", 0),
            }

        return tree

    def diff_versions(
        self,
        mapping_id: int,
        from_version: int,
        to_version: int,
    ) -> dict[str, Any]:
        """Compare two mapping versions.

        Args:
            mapping_id: Mapping ID
            from_version: Base version number
            to_version: Target version number

        Returns:
            Diff with summary and detailed changes for nodes/edges

        Example:
            >>> diff = client.mappings.diff_versions(1, from_version=2, to_version=3)
            >>> print(f"Added {diff['summary']['nodes_added']} nodes")
        """
        response = self._http.get(
            f"/api/mappings/{mapping_id}/versions/{from_version}/diff/{to_version}"
        )
        return response["data"]
