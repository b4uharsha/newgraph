"""Common Pydantic models used across the SDK."""

from __future__ import annotations

import base64
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    pass

T = TypeVar("T")


class PaginatedList(BaseModel, Generic[T]):
    """Paginated list of items from API."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    items: list[T]
    total: int
    offset: int
    limit: int

    def __iter__(self) -> Iterator[T]:
        """Iterate over items."""
        return iter(self.items)

    def __len__(self) -> int:
        """Return number of items in current page."""
        return len(self.items)

    def __getitem__(self, index: int) -> T:
        """Get item by index."""
        return self.items[index]

    @property
    def has_more(self) -> bool:
        """Check if there are more items to fetch."""
        return self.offset + len(self.items) < self.total

    @property
    def page_count(self) -> int:
        """Total number of pages."""
        if self.limit == 0:
            return 0
        return (self.total + self.limit - 1) // self.limit


class QueryResult(BaseModel):
    """Result of a Cypher query with multiple output format options.

    Analysts can convert results to their preferred format:
    - DataFrames (polars/pandas) for tabular analysis
    - Dicts for programmatic access
    - NetworkX for graph algorithms

    Examples:
        >>> result = conn.query("MATCH (n:Customer) RETURN n.name, n.age LIMIT 10")

        >>> # As DataFrame
        >>> df = result.to_polars()
        >>> df = result.to_pandas()

        >>> # As list of dicts
        >>> for row in result:
        ...     print(row["name"], row["age"])

        >>> # Single value
        >>> count = conn.query("RETURN count(*)").scalar()
    """

    model_config = ConfigDict(frozen=True)

    columns: list[str]
    column_types: list[str] = []  # Ryugraph types: STRING, INT64, DATE, TIMESTAMP, etc.
    rows: list[list[Any]]
    row_count: int
    execution_time_ms: int = 0

    @classmethod
    def from_api_response(cls, data: dict[str, Any], coerce_types: bool = True) -> QueryResult:
        """Create QueryResult from API response.

        Args:
            data: API response data dict
            coerce_types: If True, convert DATE/TIMESTAMP/INTERVAL to Python types
        """
        columns = data["columns"]
        # Use "or" to handle both missing key AND empty list from wrappers
        column_types = data.get("column_types") or ["STRING"] * len(columns)
        rows = data["rows"]

        if coerce_types:
            rows = _coerce_rows(rows, column_types)

        return cls(
            columns=columns,
            column_types=column_types,
            rows=rows,
            row_count=data["row_count"],
            execution_time_ms=data["execution_time_ms"],
        )

    def __iter__(self) -> Iterator[dict[str, Any]]:
        """Iterate over rows as dicts."""
        for row in self.rows:
            yield dict(zip(self.columns, row, strict=True))

    def __len__(self) -> int:
        """Return number of rows."""
        return self.row_count

    def to_dicts(self) -> list[dict[str, Any]]:
        """Convert to list of dictionaries."""
        return list(self)

    def to_list_of_dicts(self) -> list[dict[str, Any]]:
        """Convert to list of dictionaries (alias for to_dicts)."""
        return self.to_dicts()

    def scalar(self) -> Any:
        """Return single scalar value.

        Raises:
            ValueError: If result has more than one row or column.
        """
        if self.row_count != 1 or len(self.columns) != 1:
            raise ValueError(
                f"Expected single value, got {self.row_count} rows and {len(self.columns)} columns"
            )
        return self.rows[0][0]

    def to_polars(self) -> Any:
        """Convert to Polars DataFrame.

        Returns:
            polars.DataFrame

        Raises:
            ImportError: If polars is not installed.
        """
        try:
            import polars as pl
        except ImportError as e:
            raise ImportError(
                "polars is required for to_polars(). "
                "Install with: pip install graph-olap-sdk[dataframe]"
            ) from e

        return pl.DataFrame(
            {col: [row[i] for row in self.rows] for i, col in enumerate(self.columns)}
        )

    def to_pandas(self) -> Any:
        """Convert to Pandas DataFrame.

        Returns:
            pandas.DataFrame

        Raises:
            ImportError: If pandas is not installed.
        """
        try:
            import pandas as pd
        except ImportError as e:
            raise ImportError(
                "pandas is required for to_pandas(). "
                "Install with: pip install graph-olap-sdk[dataframe]"
            ) from e

        return pd.DataFrame(self.rows, columns=self.columns)

    def to_networkx(self) -> Any:
        """Convert to NetworkX graph (when result contains nodes/edges).

        Returns:
            networkx.Graph or networkx.DiGraph

        Raises:
            ImportError: If networkx is not installed.
        """
        try:
            import networkx as nx
        except ImportError as e:
            raise ImportError(
                "networkx is required for to_networkx(). "
                "Install with: pip install graph-olap-sdk[viz]"
            ) from e

        G = nx.DiGraph()

        for row in self:
            for value in row.values():
                if isinstance(value, dict):
                    if "_label" in value:  # Node
                        node_id = value.get("_id")
                        props = {k: v for k, v in value.items() if not k.startswith("_")}
                        props["_label"] = value["_label"]
                        G.add_node(node_id, **props)
                    elif "_type" in value:  # Edge
                        G.add_edge(
                            value.get("_src"),
                            value.get("_dst"),
                            _type=value.get("_type"),
                            **{k: v for k, v in value.items() if not k.startswith("_")},
                        )

        return G

    def to_csv(self, path: str) -> None:
        """Export to CSV file."""
        df = self.to_polars()
        df.write_csv(path)

    def to_parquet(self, path: str) -> None:
        """Export to Parquet file."""
        df = self.to_polars()
        df.write_parquet(path)

    def show(self, max_rows: int = 20) -> Any:
        """Display in Jupyter with auto-selected visualization.

        For tabular data, uses itables for interactive display.
        For graph data, uses pyvis for visualization.
        """
        try:
            from IPython.display import display  # noqa: F401 - used for IPython detection

            # Check if we have graph data
            has_nodes = any(isinstance(v, dict) and "_label" in v for row in self.rows for v in row)

            if has_nodes:
                # Graph visualization
                return self._show_graph(max_rows)
            else:
                # Tabular display
                return self._show_table(max_rows)
        except ImportError:
            # Not in Jupyter, print as table
            return self._print_table(max_rows)

    def _show_table(self, max_rows: int) -> Any:
        """Show as interactive table."""
        try:
            from itables import show

            df = self.to_pandas()
            return show(df.head(max_rows))
        except ImportError:
            return self._print_table(max_rows)

    def _show_graph(self, max_rows: int) -> Any:
        """Show as graph visualization."""
        try:
            from pyvis.network import Network

            G = self.to_networkx()
            net = Network(notebook=True, height="500px", width="100%")
            net.from_nx(G)
            return net.show("graph.html")
        except ImportError:
            return self._print_table(max_rows)

    def _print_table(self, max_rows: int) -> None:
        """Print as text table."""
        print(" | ".join(self.columns))
        print("-" * (len(self.columns) * 15))
        for row in self.rows[:max_rows]:
            print(" | ".join(str(v)[:15] for v in row))
        if self.row_count > max_rows:
            print(f"... and {self.row_count - max_rows} more rows")

    def _repr_html_(self) -> str:
        """Rich HTML display for Jupyter notebooks."""
        rows_html = ""
        for row in self.rows[:10]:
            cells = "".join(
                f"<td style='padding: 6px; border: 1px solid #e1e4e8;'>{v}</td>" for v in row
            )
            rows_html += f"<tr>{cells}</tr>"

        more_rows = ""
        if self.row_count > 10:
            more_rows = f"<tr><td colspan='{len(self.columns)}' style='padding: 6px; color: #586069; text-align: center;'>... and {self.row_count - 10} more rows</td></tr>"

        headers = "".join(
            f"<th style='padding: 6px; background: #f6f8fa; border: 1px solid #e1e4e8;'>{col}</th>"
            for col in self.columns
        )

        return f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; font-size: 13px;">
            <div style="color: #586069; margin-bottom: 8px;">{self.row_count} rows, {self.execution_time_ms}ms</div>
            <table style="border-collapse: collapse; width: 100%;">
                <thead><tr>{headers}</tr></thead>
                <tbody>{rows_html}{more_rows}</tbody>
            </table>
        </div>
        """


class AlgorithmExecution(BaseModel):
    """Result of algorithm execution.

    Uses shared enums from graph-olap-schemas for consistency with wrapper API.

    Duration fields:
    - elapsed_ms: Time since execution started (available while running)
    - duration_ms: Total execution time (set when completed)
    """

    model_config = ConfigDict(frozen=True)

    execution_id: str
    algorithm: str
    algorithm_type: str | None = None  # "native" or "networkx"
    status: str  # "pending", "running", "completed", "failed", "cancelled"
    started_at: datetime
    completed_at: datetime | None = None
    result_property: str | None = None
    node_label: str | None = None
    nodes_updated: int | None = None
    elapsed_ms: int | None = None  # Available while running
    duration_ms: int | None = None  # Set when completed
    error_message: str | None = None
    result: dict[str, Any] | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> AlgorithmExecution:
        """Create from API response data.

        Handles both field naming conventions:
        - SDK format: algorithm
        - Wrapper format: algorithm_name

        Also handles enum types from shared schemas (ExecutionStatus, AlgorithmType).
        """
        # Get algorithm name (wrapper uses algorithm_name, SDK uses algorithm)
        algorithm = data.get("algorithm_name") or data.get("algorithm", "")

        # Get status (may be enum value or string)
        status = data.get("status", "")
        if hasattr(status, "value"):
            status = status.value

        # Get algorithm_type (may be enum value or string)
        algorithm_type = data.get("algorithm_type")
        if hasattr(algorithm_type, "value"):
            algorithm_type = algorithm_type.value

        return cls(
            execution_id=data["execution_id"],
            algorithm=algorithm,
            algorithm_type=algorithm_type,
            status=status,
            started_at=_parse_datetime(data["started_at"]),
            completed_at=_parse_datetime(data["completed_at"])
            if data.get("completed_at")
            else None,
            result_property=data.get("result_property"),
            node_label=data.get("node_label"),
            nodes_updated=data.get("nodes_updated"),
            elapsed_ms=data.get("elapsed_ms"),
            duration_ms=data.get("duration_ms"),
            error_message=data.get("error_message"),
            result=data.get("result"),
        )


class Schema(BaseModel):
    """Graph schema with node labels and relationship types."""

    model_config = ConfigDict(frozen=True)

    node_labels: dict[str, list[str]]  # label -> [property names]
    relationship_types: dict[str, list[str]]  # type -> [property names]
    node_count: int
    relationship_count: int

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> Schema:
        """Create from API response data.

        Handles both formats:
        - SDK format: node_labels, relationship_types dicts
        - Wrapper format: node_tables, edge_tables lists
        """
        # Check if it's wrapper format (has node_tables/edge_tables)
        if "node_tables" in data:
            # Transform wrapper format to SDK format
            node_labels = {}
            for table in data.get("node_tables", []):
                label = table.get("label")
                props = list(table.get("properties", {}).keys())
                node_labels[label] = props

            relationship_types = {}
            for table in data.get("edge_tables", []):
                rel_type = table.get("type")
                props = list(table.get("properties", {}).keys())
                relationship_types[rel_type] = props

            return cls(
                node_labels=node_labels,
                relationship_types=relationship_types,
                node_count=data.get("total_nodes", 0),
                relationship_count=data.get("total_edges", 0),
            )

        # SDK format (legacy)
        return cls(
            node_labels=data.get("node_labels", {}),
            relationship_types=data.get("relationship_types", {}),
            node_count=data.get("node_count", 0),
            relationship_count=data.get("relationship_count", 0),
        )

    def _repr_html_(self) -> str:
        """Rich HTML display for Jupyter notebooks."""
        nodes_html = ""
        for label, props in self.node_labels.items():
            props_str = ", ".join(props) if props else "<em>no properties</em>"
            nodes_html += f"<tr><td style='padding: 4px;'><strong>{label}</strong></td><td style='padding: 4px;'>{props_str}</td></tr>"

        rels_html = ""
        for rel_type, props in self.relationship_types.items():
            props_str = ", ".join(props) if props else "<em>no properties</em>"
            rels_html += f"<tr><td style='padding: 4px;'><strong>{rel_type}</strong></td><td style='padding: 4px;'>{props_str}</td></tr>"

        return f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; font-size: 13px;">
            <h4 style="margin: 0 0 12px 0;">Graph Schema</h4>
            <div style="color: #586069; margin-bottom: 8px;">{self.node_count:,} nodes, {self.relationship_count:,} relationships</div>

            <h5 style="margin: 12px 0 8px 0;">Node Labels</h5>
            <table style="border-collapse: collapse;">{nodes_html}</table>

            <h5 style="margin: 12px 0 8px 0;">Relationship Types</h5>
            <table style="border-collapse: collapse;">{rels_html}</table>
        </div>
        """


class Favorite(BaseModel):
    """User favorite/bookmark."""

    model_config = ConfigDict(frozen=True)

    resource_type: str  # mapping, instance
    resource_id: int
    resource_name: str
    created_at: datetime

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> Favorite:
        """Create from API response data."""
        return cls(
            resource_type=data["resource_type"],
            resource_id=data["resource_id"],
            resource_name=data.get("resource_name") or "",
            created_at=_parse_datetime(data["created_at"]),
        )


# =============================================================================
# Type Coercion Helpers
# =============================================================================


def _parse_datetime(value: str) -> datetime:
    """Parse ISO datetime string, handling Z suffix."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _coerce_rows(rows: list[list[Any]], column_types: list[str]) -> list[list[Any]]:
    """Convert string representations to proper Python types."""
    coerced = []
    for row in rows:
        coerced_row = []
        for value, col_type in zip(row, column_types, strict=True):
            coerced_row.append(_coerce_value(value, col_type))
        coerced.append(coerced_row)
    return coerced


def _coerce_value(value: Any, col_type: str) -> Any:
    """Coerce a single value based on its column type."""
    if value is None:
        return None

    col_type = col_type.upper()

    # Date/time types
    if col_type == "DATE" and isinstance(value, str):
        return date.fromisoformat(value)

    if col_type == "TIMESTAMP" and isinstance(value, str):
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)

    if col_type == "INTERVAL" and isinstance(value, str):
        return _parse_interval(value)

    # Binary data
    if col_type == "BLOB" and isinstance(value, str):
        return base64.b64decode(value)

    # NODE - recursively coerce properties
    if isinstance(value, dict) and "_label" in value:
        return _coerce_node(value)

    # REL - recursively coerce properties
    if isinstance(value, dict) and "_type" in value:
        return _coerce_rel(value)

    # LIST - recursive
    if col_type.startswith("LIST") and isinstance(value, list):
        inner_type = col_type[5:-1] if col_type.startswith("LIST<") else "STRING"
        return [_coerce_value(v, inner_type) for v in value]

    return value


def _coerce_node(node: dict[str, Any]) -> dict[str, Any]:
    """Coerce node properties based on their apparent types."""
    result = {"_id": node["_id"], "_label": node["_label"]}
    for key, value in node.items():
        if not key.startswith("_"):
            result[key] = _infer_and_coerce(value)
    return result


def _coerce_rel(rel: dict[str, Any]) -> dict[str, Any]:
    """Coerce relationship properties."""
    result = {
        "_id": rel.get("_id"),
        "_type": rel["_type"],
        "_src": rel.get("_src"),
        "_dst": rel.get("_dst"),
    }
    for key, value in rel.items():
        if not key.startswith("_"):
            result[key] = _infer_and_coerce(value)
    return result


def _infer_and_coerce(value: Any) -> Any:
    """Infer type from value and coerce if needed."""
    if value is None:
        return None

    if isinstance(value, str):
        # Try date
        if len(value) == 10 and value[4] == "-" and value[7] == "-":
            try:
                return date.fromisoformat(value)
            except ValueError:
                pass

        # Try datetime
        if "T" in value:
            try:
                if value.endswith("Z"):
                    value = value[:-1] + "+00:00"
                return datetime.fromisoformat(value)
            except ValueError:
                pass

    return value


def _parse_interval(value: str) -> timedelta:
    """Parse ISO 8601 duration string to timedelta.

    Examples:
        PT1H -> 1 hour
        PT30M -> 30 minutes
        P1D -> 1 day
        P1DT2H30M -> 1 day, 2 hours, 30 minutes
    """
    import re

    pattern = r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?"
    match = re.match(pattern, value)

    if not match:
        raise ValueError(f"Invalid interval format: {value}")

    days = int(match.group(1) or 0)
    hours = int(match.group(2) or 0)
    minutes = int(match.group(3) or 0)
    seconds = int(match.group(4) or 0)

    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
