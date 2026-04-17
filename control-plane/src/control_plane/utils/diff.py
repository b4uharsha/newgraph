"""
Diff utilities for comparing mapping versions.

Provides semantic comparison of node and edge definitions between mapping versions,
producing a structured diff format that matches the API specification.
"""

from dataclasses import dataclass
from typing import Any, Literal

from deepdiff import DeepDiff

from control_plane.models.domain import EdgeDefinition, MappingVersion, NodeDefinition


@dataclass
class NodeDiff:
    """Diff result for a single node definition."""

    label: str
    change_type: Literal["added", "removed", "modified"]
    fields_changed: list[str] | None  # None for added/removed
    from_def: dict[str, Any] | None  # None for added
    to_def: dict[str, Any] | None  # None for removed


@dataclass
class EdgeDiff:
    """Diff result for a single edge definition."""

    type: str
    change_type: Literal["added", "removed", "modified"]
    fields_changed: list[str] | None  # None for added/removed
    from_def: dict[str, Any] | None  # None for added
    to_def: dict[str, Any] | None  # None for removed


@dataclass
class MappingDiffResult:
    """Complete diff result between two mapping versions."""

    mapping_id: int
    from_version: int
    to_version: int
    nodes_added: int
    nodes_removed: int
    nodes_modified: int
    edges_added: int
    edges_removed: int
    edges_modified: int
    node_diffs: list[NodeDiff]
    edge_diffs: list[EdgeDiff]


def diff_mapping_versions(
    from_version: MappingVersion, to_version: MappingVersion
) -> MappingDiffResult:
    """
    Compare two mapping versions and produce a semantic diff.

    Algorithm:
    1. Convert node_definitions/edge_definitions to dicts keyed by label/type
    2. Find added: in to_version but not from_version
    3. Find removed: in from_version but not to_version
    4. Find modified: in both, but content differs
    5. For modified items, use DeepDiff to identify changed fields
    6. Return structured diff result

    Args:
        from_version: Starting version
        to_version: Ending version

    Returns:
        MappingDiffResult: Structured diff with summary counts and detailed changes
    """
    # Convert to dicts keyed by label/type for efficient lookup
    from_nodes = {node.label: node for node in from_version.node_definitions}
    to_nodes = {node.label: node for node in to_version.node_definitions}

    from_edges = {edge.type: edge for edge in from_version.edge_definitions}
    to_edges = {edge.type: edge for edge in to_version.edge_definitions}

    # Compute node diffs
    node_diffs: list[NodeDiff] = []
    nodes_added = 0
    nodes_removed = 0
    nodes_modified = 0

    # Find added nodes
    for label in to_nodes.keys() - from_nodes.keys():
        nodes_added += 1
        node_diffs.append(
            NodeDiff(
                label=label,
                change_type="added",
                fields_changed=None,
                from_def=None,
                to_def=to_nodes[label].to_dict(),
            )
        )

    # Find removed nodes
    for label in from_nodes.keys() - to_nodes.keys():
        nodes_removed += 1
        node_diffs.append(
            NodeDiff(
                label=label,
                change_type="removed",
                fields_changed=None,
                from_def=from_nodes[label].to_dict(),
                to_def=None,
            )
        )

    # Find modified nodes
    for label in from_nodes.keys() & to_nodes.keys():
        from_node = from_nodes[label]
        to_node = to_nodes[label]

        fields_changed = _diff_node_definition(from_node, to_node)
        if fields_changed:
            nodes_modified += 1
            node_diffs.append(
                NodeDiff(
                    label=label,
                    change_type="modified",
                    fields_changed=fields_changed,
                    from_def=from_node.to_dict(),
                    to_def=to_node.to_dict(),
                )
            )

    # Compute edge diffs
    edge_diffs: list[EdgeDiff] = []
    edges_added = 0
    edges_removed = 0
    edges_modified = 0

    # Find added edges
    for edge_type in to_edges.keys() - from_edges.keys():
        edges_added += 1
        edge_diffs.append(
            EdgeDiff(
                type=edge_type,
                change_type="added",
                fields_changed=None,
                from_def=None,
                to_def=to_edges[edge_type].to_dict(),
            )
        )

    # Find removed edges
    for edge_type in from_edges.keys() - to_edges.keys():
        edges_removed += 1
        edge_diffs.append(
            EdgeDiff(
                type=edge_type,
                change_type="removed",
                fields_changed=None,
                from_def=from_edges[edge_type].to_dict(),
                to_def=None,
            )
        )

    # Find modified edges
    for edge_type in from_edges.keys() & to_edges.keys():
        from_edge = from_edges[edge_type]
        to_edge = to_edges[edge_type]

        fields_changed = _diff_edge_definition(from_edge, to_edge)
        if fields_changed:
            edges_modified += 1
            edge_diffs.append(
                EdgeDiff(
                    type=edge_type,
                    change_type="modified",
                    fields_changed=fields_changed,
                    from_def=from_edge.to_dict(),
                    to_def=to_edge.to_dict(),
                )
            )

    return MappingDiffResult(
        mapping_id=from_version.mapping_id,
        from_version=from_version.version,
        to_version=to_version.version,
        nodes_added=nodes_added,
        nodes_removed=nodes_removed,
        nodes_modified=nodes_modified,
        edges_added=edges_added,
        edges_removed=edges_removed,
        edges_modified=edges_modified,
        node_diffs=node_diffs,
        edge_diffs=edge_diffs,
    )


def _diff_node_definition(from_node: NodeDefinition, to_node: NodeDefinition) -> list[str]:
    """
    Returns list of changed field names (e.g., ["sql", "properties"]).

    Uses DeepDiff to detect changes in node definition fields.
    """
    from_dict = from_node.to_dict()
    to_dict = to_node.to_dict()

    # Use DeepDiff to find what changed
    diff = DeepDiff(from_dict, to_dict, ignore_order=False, report_repetition=True)

    if not diff:
        return []

    # Extract changed field names from DeepDiff result
    changed_fields: set[str] = set()

    # Check for value changes
    if "values_changed" in diff:
        for path in diff["values_changed"].keys():
            field = _extract_top_level_field(path)
            if field:
                changed_fields.add(field)

    # Check for type changes
    if "type_changes" in diff:
        for path in diff["type_changes"].keys():
            field = _extract_top_level_field(path)
            if field:
                changed_fields.add(field)

    # Check for added/removed items in lists
    if "iterable_item_added" in diff or "iterable_item_removed" in diff:
        for path in list(diff.get("iterable_item_added", {}).keys()) + list(
            diff.get("iterable_item_removed", {}).keys()
        ):
            field = _extract_top_level_field(path)
            if field:
                changed_fields.add(field)

    return sorted(changed_fields)


def _diff_edge_definition(from_edge: EdgeDefinition, to_edge: EdgeDefinition) -> list[str]:
    """
    Returns list of changed field names for edge definitions.

    Uses DeepDiff to detect changes in edge definition fields.
    """
    from_dict = from_edge.to_dict()
    to_dict = to_edge.to_dict()

    # Use DeepDiff to find what changed
    diff = DeepDiff(from_dict, to_dict, ignore_order=False, report_repetition=True)

    if not diff:
        return []

    # Extract changed field names from DeepDiff result
    changed_fields: set[str] = set()

    # Check for value changes
    if "values_changed" in diff:
        for path in diff["values_changed"].keys():
            field = _extract_top_level_field(path)
            if field:
                changed_fields.add(field)

    # Check for type changes
    if "type_changes" in diff:
        for path in diff["type_changes"].keys():
            field = _extract_top_level_field(path)
            if field:
                changed_fields.add(field)

    # Check for added/removed items in lists
    if "iterable_item_added" in diff or "iterable_item_removed" in diff:
        for path in list(diff.get("iterable_item_added", {}).keys()) + list(
            diff.get("iterable_item_removed", {}).keys()
        ):
            field = _extract_top_level_field(path)
            if field:
                changed_fields.add(field)

    return sorted(changed_fields)


def _extract_top_level_field(deepdiff_path: str) -> str | None:
    """
    Extract top-level field name from DeepDiff path.

    Examples:
        "root['sql']" -> "sql"
        "root['properties'][0]" -> "properties"
        "root['primary_key']['name']" -> "primary_key"

    Args:
        deepdiff_path: Path string from DeepDiff output

    Returns:
        Top-level field name or None if path doesn't match expected format
    """
    # DeepDiff paths look like: root['field_name'] or root['field_name'][index]
    if not deepdiff_path.startswith("root["):
        return None

    # Extract first field name after 'root['
    parts = deepdiff_path[5:]  # Skip 'root['
    if "']" in parts:
        field_name = parts.split("']")[0].strip("'\"")
        return field_name

    return None
