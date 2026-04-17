"""Utilities for rendering mapping version diffs in Jupyter notebooks.

These helpers provide additional ways to visualize diff results beyond
the automatic HTML rendering built into MappingDiff._repr_html_().
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from graph_olap.models.mapping import MappingDiff


def render_diff_summary(diff: MappingDiff) -> None:
    """Display a formatted summary of the diff.

    Args:
        diff: MappingDiff object

    Example:
        >>> from graph_olap.utils.diff import render_diff_summary
        >>> diff = client.mappings.diff(mapping_id=1, from_version=1, to_version=2)
        >>> render_diff_summary(diff)
        Mapping Diff: v1 → v2
        =====================
        Nodes:   +1  -0  ~0
        Edges:   +0  -0  ~1
    """
    s = diff.summary
    print(f"Mapping Diff: v{diff.from_version} → v{diff.to_version}")
    print("=" * 40)
    print(
        f"Nodes:   +{s['nodes_added']}  -{s['nodes_removed']}  ~{s['nodes_modified']}"
    )
    print(
        f"Edges:   +{s['edges_added']}  -{s['edges_removed']}  ~{s['edges_modified']}"
    )


def render_diff_details(diff: MappingDiff, show_from_to: bool = False) -> None:
    """Display detailed changes line by line.

    Args:
        diff: MappingDiff object
        show_from_to: Whether to show before/after details (can be verbose)

    Example:
        >>> from graph_olap.utils.diff import render_diff_details
        >>> diff = client.mappings.diff(mapping_id=1, from_version=1, to_version=2)
        >>> render_diff_details(diff)
        + Node: Supplier
        ~ Node: Customer (sql, properties)
        ~ Edge: PURCHASED (properties)
    """
    # Show added nodes
    for node in diff.nodes_added():
        print(f"+ Node: {node.label}")
        if show_from_to and node.to:
            print(f"    SQL: {node.to.get('sql', 'N/A')}")

    # Show removed nodes
    for node in diff.nodes_removed():
        print(f"- Node: {node.label}")

    # Show modified nodes
    for node in diff.nodes_modified():
        fields = ", ".join(node.fields_changed or [])
        print(f"~ Node: {node.label} ({fields})")
        if show_from_to and node.from_ and node.to:
            for field in node.fields_changed or []:
                print(f"    {field}:")
                print(f"      Before: {node.from_.get(field)}")
                print(f"      After:  {node.to.get(field)}")

    # Show added edges
    for edge in diff.edges_added():
        print(f"+ Edge: {edge.type}")

    # Show removed edges
    for edge in diff.edges_removed():
        print(f"- Edge: {edge.type}")

    # Show modified edges
    for edge in diff.edges_modified():
        fields = ", ".join(edge.fields_changed or [])
        print(f"~ Edge: {edge.type} ({fields})")


def diff_to_dict(diff: MappingDiff) -> dict:
    """Convert diff to a simple dict for custom rendering.

    Args:
        diff: MappingDiff object

    Returns:
        Dictionary representation of the diff

    Example:
        >>> from graph_olap.utils.diff import diff_to_dict
        >>> diff = client.mappings.diff(mapping_id=1, from_version=1, to_version=2)
        >>> data = diff_to_dict(diff)
        >>> import pandas as pd
        >>> pd.DataFrame(data['changes'])
    """
    changes = []

    for node in diff.nodes_added():
        changes.append({
            "type": "node",
            "name": node.label,
            "change": "added",
            "fields": None,
        })

    for node in diff.nodes_removed():
        changes.append({
            "type": "node",
            "name": node.label,
            "change": "removed",
            "fields": None,
        })

    for node in diff.nodes_modified():
        changes.append({
            "type": "node",
            "name": node.label,
            "change": "modified",
            "fields": ", ".join(node.fields_changed or []),
        })

    for edge in diff.edges_added():
        changes.append({
            "type": "edge",
            "name": edge.type,
            "change": "added",
            "fields": None,
        })

    for edge in diff.edges_removed():
        changes.append({
            "type": "edge",
            "name": edge.type,
            "change": "removed",
            "fields": None,
        })

    for edge in diff.edges_modified():
        changes.append({
            "type": "edge",
            "name": edge.type,
            "change": "modified",
            "fields": ", ".join(edge.fields_changed or []),
        })

    return {
        "mapping_id": diff.mapping_id,
        "from_version": diff.from_version,
        "to_version": diff.to_version,
        "summary": diff.summary,
        "changes": changes,
    }
