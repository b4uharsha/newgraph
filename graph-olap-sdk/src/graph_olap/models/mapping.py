"""Mapping-related Pydantic models.

These models extend the shared graph-olap-schemas with SDK-specific
functionality for API serialization and Jupyter display.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

# Import shared types for re-export and reference
from graph_olap_schemas import (
    PrimaryKeyDefinition,
    RyugraphType,
)
from pydantic import BaseModel, ConfigDict, Field


class PropertyDefinition(BaseModel):
    """SDK PropertyDefinition with flexible typing for client convenience.

    Note: Uses str for type field instead of RyugraphType enum for
    flexibility when consuming API responses.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    type: str  # STRING, INT64, DOUBLE, BOOL, DATE, TIMESTAMP, etc.


class NodeDefinition(BaseModel):
    """SDK NodeDefinition with API serialization support.

    Note: Uses dict for primary_key instead of PrimaryKeyDefinition for
    flexibility when consuming API responses.
    """

    model_config = ConfigDict(frozen=True)

    label: str
    sql: str
    primary_key: dict[str, str]  # {"name": str, "type": str}
    properties: list[PropertyDefinition] = Field(default_factory=list)

    def to_api_dict(self) -> dict[str, Any]:
        """Convert to API request format."""
        return {
            "label": self.label,
            "sql": self.sql,
            "primary_key": self.primary_key,
            "properties": [{"name": p.name, "type": p.type} for p in self.properties],
        }


class EdgeDefinition(BaseModel):
    """SDK EdgeDefinition with API serialization support."""

    model_config = ConfigDict(frozen=True)

    type: str
    from_node: str
    to_node: str
    sql: str
    from_key: str
    to_key: str
    properties: list[PropertyDefinition] = Field(default_factory=list)

    def to_api_dict(self) -> dict[str, Any]:
        """Convert to API request format."""
        return {
            "type": self.type,
            "from_node": self.from_node,
            "to_node": self.to_node,
            "sql": self.sql,
            "from_key": self.from_key,
            "to_key": self.to_key,
            "properties": [{"name": p.name, "type": p.type} for p in self.properties],
        }


class MappingVersion(BaseModel):
    """Immutable mapping version.

    Matches MappingVersionResponse schema from graph_olap_schemas.
    """

    model_config = ConfigDict(frozen=True)

    mapping_id: int | None = None  # Present in version detail, not in summary
    version: int
    change_description: str | None = None
    node_definitions: list[NodeDefinition] = Field(default_factory=list)
    edge_definitions: list[EdgeDefinition] = Field(default_factory=list)
    created_at: datetime | None = None
    created_by: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> MappingVersion:
        """Create from API response data.

        Handles both MappingVersionResponse (full) and MappingVersionSummaryResponse (list).
        """
        node_definitions = []
        if "node_definitions" in data:
            node_definitions = [
                NodeDefinition(
                    label=n["label"],
                    sql=n["sql"],
                    primary_key=n["primary_key"],
                    properties=[
                        PropertyDefinition(name=p["name"], type=p["type"])
                        for p in n.get("properties", [])
                    ],
                )
                for n in data["node_definitions"]
            ]

        edge_definitions = []
        if "edge_definitions" in data:
            edge_definitions = [
                EdgeDefinition(
                    type=e["type"],
                    from_node=e["from_node"],
                    to_node=e["to_node"],
                    sql=e["sql"],
                    from_key=e["from_key"],
                    to_key=e["to_key"],
                    properties=[
                        PropertyDefinition(name=p["name"], type=p["type"])
                        for p in e.get("properties", [])
                    ],
                )
                for e in data["edge_definitions"]
            ]

        return cls(
            mapping_id=data.get("mapping_id"),
            version=data["version"],
            change_description=data.get("change_description"),
            node_definitions=node_definitions,
            edge_definitions=edge_definitions,
            created_at=_parse_datetime(data["created_at"]) if data.get("created_at") else None,
            created_by=data.get("created_by"),
        )


class Mapping(BaseModel):
    """Graph mapping definition.

    Matches MappingResponse/MappingSummaryResponse from graph_olap_schemas.
    """

    model_config = ConfigDict(frozen=True)

    id: int
    owner_username: str | None = None  # May be missing in lifecycle responses
    name: str | None = None  # May be missing in lifecycle responses
    description: str | None = None
    current_version: int | None = None  # May be missing in lifecycle responses
    created_at: datetime | None = None
    updated_at: datetime | None = None
    ttl: str | None = None
    inactivity_timeout: str | None = None
    snapshot_count: int | None = None
    # From MappingSummaryResponse (list endpoint)
    node_count: int | None = None
    edge_type_count: int | None = None
    # From MappingResponse (detail endpoint) - embedded version info
    version: MappingVersion | None = None
    node_definitions: list[NodeDefinition] = Field(default_factory=list)
    edge_definitions: list[EdgeDefinition] = Field(default_factory=list)
    change_description: str | None = None
    version_created_at: datetime | None = None
    version_created_by: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> Mapping:
        """Create from API response data.

        Handles both MappingResponse (detail) and MappingSummaryResponse (list).
        """
        # Parse nested version object if present
        version = None
        if data.get("version"):
            version = MappingVersion.from_api_response(data["version"])

        # Parse top-level node/edge definitions (for backward compatibility)
        node_definitions = []
        if "node_definitions" in data:
            node_definitions = [
                NodeDefinition(
                    label=n["label"],
                    sql=n["sql"],
                    primary_key=n["primary_key"],
                    properties=[
                        PropertyDefinition(name=p["name"], type=p["type"])
                        for p in n.get("properties", [])
                    ],
                )
                for n in data["node_definitions"]
            ]

        edge_definitions = []
        if "edge_definitions" in data:
            edge_definitions = [
                EdgeDefinition(
                    type=e["type"],
                    from_node=e["from_node"],
                    to_node=e["to_node"],
                    sql=e["sql"],
                    from_key=e["from_key"],
                    to_key=e["to_key"],
                    properties=[
                        PropertyDefinition(name=p["name"], type=p["type"])
                        for p in e.get("properties", [])
                    ],
                )
                for e in data["edge_definitions"]
            ]

        return cls(
            id=data["id"],
            owner_username=data.get("owner_username"),  # Optional in lifecycle responses
            name=data.get("name"),  # Optional in lifecycle responses
            description=data.get("description"),
            current_version=data.get("current_version"),  # May be missing in lifecycle responses
            created_at=_parse_datetime(data["created_at"]) if data.get("created_at") else None,
            updated_at=_parse_datetime(data["updated_at"]) if data.get("updated_at") else None,
            ttl=data.get("ttl"),
            inactivity_timeout=data.get("inactivity_timeout"),
            snapshot_count=data.get("snapshot_count"),
            node_count=data.get("node_count"),
            edge_type_count=data.get("edge_type_count"),
            version=version,
            node_definitions=node_definitions,
            edge_definitions=edge_definitions,
            change_description=data.get("change_description"),
            version_created_at=_parse_datetime(data["version_created_at"]) if data.get("version_created_at") else None,
            version_created_by=data.get("version_created_by"),
        )

    def _repr_html_(self) -> str:
        """Rich HTML display for Jupyter notebooks."""
        desc = self.description or "<em>No description</em>"
        return f"""
        <div style="border: 1px solid #e1e4e8; padding: 12px; border-radius: 6px; margin: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;">
            <h4 style="margin: 0 0 8px 0; color: #24292e;">Mapping: {self.name}</h4>
            <p style="margin: 0 0 12px 0; color: #586069; font-size: 14px;">{desc}</p>
            <table style="border-collapse: collapse; font-size: 13px;">
                <tr><td style="padding: 4px 12px 4px 0; color: #586069;"><strong>ID:</strong></td><td>{self.id}</td></tr>
                <tr><td style="padding: 4px 12px 4px 0; color: #586069;"><strong>Owner:</strong></td><td>{self.owner_username}</td></tr>
                <tr><td style="padding: 4px 12px 4px 0; color: #586069;"><strong>Version:</strong></td><td>v{self.current_version}</td></tr>
            </table>
        </div>
        """


class NodeDiff(BaseModel):
    """Diff result for a node definition between versions.

    Matches NodeDiffResponse from graph_olap_schemas.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    label: str
    change_type: str  # "added", "removed", "modified"
    fields_changed: list[str] | None = None
    from_: dict[str, Any] | None = Field(None, alias="from")
    to: dict[str, Any] | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> NodeDiff:
        """Create from API response data."""
        return cls.model_validate(data)


class EdgeDiff(BaseModel):
    """Diff result for an edge definition between versions.

    Matches EdgeDiffResponse from graph_olap_schemas.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    type: str
    change_type: str  # "added", "removed", "modified"
    fields_changed: list[str] | None = None
    from_: dict[str, Any] | None = Field(None, alias="from")
    to: dict[str, Any] | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> EdgeDiff:
        """Create from API response data."""
        return cls.model_validate(data)


class MappingDiff(BaseModel):
    """Diff result between two mapping versions.

    Provides semantic comparison showing added, removed, and modified
    node/edge definitions.

    Example:
        >>> diff = client.mappings.diff(mapping_id=1, from_version=1, to_version=2)
        >>> print(f"Added {diff.summary['nodes_added']} nodes")
        >>> for node in diff.nodes_added():
        ...     print(f"  + {node.label}")
    """

    model_config = ConfigDict(frozen=True)

    mapping_id: int
    from_version: int
    to_version: int
    summary: dict[str, int]  # {nodes_added, nodes_removed, nodes_modified, ...}
    changes: dict[str, list[NodeDiff | EdgeDiff]]  # {nodes: [...], edges: [...]}

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> MappingDiff:
        """Create from API response data.

        Args:
            data: Response data from GET /api/mappings/:id/versions/:v1/diff/:v2

        Returns:
            MappingDiff object
        """
        # Parse node diffs
        node_diffs = [
            NodeDiff.from_api_response(n) for n in data["changes"].get("nodes", [])
        ]

        # Parse edge diffs
        edge_diffs = [
            EdgeDiff.from_api_response(e) for e in data["changes"].get("edges", [])
        ]

        return cls(
            mapping_id=data["mapping_id"],
            from_version=data["from_version"],
            to_version=data["to_version"],
            summary=data["summary"],
            changes={"nodes": node_diffs, "edges": edge_diffs},
        )

    def nodes_added(self) -> list[NodeDiff]:
        """Filter nodes with change_type='added'."""
        return [n for n in self.changes["nodes"] if n.change_type == "added"]

    def nodes_removed(self) -> list[NodeDiff]:
        """Filter nodes with change_type='removed'."""
        return [n for n in self.changes["nodes"] if n.change_type == "removed"]

    def nodes_modified(self) -> list[NodeDiff]:
        """Filter nodes with change_type='modified'."""
        return [n for n in self.changes["nodes"] if n.change_type == "modified"]

    def edges_added(self) -> list[EdgeDiff]:
        """Filter edges with change_type='added'."""
        return [e for e in self.changes["edges"] if e.change_type == "added"]

    def edges_removed(self) -> list[EdgeDiff]:
        """Filter edges with change_type='removed'."""
        return [e for e in self.changes["edges"] if e.change_type == "removed"]

    def edges_modified(self) -> list[EdgeDiff]:
        """Filter edges with change_type='modified'."""
        return [e for e in self.changes["edges"] if e.change_type == "modified"]

    def _repr_html_(self) -> str:
        """Rich HTML display for Jupyter notebooks."""
        s = self.summary
        return f"""
        <div style="border: 1px solid #e1e4e8; padding: 12px; border-radius: 6px; margin: 8px 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;">
            <h4 style="margin: 0 0 8px 0; color: #24292e;">Mapping Diff: v{self.from_version} → v{self.to_version}</h4>
            <table style="border-collapse: collapse; font-size: 13px; margin-top: 8px;">
                <tr style="background: #f6f8fa;">
                    <th style="padding: 6px 12px; text-align: left; border-bottom: 1px solid #d1d5da;">Category</th>
                    <th style="padding: 6px 12px; text-align: right; border-bottom: 1px solid #d1d5da;">Added</th>
                    <th style="padding: 6px 12px; text-align: right; border-bottom: 1px solid #d1d5da;">Removed</th>
                    <th style="padding: 6px 12px; text-align: right; border-bottom: 1px solid #d1d5da;">Modified</th>
                </tr>
                <tr>
                    <td style="padding: 6px 12px; border-bottom: 1px solid #e1e4e8;"><strong>Nodes</strong></td>
                    <td style="padding: 6px 12px; text-align: right; color: #22863a; border-bottom: 1px solid #e1e4e8;">{s['nodes_added']}</td>
                    <td style="padding: 6px 12px; text-align: right; color: #cb2431; border-bottom: 1px solid #e1e4e8;">{s['nodes_removed']}</td>
                    <td style="padding: 6px 12px; text-align: right; color: #0366d6; border-bottom: 1px solid #e1e4e8;">{s['nodes_modified']}</td>
                </tr>
                <tr>
                    <td style="padding: 6px 12px;"><strong>Edges</strong></td>
                    <td style="padding: 6px 12px; text-align: right; color: #22863a;">{s['edges_added']}</td>
                    <td style="padding: 6px 12px; text-align: right; color: #cb2431;">{s['edges_removed']}</td>
                    <td style="padding: 6px 12px; text-align: right; color: #0366d6;">{s['edges_modified']}</td>
                </tr>
            </table>
        </div>
        """


def _parse_datetime(value: str) -> datetime:
    """Parse ISO datetime string, handling Z suffix."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


# Re-export shared types for backward compatibility
__all__ = [
    "EdgeDefinition",
    "EdgeDiff",
    "Mapping",
    "MappingDiff",
    "MappingVersion",
    "NodeDefinition",
    # Diff types
    "NodeDiff",
    # From shared schemas (re-exported)
    "PrimaryKeyDefinition",
    # SDK types
    "PropertyDefinition",
    "RyugraphType",
]
