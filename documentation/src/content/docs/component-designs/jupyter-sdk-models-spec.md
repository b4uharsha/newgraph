---
title: "Jupyter SDK Models Specification"
scope: hsbc
---

# Jupyter SDK Models Specification

Immutable **Pydantic** models used by the Jupyter SDK. All models are
``pydantic.BaseModel`` subclasses with ``model_config = ConfigDict(frozen=True)``
(sometimes also ``arbitrary_types_allowed=True``). Deserialization always goes
through a classmethod named ``from_api_response(cls, data: dict | BaseModel)``
so that API envelope variations (e.g. ``{"data": {...}}`` vs. the payload
returned directly) can be normalized in one place.

> **Historical note:** earlier drafts of this spec used stdlib ``@dataclass``
> plus ``from_dict``. That form is retained in-page as a readability shortcut
> for the *field set*, but the actual implementation is always
> ``BaseModel + ConfigDict(frozen=True) + from_api_response``. Treat every
> ``@dataclass`` block below as equivalent to the Pydantic pattern:
>
> ```python
> from pydantic import BaseModel, ConfigDict
>
> class NodeDefinition(BaseModel):
>     model_config = ConfigDict(frozen=True)
>     label: str
>     sql: str
>     primary_key: PropertyDefinition
>     properties: list[PropertyDefinition]
>
>     @classmethod
>     def from_api_response(cls, data: dict) -> "NodeDefinition":
>         return cls.model_validate(data)
> ```

## Prerequisites

- [jupyter-sdk.design.md](-/jupyter-sdk.design.md) - Core SDK design

## Related Components

- [jupyter-sdk.connection.design.md](-/jupyter-sdk.connection.design.md) - Instance connection
- [api.mappings.spec.md](--/system-design/api/api.mappings.spec.md) - API response schemas

---

## Shipped Model Inventory

The SDK models live under ``graph_olap/models/`` and are grouped by the
bounded context they describe:

| Module | Key models |
|--------|-----------|
| ``models/common.py`` | ``PaginatedList[T]``, ``QueryResult``, ``Schema``, ``AlgorithmExecution``, ``PropertyDefinition`` |
| ``models/mapping.py`` | ``Mapping``, ``MappingVersion``, ``NodeDefinition``, ``EdgeDefinition``, ``MappingDiff``, ``NodeDiff``, ``EdgeDiff`` |
| ``models/snapshot.py`` | ``Snapshot``, ``SnapshotProgress`` |
| ``models/instance.py`` | ``Instance``, ``InstanceProgress``, ``LockStatus``, ``WrapperType`` |
| ``models/schema.py`` | Starburst schema inspection models |
| ``models/ops.py`` | ``LifecycleConfig``, ``ResourceLifecycleConfig``, ``ConcurrencyConfig``, ``MaintenanceMode``, ``ClusterHealth`` |

All of the lifecycle / ops models (``InstanceProgress``, ``LockStatus``,
``NodeDiff``, ``EdgeDiff``, ``MappingDiff``, ``LifecycleConfig``,
``ConcurrencyConfig``, ``MaintenanceMode``, ``ClusterHealth``) are first-class
exported types — they are not stubs.

---

## Model Definitions

### Mapping Models

```python
# models/mapping.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

class PropertyDefinition(BaseModel):
    """Single typed property on a node or edge table."""
    model_config = ConfigDict(frozen=True)
    name: str
    type: str               # Ryugraph type: STRING, INT64, DATE, TIMESTAMP, ...
    nullable: bool = True


class NodeDefinition(BaseModel):
    """Node table definition for graph mapping."""
    model_config = ConfigDict(frozen=True)
    label: str
    sql: str
    primary_key: PropertyDefinition
    properties: list[PropertyDefinition]  # typed, NOT list[dict]

    @classmethod
    def from_api_response(cls, data: dict) -> "NodeDefinition":
        return cls.model_validate(data)


class EdgeDefinition(BaseModel):
    """Edge table definition for graph mapping."""
    model_config = ConfigDict(frozen=True)
    type: str
    from_node: str
    to_node: str
    sql: str
    from_key: str
    to_key: str
    properties: list[PropertyDefinition]  # typed, NOT list[dict]

    @classmethod
    def from_api_response(cls, data: dict) -> "EdgeDefinition":
        return cls.model_validate(data)


@dataclass
class MappingVersion:
    """Immutable mapping version."""
    mapping_id: int
    version: int
    change_description: str | None
    node_definitions: list[NodeDefinition]
    edge_definitions: list[EdgeDefinition]
    created_at: datetime
    created_by: str
    created_by_name: str

    @classmethod
    def from_dict(cls, data: dict) -> "MappingVersion":
        return cls(
            mapping_id=data["mapping_id"],
            version=data["version"],
            change_description=data.get("change_description"),
            node_definitions=[NodeDefinition.from_dict(n) for n in data["node_definitions"]],
            edge_definitions=[EdgeDefinition.from_dict(e) for e in data["edge_definitions"]],
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            created_by=data["created_by"],
            created_by_name=data["created_by_name"],
        )


@dataclass
class Mapping:
    """Graph mapping definition."""
    id: int
    owner_username: str
    name: str
    description: str | None
    current_version: int
    created_at: datetime
    updated_at: datetime
    ttl: str | None
    inactivity_timeout: str | None
    snapshot_count: int
    version: MappingVersion | None = None  # Included when fetching single mapping

    @classmethod
    def from_dict(cls, data: dict) -> "Mapping":
        version = None
        if "version" in data and data["version"]:
            version = MappingVersion.from_dict(data["version"])

        return cls(
            id=data["id"],
            owner_username=data["owner_username"],
            name=data["name"],
            description=data.get("description"),
            current_version=data["current_version"],
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00")),
            ttl=data.get("ttl"),
            inactivity_timeout=data.get("inactivity_timeout"),
            snapshot_count=data.get("snapshot_count", 0),
            version=version,
        )

    def _repr_html_(self) -> str:
        """Rich HTML display for Jupyter notebooks."""
        return f"""
        <div style="border: 1px solid #ddd; padding: 10px; border-radius: 5px; margin: 5px 0;">
            <h4 style="margin: 0 0 10px 0;">Mapping: {self.name}</h4>
            <table style="border-collapse: collapse;">
                <tr><td style="padding: 2px 10px;"><strong>ID:</strong></td><td>{self.id}</td></tr>
                <tr><td style="padding: 2px 10px;"><strong>Owner:</strong></td><td>{self.owner_username}</td></tr>
                <tr><td style="padding: 2px 10px;"><strong>Version:</strong></td><td>{self.current_version}</td></tr>
                <tr><td style="padding: 2px 10px;"><strong>Snapshots:</strong></td><td>{self.snapshot_count}</td></tr>
            </table>
        </div>
        """
```

### Snapshot Model

```python
# models/snapshot.py
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Snapshot:
    """Data snapshot from mapping export."""
    id: int
    mapping_id: int
    mapping_name: str
    mapping_version: int
    owner_username: str
    name: str
    description: str | None
    gcs_path: str
    size_bytes: int | None
    node_counts: dict[str, int] | None
    edge_counts: dict[str, int] | None
    status: str  # pending, creating, ready, failed
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    ttl: str | None
    inactivity_timeout: str | None
    instance_count: int

    @classmethod
    def from_dict(cls, data: dict) -> "Snapshot":
        return cls(
            id=data["id"],
            mapping_id=data["mapping_id"],
            mapping_name=data.get("mapping_name", ""),
            mapping_version=data["mapping_version"],
            owner_username=data["owner_username"],
            name=data["name"],
            description=data.get("description"),
            gcs_path=data.get("gcs_path", ""),
            size_bytes=data.get("size_bytes"),
            node_counts=data.get("node_counts"),
            edge_counts=data.get("edge_counts"),
            status=data["status"],
            error_message=data.get("error_message"),
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00")),
            ttl=data.get("ttl"),
            inactivity_timeout=data.get("inactivity_timeout"),
            instance_count=data.get("instance_count", 0),
        )

    def _repr_html_(self) -> str:
        """Rich HTML display for Jupyter notebooks."""
        status_color = {
            "ready": "#28a745",
            "creating": "#007bff",
            "pending": "#6c757d",
            "failed": "#dc3545",
        }.get(self.status, "#6c757d")

        return f"""
        <div style="border: 1px solid #ddd; padding: 10px; border-radius: 5px; margin: 5px 0;">
            <h4 style="margin: 0 0 10px 0;">Snapshot: {self.name}</h4>
            <span style="background: {status_color}; color: white; padding: 2px 8px; border-radius: 3px;">{self.status}</span>
            <table style="border-collapse: collapse; margin-top: 10px;">
                <tr><td style="padding: 2px 10px;"><strong>ID:</strong></td><td>{self.id}</td></tr>
                <tr><td style="padding: 2px 10px;"><strong>Mapping:</strong></td><td>{self.mapping_name} (v{self.mapping_version})</td></tr>
                <tr><td style="padding: 2px 10px;"><strong>Owner:</strong></td><td>{self.owner_username}</td></tr>
                <tr><td style="padding: 2px 10px;"><strong>Instances:</strong></td><td>{self.instance_count}</td></tr>
            </table>
        </div>
        """
```

### Instance Model

```python
# models/instance.py
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Instance:
    """Running graph instance."""
    id: int
    snapshot_id: int
    snapshot_name: str
    owner_username: str
    name: str
    description: str | None
    instance_url: str | None
    status: str  # starting, running, stopping, failed
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    last_activity_at: datetime | None
    ttl: str | None
    inactivity_timeout: str | None
    memory_usage_bytes: int | None
    disk_usage_bytes: int | None

    @classmethod
    def from_dict(cls, data: dict) -> "Instance":
        return cls(
            id=data["id"],
            snapshot_id=data["snapshot_id"],
            snapshot_name=data.get("snapshot_name", ""),
            owner_username=data["owner_username"],
            name=data["name"],
            description=data.get("description"),
            instance_url=data.get("instance_url"),
            status=data["status"],
            error_message=data.get("error_message"),
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00")),
            started_at=datetime.fromisoformat(data["started_at"].replace("Z", "+00:00")) if data.get("started_at") else None,
            last_activity_at=datetime.fromisoformat(data["last_activity_at"].replace("Z", "+00:00")) if data.get("last_activity_at") else None,
            ttl=data.get("ttl"),
            inactivity_timeout=data.get("inactivity_timeout"),
            memory_usage_bytes=data.get("memory_usage_bytes"),
            disk_usage_bytes=data.get("disk_usage_bytes"),
        )

    def _repr_html_(self) -> str:
        """Rich HTML display for Jupyter notebooks."""
        status_color = {
            "running": "#28a745",
            "starting": "#007bff",
            "stopping": "#ffc107",
            "failed": "#dc3545",
        }.get(self.status, "#6c757d")

        memory_mb = f"{self.memory_usage_bytes / 1024 / 1024:.1f} MB" if self.memory_usage_bytes else "N/A"

        return f"""
        <div style="border: 1px solid #ddd; padding: 10px; border-radius: 5px; margin: 5px 0;">
            <h4 style="margin: 0 0 10px 0;">Instance: {self.name}</h4>
            <span style="background: {status_color}; color: white; padding: 2px 8px; border-radius: 3px;">{self.status}</span>
            <table style="border-collapse: collapse; margin-top: 10px;">
                <tr><td style="padding: 2px 10px;"><strong>ID:</strong></td><td>{self.id}</td></tr>
                <tr><td style="padding: 2px 10px;"><strong>URL:</strong></td><td><a href="{self.instance_url}">{self.instance_url}</a></td></tr>
                <tr><td style="padding: 2px 10px;"><strong>Memory:</strong></td><td>{memory_mb}</td></tr>
            </table>
        </div>
        """
```

### Common Models

```python
# models/common.py
from dataclasses import dataclass
from datetime import datetime

@dataclass
class QueryResult:
    """
    Result of a Cypher query with multiple output format options.

    Analysts can convert results to their preferred format:
    - DataFrames (polars/pandas) for tabular analysis
    - Dicts for programmatic access
    - NetworkX for graph algorithms
    - Scalar for single values (COUNT, SUM, etc.)

    Type coercion is automatic based on column_types from the API:
    - DATE strings → datetime.date
    - TIMESTAMP strings → datetime.datetime
    - INTERVAL strings → datetime.timedelta
    - BLOB base64 → bytes

    Examples:
        >>> result = conn.query("MATCH (n:Customer) RETURN n.name, n.age LIMIT 10")

        >>> # As DataFrame (most common)
        >>> df = result.to_polars()
        >>> df = result.to_pandas()

        >>> # As list of dicts
        >>> for row in result:
        ...     print(row["name"], row["age"])

        >>> # Single value
        >>> count = conn.query("RETURN count(*)").scalar()

        >>> # Export
        >>> result.to_csv("customers.csv")

        >>> # Disable type coercion for raw values
        >>> result = conn.query(cypher, coerce_types=False)
    """
    columns: list[str]
    column_types: list[str]  # Ryugraph types: STRING, INT64, DATE, TIMESTAMP, etc.
    rows: list[list]
    row_count: int
    execution_time_ms: int

    @classmethod
    def from_dict(cls, data: dict, coerce_types: bool = True) -> "QueryResult":
        """
        Create QueryResult from API response.

        Args:
            data: API response data dict
            coerce_types: If True, convert DATE/TIMESTAMP/INTERVAL to Python types
        """
        columns = data["columns"]
        column_types = data.get("column_types", ["STRING"] * len(columns))
        rows = data["rows"]

        if coerce_types:
            rows = cls._coerce_rows(rows, column_types)

        return cls(
            columns=columns,
            column_types=column_types,
            rows=rows,
            row_count=data["row_count"],
            execution_time_ms=data["execution_time_ms"],
        )

    @classmethod
    def _coerce_rows(cls, rows: list[list], column_types: list[str]) -> list[list]:
        """Convert string representations to proper Python types."""
        coerced = []
        for row in rows:
            coerced_row = []
            for i, (value, col_type) in enumerate(zip(row, column_types)):
                coerced_row.append(cls._coerce_value(value, col_type))
            coerced.append(coerced_row)
        return coerced

    @classmethod
    def _coerce_value(cls, value, col_type: str):
        """Coerce a single value based on its column type."""
        if value is None:
            return None

        col_type = col_type.upper()

        # Date/time types
        if col_type == "DATE" and isinstance(value, str):
            from datetime import date
            return date.fromisoformat(value)

        if col_type == "TIMESTAMP" and isinstance(value, str):
            from datetime import datetime
            # Handle ISO format with optional Z suffix
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            return datetime.fromisoformat(value)

        if col_type == "INTERVAL" and isinstance(value, str):
            return cls._parse_interval(value)

        # Binary data
        if col_type == "BLOB" and isinstance(value, str):
            import base64
            return base64.b64decode(value)

        # NODE - recursively coerce properties
        if isinstance(value, dict) and "_label" in value:
            return cls._coerce_node(value)

        # REL - recursively coerce properties
        if isinstance(value, dict) and "_type" in value:
            return cls._coerce_rel(value)

        # PATH - list of alternating nodes/rels
        if col_type == "PATH" and isinstance(value, list):
            return [
                cls._coerce_node(v) if "_label" in v else cls._coerce_rel(v)
                for v in value
            ]

        # LIST - recursive
        if col_type.startswith("LIST") and isinstance(value, list):
            # Extract inner type: LIST<STRING> -> STRING
            inner_type = col_type[5:-1] if col_type.startswith("LIST<") else "STRING"
            return [cls._coerce_value(v, inner_type) for v in value]

        return value

    @classmethod
    def _coerce_node(cls, node: dict) -> dict:
        """Coerce node properties based on their apparent types."""
        result = {"_id": node["_id"], "_label": node["_label"]}
        for key, value in node.items():
            if not key.startswith("_"):
                result[key] = cls._infer_and_coerce(value)
        return result

    @classmethod
    def _coerce_rel(cls, rel: dict) -> dict:
        """Coerce relationship properties."""
        result = {
            "_id": rel.get("_id"),
            "_type": rel["_type"],
            "_start": rel.get("_start"),
            "_end": rel.get("_end"),
        }
        for key, value in rel.items():
            if not key.startswith("_"):
                result[key] = cls._infer_and_coerce(value)
        return result

    @classmethod
    def _infer_and_coerce(cls, value):
        """Infer type from value format and coerce if needed."""
        if not isinstance(value, str):
            return value

        # ISO date pattern: YYYY-MM-DD
        if len(value) == 10 and value[4] == "-" and value[7] == "-":
            try:
                from datetime import date
                return date.fromisoformat(value)
            except ValueError:
                pass

        # ISO timestamp pattern
        if "T" in value and len(value) >= 19:
            try:
                from datetime import datetime
                if value.endswith("Z"):
                    value = value[:-1] + "+00:00"
                return datetime.fromisoformat(value)
            except ValueError:
                pass

        return value

    @staticmethod
    def _parse_interval(value: str) -> "timedelta":
        """Parse ISO 8601 duration string to timedelta."""
        from datetime import timedelta
        import re

        # Simple ISO 8601 duration: P1DT2H30M
        pattern = r'P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?'
        match = re.match(pattern, value)
        if match:
            days = int(match.group(1) or 0)
            hours = int(match.group(2) or 0)
            minutes = int(match.group(3) or 0)
            seconds = int(match.group(4) or 0)
            return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)

        return value  # Return as-is if can't parse

    # -------------------------------------------------------------------------
    # DataFrame Conversion
    # -------------------------------------------------------------------------

    def to_polars(self) -> "pl.DataFrame":
        """
        Convert to Polars DataFrame.

        Returns:
            polars.DataFrame with typed columns

        Example:
            >>> df = result.to_polars()
            >>> df.filter(pl.col("age") > 30).head()
        """
        import polars as pl
        if not self.rows:
            return pl.DataFrame(schema={col: pl.Utf8 for col in self.columns})
        return pl.DataFrame(dict(zip(self.columns, zip(*self.rows))))

    def to_pandas(self) -> "pd.DataFrame":
        """
        Convert to Pandas DataFrame.

        Returns:
            pandas.DataFrame

        Example:
            >>> df = result.to_pandas()
            >>> df[df["age"] > 30].head()
        """
        import pandas as pd
        return pd.DataFrame(self.rows, columns=self.columns)

    # -------------------------------------------------------------------------
    # Dict/JSON Conversion
    # -------------------------------------------------------------------------

    def to_dicts(self) -> list[dict]:
        """
        Convert to list of dictionaries.

        Returns:
            List of dicts, one per row

        Example:
            >>> rows = result.to_dicts()
            >>> rows[0]  # {'name': 'Alice', 'age': 30}
        """
        return [dict(zip(self.columns, row)) for row in self.rows]

    def to_json(self, path: str | None = None, indent: int = 2) -> str | None:
        """
        Convert to JSON string or write to file.

        Args:
            path: Optional file path to write to
            indent: JSON indentation (default 2)

        Returns:
            JSON string if path is None, else None
        """
        import json
        data = {"columns": self.columns, "rows": self.to_dicts()}
        if path:
            with open(path, "w") as f:
                json.dump(data, f, indent=indent, default=str)
            return None
        return json.dumps(data, indent=indent, default=str)

    # -------------------------------------------------------------------------
    # Scalar Extraction
    # -------------------------------------------------------------------------

    def scalar(self) -> any:
        """
        Extract single scalar value.

        Use for queries that return a single value like COUNT(*), SUM(), etc.

        Returns:
            The single value

        Raises:
            ValueError: If result has multiple rows or columns

        Example:
            >>> count = conn.query("MATCH (n) RETURN count(n)").scalar()
            >>> avg = conn.query("MATCH (n) RETURN avg(n.age)").scalar()
        """
        if self.row_count == 0:
            return None
        if self.row_count != 1 or len(self.columns) != 1:
            raise ValueError(
                f"scalar() requires exactly 1 row and 1 column, "
                f"got {self.row_count} rows and {len(self.columns)} columns. "
                f"Use to_polars() or to_dicts() for multi-value results."
            )
        return self.rows[0][0]

    def first(self) -> dict | None:
        """
        Get first row as dict, or None if empty.

        Example:
            >>> user = conn.query("MATCH (u:User {id: $id}) RETURN u.*", {"id": 123}).first()
            >>> if user:
            ...     print(user["name"])
        """
        if self.row_count == 0:
            return None
        return dict(zip(self.columns, self.rows[0]))

    # -------------------------------------------------------------------------
    # Graph Conversion
    # -------------------------------------------------------------------------

    def to_networkx(self, directed: bool = True) -> "nx.Graph":
        """
        Convert to NetworkX graph.

        Works when query returns nodes and relationships (RETURN n, r, m or RETURN *).
        Nodes are identified by _id, properties become node/edge attributes.

        Args:
            directed: If True, return DiGraph; else Graph

        Returns:
            NetworkX Graph or DiGraph

        Example:
            >>> result = conn.query("MATCH (a)-[r]->(b) RETURN a, r, b LIMIT 100")
            >>> G = result.to_networkx()
            >>> nx.pagerank(G)
        """
        import networkx as nx
        G = nx.DiGraph() if directed else nx.Graph()

        for row in self.rows:
            row_dict = dict(zip(self.columns, row))
            for col, val in row_dict.items():
                if isinstance(val, dict):
                    if "_label" in val:  # Node
                        node_id = val.get("_id", f"{val['_label']}_{id(val)}")
                        props = {k: v for k, v in val.items() if not k.startswith("_")}
                        props["_label"] = val.get("_label")
                        G.add_node(node_id, **props)
                    elif "_type" in val:  # Relationship
                        src = val.get("_start")
                        dst = val.get("_end")
                        props = {k: v for k, v in val.items() if not k.startswith("_")}
                        props["_type"] = val.get("_type")
                        if src and dst:
                            G.add_edge(src, dst, **props)
        return G

    # -------------------------------------------------------------------------
    # Export Methods
    # -------------------------------------------------------------------------

    def to_csv(self, path: str, **kwargs) -> None:
        """
        Export to CSV file.

        Args:
            path: Output file path
            **kwargs: Passed to polars write_csv()

        Example:
            >>> result.to_csv("output.csv")
        """
        self.to_polars().write_csv(path, **kwargs)

    def to_parquet(self, path: str, **kwargs) -> None:
        """
        Export to Parquet file.

        Args:
            path: Output file path
            **kwargs: Passed to polars write_parquet()

        Example:
            >>> result.to_parquet("output.parquet", compression="snappy")
        """
        self.to_polars().write_parquet(path, **kwargs)

    # -------------------------------------------------------------------------
    # Smart Visualization (Analyst-Friendly UX)
    # -------------------------------------------------------------------------

    def show(
        self,
        as_type: str | None = None,
        **kwargs,
    ):
        """
        Smart visualization - automatically picks the best display format.

        This is the PRIMARY method analysts should use. It automatically:
        - Detects if data contains graphs (nodes/relationships) or tabular data
        - Chooses appropriate visualization based on data size
        - Uses sensible defaults that work well in Jupyter

        Args:
            as_type: Force a specific visualization type:
                - None (default): Auto-detect best visualization
                - "table": Interactive DataTable (sortable, filterable)
                - "graph": Network graph visualization
                - "chart": Bar/line chart (for aggregations)
                - "json": Pretty-printed JSON
            **kwargs: Passed to underlying visualization

        Examples:
            >>> # Just show it - SDK picks the best visualization
            >>> result.show()

            >>> # Force table view for graph data
            >>> result.show("table")

            >>> # Force graph view with options
            >>> result.show("graph", layout="dagre", node_color="community")

        Size-Based Auto-Selection:
            - Tabular data, ≤100 rows: Simple HTML table
            - Tabular data, >100 rows: Interactive DataTable (itables)
            - Graph data, ≤5K nodes: PyVis interactive graph
            - Graph data, 5K-50K nodes: ipycytoscape
            - Graph data, >50K nodes: Graphistry (if available)
        """
        if as_type:
            return self._show_as(as_type, **kwargs)

        # Auto-detect best visualization
        if self._is_graph_data():
            return self._show_graph_auto(**kwargs)
        else:
            return self._show_table_auto(**kwargs)

    def _is_graph_data(self) -> bool:
        """Detect if result contains nodes/relationships."""
        if not self.rows:
            return False
        # Check first few rows for graph structures
        for row in self.rows[:5]:
            for val in row:
                if isinstance(val, dict):
                    if "_label" in val or "_type" in val:
                        return True
        return False

    def _show_as(self, as_type: str, **kwargs):
        """Show as specific visualization type."""
        if as_type == "table":
            return self._show_table_auto(**kwargs)
        elif as_type == "graph":
            return self._show_graph_auto(**kwargs)
        elif as_type == "chart":
            return self.to_altair(**kwargs)
        elif as_type == "json":
            from IPython.display import JSON
            return JSON(self.to_dicts())
        else:
            raise ValueError(f"Unknown visualization type: {as_type}")

    def _show_table_auto(self, **kwargs):
        """Auto-select best table visualization."""
        if self.row_count <= 100:
            # Simple HTML table is fine
            from IPython.display import HTML
            return HTML(self._repr_html_())
        else:
            # Use itables for large results
            return self.to_itables(**kwargs)

    def _show_graph_auto(self, **kwargs):
        """Auto-select best graph visualization based on size."""
        G = self.to_networkx()
        node_count = G.number_of_nodes()

        if node_count <= 5000:
            # PyVis for small-medium graphs
            return self.to_pyvis(**kwargs)
        elif node_count <= 50000:
            # ipycytoscape for larger graphs
            return self.to_cytoscape(**kwargs)
        else:
            # Graphistry for massive graphs
            try:
                return self.to_graphistry(**kwargs)
            except ImportError:
                # Fall back to cytoscape with warning
                print(f"⚠️ Large graph ({node_count:,} nodes). Install graphistry for better performance.")
                return self.to_cytoscape(**kwargs)

    # -------------------------------------------------------------------------
    # Specific Visualization Methods (for advanced users)
    # -------------------------------------------------------------------------

    def to_itables(self, **kwargs) -> None:
        """
        Display as interactive DataTable using itables.

        Provides sorting, filtering, search, and pagination for large results.
        Requires: pip install itables

        Args:
            **kwargs: Passed to itables.show()
                - lengthMenu: Page size options [10, 25, 50, 100]
                - classes: CSS classes ("display", "compact", "cell-border")
                - scrollX: Enable horizontal scroll
                - columnDefs: Column-specific settings

        Example:
            >>> result = conn.query("MATCH (n:Customer) RETURN n.* LIMIT 10000")
            >>> result.to_itables(lengthMenu=[25, 50, 100], scrollX=True)
        """
        try:
            from itables import show
            df = self.to_pandas()
            show(df, **kwargs)
        except ImportError:
            raise ImportError(
                "itables not installed. Install with: pip install itables"
            )

    def to_cytoscape(
        self,
        layout: str = "cose",
        directed: bool = True,
        node_color_property: str | None = None,
        node_size_property: str | None = None,
        edge_width_property: str | None = None,
        **kwargs,
    ):
        """
        Display as interactive graph using ipycytoscape.

        Better for complex graphs than PyVis - supports advanced layouts,
        styling based on properties, and larger graphs (~50K nodes).
        Requires: pip install ipycytoscape

        Args:
            layout: Layout algorithm - "cose", "dagre", "klay", "cola", "spread", etc.
            directed: Show directed edges
            node_color_property: Node property for color mapping
            node_size_property: Node property for size mapping
            edge_width_property: Edge property for width mapping
            **kwargs: Additional ipycytoscape options

        Returns:
            ipycytoscape.CytoscapeWidget for display in Jupyter

        Example:
            >>> result = conn.query("MATCH (a)-[r]->(b) RETURN a, r, b LIMIT 1000")
            >>> result.to_cytoscape(
            ...     layout="dagre",
            ...     node_color_property="community",
            ...     node_size_property="pagerank"
            ... )
        """
        try:
            import ipycytoscape
        except ImportError:
            raise ImportError(
                "ipycytoscape not installed. Install with: pip install ipycytoscape"
            )

        G = self.to_networkx(directed=directed)

        # Build cytoscape elements
        elements = []

        # Add nodes
        for node_id, attrs in G.nodes(data=True):
            node_data = {"id": str(node_id), "label": attrs.get("_label", "")}
            node_data.update({k: v for k, v in attrs.items() if not k.startswith("_")})
            elements.append({"data": node_data, "group": "nodes"})

        # Add edges
        for src, dst, attrs in G.edges(data=True):
            edge_data = {
                "source": str(src),
                "target": str(dst),
                "label": attrs.get("_type", ""),
            }
            edge_data.update({k: v for k, v in attrs.items() if not k.startswith("_")})
            elements.append({"data": edge_data, "group": "edges"})

        # Create widget
        cyto = ipycytoscape.CytoscapeWidget()
        cyto.graph.add_graph_from_json(elements)

        # Apply layout
        cyto.set_layout(name=layout)

        # Apply styling based on properties
        style = self._build_cytoscape_style(
            node_color_property, node_size_property, edge_width_property
        )
        cyto.set_style(style)

        return cyto

    def _build_cytoscape_style(
        self,
        node_color_prop: str | None,
        node_size_prop: str | None,
        edge_width_prop: str | None,
    ) -> list[dict]:
        """Build Cytoscape.js style based on property mappings."""
        style = [
            {
                "selector": "node",
                "style": {
                    "label": "data(label)",
                    "background-color": "#1565C0",
                    "color": "#fff",
                    "text-valign": "center",
                    "text-halign": "center",
                    "font-size": "10px",
                },
            },
            {
                "selector": "edge",
                "style": {
                    "label": "data(label)",
                    "curve-style": "bezier",
                    "target-arrow-shape": "triangle",
                    "line-color": "#999",
                    "target-arrow-color": "#999",
                    "font-size": "8px",
                },
            },
        ]

        if node_color_prop:
            style[0]["style"]["background-color"] = f"mapData({node_color_prop}, 0, 1, #1565C0, #C62828)"

        if node_size_prop:
            style[0]["style"]["width"] = f"mapData({node_size_prop}, 0, 1, 20, 60)"
            style[0]["style"]["height"] = f"mapData({node_size_prop}, 0, 1, 20, 60)"

        if edge_width_prop:
            style[1]["style"]["width"] = f"mapData({edge_width_prop}, 0, 1, 1, 5)"

        return style

    def to_graphistry(
        self,
        node_label: str = "_label",
        edge_label: str = "_type",
        point_color: str | None = None,
        point_size: str | None = None,
    ):
        """
        Display as GPU-accelerated visualization using Graphistry.

        For very large graphs (millions of nodes/edges). Requires Graphistry account.
        Requires: pip install graphistry

        Args:
            node_label: Node property for labels
            edge_label: Edge property for labels
            point_color: Node property for color
            point_size: Node property for size

        Returns:
            Graphistry visualization (renders in notebook or returns URL)

        Example:
            >>> import graphistry
            >>> graphistry.register(api=3, username='...', password='...')
            >>> result = conn.query("MATCH (a)-[r]->(b) RETURN a, r, b LIMIT 100000")
            >>> result.to_graphistry(point_color="community")
        """
        try:
            import graphistry
        except ImportError:
            raise ImportError(
                "graphistry not installed. Install with: pip install graphistry"
            )

        G = self.to_networkx()

        g = graphistry.from_networkx(G)

        if point_color:
            g = g.encode_point_color(point_color)
        if point_size:
            g = g.encode_point_size(point_size)

        return g.plot()

    def to_altair(
        self,
        x: str | None = None,
        y: str | None = None,
        color: str | None = None,
        chart_type: str = "bar",
    ):
        """
        Create quick exploratory chart using Altair.

        Requires: pip install altair

        Args:
            x: Column for x-axis
            y: Column for y-axis (or aggregation like "count()")
            color: Column for color encoding
            chart_type: "bar", "line", "scatter", "area"

        Returns:
            altair.Chart

        Example:
            >>> result = conn.query("MATCH (n:Customer) RETURN n.city, count(*) as cnt")
            >>> result.to_altair(x="n.city", y="cnt", chart_type="bar")
        """
        try:
            import altair as alt
        except ImportError:
            raise ImportError(
                "altair not installed. Install with: pip install altair"
            )

        df = self.to_pandas()

        if x is None:
            x = self.columns[0]
        if y is None:
            y = self.columns[1] if len(self.columns) > 1 else "count()"

        chart_map = {
            "bar": alt.Chart(df).mark_bar(),
            "line": alt.Chart(df).mark_line(),
            "scatter": alt.Chart(df).mark_circle(),
            "area": alt.Chart(df).mark_area(),
        }

        chart = chart_map.get(chart_type, chart_map["bar"])
        chart = chart.encode(x=x, y=y)

        if color:
            chart = chart.encode(color=color)

        return chart.interactive()

    # -------------------------------------------------------------------------
    # Iteration & Indexing
    # -------------------------------------------------------------------------

    def __iter__(self):
        """Iterate over rows as dicts."""
        for row in self.rows:
            yield dict(zip(self.columns, row))

    def __len__(self) -> int:
        """Return row count."""
        return self.row_count

    def __getitem__(self, index: int) -> dict:
        """Get row by index as dict."""
        return dict(zip(self.columns, self.rows[index]))

    def __bool__(self) -> bool:
        """True if result has rows."""
        return self.row_count > 0

    # -------------------------------------------------------------------------
    # Jupyter Display
    # -------------------------------------------------------------------------

    def _repr_html_(self) -> str:
        """Rich HTML table display for Jupyter notebooks."""
        if not self.rows:
            return "<p style='color: #666;'>No results</p>"

        # Build header
        header = "".join(
            f"<th style='padding: 8px; border: 1px solid #ddd; background: #f5f5f5;'>{col}</th>"
            for col in self.columns
        )

        # Build rows (limit to 100 for display)
        rows_html = ""
        display_rows = self.rows[:100]
        for i, row in enumerate(display_rows):
            bg = "#fff" if i % 2 == 0 else "#fafafa"
            cells = "".join(
                f"<td style='padding: 8px; border: 1px solid #ddd; background: {bg};'>{self._format_cell(cell)}</td>"
                for cell in row
            )
            rows_html += f"<tr>{cells}</tr>"

        truncated = ""
        if self.row_count > 100:
            truncated = f"<p style='color: #666; font-size: 0.9em;'><em>Showing 100 of {self.row_count:,} rows</em></p>"

        return f"""
        <div style="overflow-x: auto;">
            <table style="border-collapse: collapse; font-family: monospace; font-size: 13px;">
                <thead><tr>{header}</tr></thead>
                <tbody>{rows_html}</tbody>
            </table>
        </div>
        {truncated}
        <p style="color: #888; font-size: 0.85em;">{self.row_count:,} rows in {self.execution_time_ms}ms</p>
        """

    def _format_cell(self, value) -> str:
        """Format cell value for HTML display."""
        if value is None:
            return "<span style='color: #999;'>null</span>"
        if isinstance(value, dict):
            # Node or relationship - show abbreviated
            if "_label" in value:
                return f"<span style='color: #1565C0;'>:{value['_label']}</span>"
            if "_type" in value:
                return f"<span style='color: #2E7D32;'>[:{value['_type']}]</span>"
            return "{...}"
        if isinstance(value, list):
            return f"[{len(value)} items]"
        if isinstance(value, str) and len(value) > 50:
            return value[:47] + "..."
        return str(value)


@dataclass
class Schema:
    """Graph schema with node and relationship tables."""
    nodes: dict[str, dict]  # {label: {primary_key, properties}}
    relationships: dict[str, dict]  # {type: {from, to, properties}}

    @classmethod
    def from_dict(cls, data: dict) -> "Schema":
        return cls(
            nodes=data.get("nodes", {}),
            relationships=data.get("relationships", {}),
        )

    def _repr_html_(self) -> str:
        """Rich HTML display for Jupyter notebooks."""
        nodes_html = ""
        for label, info in self.nodes.items():
            props = ", ".join(f"{k}: {v}" for k, v in info.get("properties", {}).items())
            nodes_html += f"<li><strong>{label}</strong> (PK: {info.get('primary_key')})<br/><small>{props}</small></li>"

        rels_html = ""
        for rel_type, info in self.relationships.items():
            props = ", ".join(f"{k}: {v}" for k, v in info.get("properties", {}).items())
            rels_html += f"<li><strong>{rel_type}</strong>: {info.get('from')} → {info.get('to')}<br/><small>{props}</small></li>"

        return f"""
        <div style="border: 1px solid #ddd; padding: 15px; border-radius: 5px;">
            <h4>Graph Schema</h4>
            <h5>Node Tables ({len(self.nodes)})</h5>
            <ul>{nodes_html}</ul>
            <h5>Relationship Tables ({len(self.relationships)})</h5>
            <ul>{rels_html}</ul>
        </div>
        """


@dataclass
class LockStatus:
    """Instance lock status."""
    locked: bool
    holder_id: str | None = None
    holder_name: str | None = None
    algorithm: str | None = None
    acquired_at: datetime | None = None
    duration_seconds: int | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "LockStatus":
        return cls(
            locked=data["locked"],
            holder_id=data.get("holder_id"),
            holder_name=data.get("holder_name"),
            algorithm=data.get("algorithm"),
            acquired_at=datetime.fromisoformat(data["acquired_at"].replace("Z", "+00:00")) if data.get("acquired_at") else None,
            duration_seconds=data.get("duration_seconds"),
        )


@dataclass
class AlgorithmExecution:
    """Algorithm execution status and result."""
    execution_id: str
    algorithm: str
    status: str  # running, completed, failed
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: int | None = None
    result: dict | None = None
    error: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "AlgorithmExecution":
        return cls(
            execution_id=data["execution_id"],
            algorithm=data["algorithm"],
            status=data["status"],
            started_at=datetime.fromisoformat(data["started_at"].replace("Z", "+00:00")),
            completed_at=datetime.fromisoformat(data["completed_at"].replace("Z", "+00:00")) if data.get("completed_at") else None,
            duration_seconds=data.get("duration_seconds"),
            result=data.get("result"),
            error=data.get("error"),
        )


@dataclass
class SnapshotProgress:
    """Snapshot export progress."""
    id: int
    status: str
    phase: str
    started_at: datetime | None
    completed_at: datetime | None = None
    duration_seconds: int | None = None
    steps: list[dict] | None = None
    completed_steps: int = 0
    total_steps: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "SnapshotProgress":
        return cls(
            id=data["id"],
            status=data["status"],
            phase=data["phase"],
            started_at=datetime.fromisoformat(data["started_at"].replace("Z", "+00:00")) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"].replace("Z", "+00:00")) if data.get("completed_at") else None,
            duration_seconds=data.get("duration_seconds"),
            steps=data.get("steps"),
            completed_steps=data.get("completed_steps", 0),
            total_steps=data.get("total_steps", 0),
        )


@dataclass
class InstanceProgress:
    """Instance startup progress."""
    id: int
    status: str
    phase: str
    started_at: datetime | None
    ready_at: datetime | None = None
    startup_duration_seconds: int | None = None
    steps: list[dict] | None = None
    completed_steps: int = 0
    total_steps: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "InstanceProgress":
        return cls(
            id=data["id"],
            status=data["status"],
            phase=data["phase"],
            started_at=datetime.fromisoformat(data["started_at"].replace("Z", "+00:00")) if data.get("started_at") else None,
            ready_at=datetime.fromisoformat(data["ready_at"].replace("Z", "+00:00")) if data.get("ready_at") else None,
            startup_duration_seconds=data.get("startup_duration_seconds"),
            steps=data.get("steps"),
            completed_steps=data.get("completed_steps", 0),
            total_steps=data.get("total_steps", 0),
        )
```

---

## Ops Models

Models for operations/admin functionality and health monitoring.

```python
# models/ops.py
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ResourceLifecycleConfig:
    """
    Lifecycle configuration for a specific resource type (mapping, snapshot, instance).

    All duration values use ISO 8601 duration format (e.g., "P30D", "PT24H").
    """
    default_ttl: str | None = None
    default_inactivity: str | None = None
    max_ttl: str | None = None

    @classmethod
    def from_api_response(cls, data: dict) -> "ResourceLifecycleConfig":
        return cls(
            default_ttl=data.get("default_ttl"),
            default_inactivity=data.get("default_inactivity"),
            max_ttl=data.get("max_ttl"),
        )


@dataclass
class LifecycleConfig:
    """
    Complete lifecycle configuration for all resource types.

    Contains settings for mappings, snapshots, and instances with
    their respective TTL and inactivity timeout defaults.
    """
    mapping: ResourceLifecycleConfig
    snapshot: ResourceLifecycleConfig
    instance: ResourceLifecycleConfig

    @classmethod
    def from_api_response(cls, data: dict) -> "LifecycleConfig":
        return cls(
            mapping=ResourceLifecycleConfig.from_api_response(data.get("mapping", {})),
            snapshot=ResourceLifecycleConfig.from_api_response(data.get("snapshot", {})),
            instance=ResourceLifecycleConfig.from_api_response(data.get("instance", {})),
        )


@dataclass
class ConcurrencyConfig:
    """
    Concurrency limits for instances.

    Controls how many instances a single analyst can run and
    the total cluster-wide limit.
    """
    per_analyst: int
    cluster_total: int
    updated_at: datetime | None = None

    @classmethod
    def from_api_response(cls, data: dict) -> "ConcurrencyConfig":
        updated_at = None
        if data.get("updated_at"):
            updated_at = datetime.fromisoformat(
                data["updated_at"].replace("Z", "+00:00")
            )
        return cls(
            per_analyst=data["per_analyst"],
            cluster_total=data["cluster_total"],
            updated_at=updated_at,
        )


@dataclass
class MaintenanceMode:
    """
    Maintenance mode status.

    When enabled, new resource creation may be blocked and
    a message is displayed to users.
    """
    enabled: bool
    message: str = ""
    updated_at: datetime | None = None
    updated_by: str | None = None

    @classmethod
    def from_api_response(cls, data: dict) -> "MaintenanceMode":
        updated_at = None
        if data.get("updated_at"):
            updated_at = datetime.fromisoformat(
                data["updated_at"].replace("Z", "+00:00")
            )
        return cls(
            enabled=data["enabled"],
            message=data.get("message", ""),
            updated_at=updated_at,
            updated_by=data.get("updated_by"),
        )


@dataclass
class ExportConfig:
    """
    Export job configuration.

    Controls maximum duration allowed for snapshot export jobs.
    """
    max_duration_seconds: int
    updated_at: datetime | None = None
    updated_by: str | None = None

    @classmethod
    def from_api_response(cls, data: dict) -> "ExportConfig":
        updated_at = None
        if data.get("updated_at"):
            updated_at = datetime.fromisoformat(
                data["updated_at"].replace("Z", "+00:00")
            )
        return cls(
            max_duration_seconds=data["max_duration_seconds"],
            updated_at=updated_at,
            updated_by=data.get("updated_by"),
        )


@dataclass
class ComponentHealth:
    """
    Health status of a single cluster component.

    Components include database, pubsub, kubernetes, and starburst.
    """
    status: str  # "healthy", "unhealthy", "degraded"
    latency_ms: int | None = None
    error: str | None = None

    @classmethod
    def from_api_response(cls, data: dict) -> "ComponentHealth":
        return cls(
            status=data["status"],
            latency_ms=data.get("latency_ms"),
            error=data.get("error"),
        )


@dataclass
class ClusterHealth:
    """
    Overall cluster health with component breakdown.

    Aggregates health status from all infrastructure components.
    """
    status: str  # "healthy", "degraded", "unhealthy"
    components: dict[str, ComponentHealth]
    checked_at: datetime

    @classmethod
    def from_api_response(cls, data: dict) -> "ClusterHealth":
        components = {}
        for name, comp_data in data.get("components", {}).items():
            components[name] = ComponentHealth.from_api_response(comp_data)

        return cls(
            status=data["status"],
            components=components,
            checked_at=datetime.fromisoformat(
                data["checked_at"].replace("Z", "+00:00")
            ),
        )


@dataclass
class OwnerInstanceCount:
    """Instance count for a specific owner."""
    owner_username: str
    count: int

    @classmethod
    def from_api_response(cls, data: dict) -> "OwnerInstanceCount":
        return cls(
            owner_username=data["owner_username"],
            count=data["count"],
        )


@dataclass
class InstanceLimits:
    """Instance limits and current usage."""
    per_analyst: int
    cluster_total: int
    cluster_used: int
    cluster_available: int

    @classmethod
    def from_api_response(cls, data: dict) -> "InstanceLimits":
        return cls(
            per_analyst=data["per_analyst"],
            cluster_total=data["cluster_total"],
            cluster_used=data["cluster_used"],
            cluster_available=data["cluster_available"],
        )


@dataclass
class ClusterInstances:
    """
    Cluster-wide instance summary.

    Provides aggregate counts by status and owner, plus limit info.
    """
    total: int
    by_status: dict[str, int]
    by_owner: list[OwnerInstanceCount]
    limits: InstanceLimits

    @classmethod
    def from_api_response(cls, data: dict) -> "ClusterInstances":
        by_owner = [
            OwnerInstanceCount.from_api_response(o)
            for o in data.get("by_owner", [])
        ]
        return cls(
            total=data["total"],
            by_status=data.get("by_status", {}),
            by_owner=by_owner,
            limits=InstanceLimits.from_api_response(data["limits"]),
        )


@dataclass
class HealthStatus:
    """
    Basic health check response.

    Used by /health and /ready endpoints.
    """
    status: str  # "ok", "unhealthy"
    version: str | None = None
    database: str | None = None  # Only present in /ready response

    @classmethod
    def from_api_response(cls, data: dict) -> "HealthStatus":
        return cls(
            status=data["status"],
            version=data.get("version"),
            database=data.get("database"),
        )
```

---

## Favorite Resource

```python
# resources/favorites.py
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Favorite:
    """User favorite/bookmark."""
    resource_type: str  # mapping, snapshot, instance
    resource_id: int
    resource_name: str
    resource_owner: str
    created_at: datetime
    resource_exists: bool

    @classmethod
    def from_dict(cls, data: dict) -> "Favorite":
        return cls(
            resource_type=data["resource_type"],
            resource_id=data["resource_id"],
            resource_name=data["resource_name"],
            resource_owner=data["resource_owner"],
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            resource_exists=data.get("resource_exists", True),
        )


class FavoriteResource:
    """Manage user favorites/bookmarks."""

    def __init__(self, http: HTTPClient):
        self._http = http

    def list(self, resource_type: str | None = None) -> list[Favorite]:
        """
        List current user's favorites.

        Args:
            resource_type: Filter by type (mapping, snapshot, instance)

        Returns:
            List of Favorite objects
        """
        params = {}
        if resource_type:
            params["resource_type"] = resource_type

        response = self._http.get("/api/favorites", params=params)
        return [Favorite.from_dict(f) for f in response["data"]]

    def add(self, resource_type: str, resource_id: int) -> Favorite:
        """
        Add a resource to favorites.

        Args:
            resource_type: Type of resource (mapping, snapshot, instance)
            resource_id: ID of the resource

        Returns:
            Created Favorite object

        Raises:
            ConflictError: If already favorited
            NotFoundError: If resource doesn't exist
        """
        response = self._http.post(
            "/api/favorites",
            json={"resource_type": resource_type, "resource_id": resource_id},
        )
        return Favorite.from_dict(response["data"])

    def remove(self, resource_type: str, resource_id: int) -> None:
        """
        Remove a resource from favorites.

        Args:
            resource_type: Type of resource
            resource_id: ID of the resource

        Raises:
            NotFoundError: If favorite doesn't exist
        """
        self._http.delete(f"/api/favorites/{resource_type}/{resource_id}")
```

---

## Additional Snapshot Methods

Add these methods to `SnapshotResource`:

```python
# Additional methods for resources/snapshots.py

    def retry(self, snapshot_id: int) -> Snapshot:
        """
        Retry a failed snapshot export.

        Args:
            snapshot_id: ID of the failed snapshot

        Returns:
            Snapshot object with status='pending'

        Raises:
            InvalidStateError: If snapshot is not in 'failed' status
        """
        response = self._http.post(f"/api/snapshots/{snapshot_id}/retry")
        return Snapshot.from_dict(response["data"])

    def get_progress(self, snapshot_id: int) -> SnapshotProgress:
        """
        Get detailed export progress for a snapshot.

        Args:
            snapshot_id: Snapshot ID

        Returns:
            SnapshotProgress with phase, steps, and completion info
        """
        response = self._http.get(f"/api/snapshots/{snapshot_id}/progress")
        return SnapshotProgress.from_dict(response["data"])

    def create_and_wait(
        self,
        mapping_id: int,
        name: str,
        description: str | None = None,
        version: int | None = None,
        ttl: str | None = None,
        inactivity_timeout: str | None = None,
        timeout: int = 600,
        poll_interval: int = 5,
        on_progress: callable | None = None,
    ) -> Snapshot:
        """
        Create a snapshot and wait for it to become ready.

        Args:
            mapping_id: Source mapping ID
            name: Display name
            description: Optional description
            version: Mapping version (defaults to current)
            ttl: Time-to-live (ISO 8601 duration)
            inactivity_timeout: Inactivity timeout (ISO 8601 duration)
            timeout: Maximum wait time in seconds
            poll_interval: Time between status checks
            on_progress: Optional callback(phase, completed, total)

        Returns:
            Snapshot object with status='ready'

        Example:
            >>> snapshot = client.snapshots.create_and_wait(
            ...     mapping_id=1,
            ...     name="Quick Snapshot",
            ...     on_progress=lambda p, c, t: print(f"{p}: {c}/{t}")
            ... )
        """
        snapshot = self.create(
            mapping_id=mapping_id,
            name=name,
            description=description,
            version=version,
            ttl=ttl,
            inactivity_timeout=inactivity_timeout,
        )

        start = time.time()

        while time.time() - start < timeout:
            progress = self.get_progress(snapshot.id)

            if on_progress:
                on_progress(progress.phase, progress.completed_steps, progress.total_steps)

            if progress.status == "ready":
                return self.get(snapshot.id)

            if progress.status == "failed":
                snapshot = self.get(snapshot.id)
                raise SnapshotFailedError(
                    f"Snapshot {snapshot.id} failed: {snapshot.error_message}"
                )

            time.sleep(poll_interval)

        raise SDKTimeoutError(
            f"Snapshot {snapshot.id} did not become ready within {timeout}s"
        )
```

---

## Additional Instance Methods

Add these methods to `InstanceResource`:

```python
# Additional methods for resources/instances.py

    def update(
        self,
        instance_id: int,
        name: str | None = None,
        description: str | None = None,
    ) -> Instance:
        """
        Update instance metadata.

        Args:
            instance_id: Instance ID
            name: New name (optional)
            description: New description (optional)

        Returns:
            Updated Instance object
        """
        body = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description

        response = self._http.put(f"/api/instances/{instance_id}", json=body)
        return Instance.from_dict(response["data"])

    def set_lifecycle(
        self,
        instance_id: int,
        ttl: str | None = None,
        inactivity_timeout: str | None = None,
    ) -> Instance:
        """
        Set lifecycle parameters for an instance.

        Args:
            instance_id: Instance ID
            ttl: Time-to-live (ISO 8601 duration) or None to clear
            inactivity_timeout: Inactivity timeout (ISO 8601 duration) or None to clear

        Returns:
            Updated Instance object
        """
        body = {}
        if ttl is not None:
            body["ttl"] = ttl
        if inactivity_timeout is not None:
            body["inactivity_timeout"] = inactivity_timeout

        response = self._http.put(f"/api/instances/{instance_id}/lifecycle", json=body)
        return Instance.from_dict(response["data"])

    def get_progress(self, instance_id: int) -> InstanceProgress:
        """
        Get detailed startup progress for an instance.

        Args:
            instance_id: Instance ID

        Returns:
            InstanceProgress with phase, steps, and completion info
        """
        response = self._http.get(f"/api/instances/{instance_id}/progress")
        return InstanceProgress.from_dict(response["data"])

    def create_and_wait(
        self,
        snapshot_id: int,
        name: str,
        description: str | None = None,
        ttl: str | None = None,
        inactivity_timeout: str | None = None,
        timeout: int = 300,
        poll_interval: int = 5,
        on_progress: callable | None = None,
    ) -> Instance:
        """
        Create an instance and wait for it to become running.

        Args:
            snapshot_id: Source snapshot ID
            name: Display name
            description: Optional description
            ttl: Time-to-live (ISO 8601 duration)
            inactivity_timeout: Inactivity timeout (ISO 8601 duration)
            timeout: Maximum wait time in seconds
            poll_interval: Time between status checks
            on_progress: Optional callback(phase, completed, total)

        Returns:
            Instance object with status='running'

        Example:
            >>> instance = client.instances.create_and_wait(
            ...     snapshot_id=1,
            ...     name="Quick Analysis"
            ... )
            >>> conn = client.instances.connect(instance.id)
        """
        instance = self.create(
            snapshot_id=snapshot_id,
            name=name,
            description=description,
            ttl=ttl,
            inactivity_timeout=inactivity_timeout,
        )

        start = time.time()

        while time.time() - start < timeout:
            progress = self.get_progress(instance.id)

            if on_progress:
                on_progress(progress.phase, progress.completed_steps, progress.total_steps)

            if progress.status == "running":
                return self.get(instance.id)

            if progress.status == "failed":
                instance = self.get(instance.id)
                raise InstanceFailedError(
                    f"Instance {instance.id} failed: {instance.error_message}"
                )

            time.sleep(poll_interval)

        raise TimeoutError(
            f"Instance {instance.id} did not start within {timeout}s"
        )

    def delete(self, instance_id: int) -> None:
        """
        Delete an instance (immediate removal from database).

        For graceful shutdown, use terminate() instead.

        Args:
            instance_id: Instance ID to delete
        """
        self._http.delete(f"/api/instances/{instance_id}")

    def extend_ttl(
        self,
        instance_id: int,
        hours: int = 24,
    ) -> Instance:
        """
        Extend instance TTL by specified hours from current expiry.

        Convenience method matching UX "Extend TTL" button behavior.
        Calculates new expiry as current_expiry + hours.

        Args:
            instance_id: Instance ID
            hours: Hours to add to current TTL (default: 24)

        Returns:
            Updated Instance object

        Raises:
            ValidationError: If extension would exceed maximum TTL (7 days from creation)

        Example:
            >>> instance = client.instances.extend_ttl(123)  # +24 hours
            >>> instance = client.instances.extend_ttl(123, hours=48)  # +48 hours
        """
        from datetime import datetime, timedelta, timezone

        instance = self.get(instance_id)

        if instance.expires_at is None:
            # No current TTL - set absolute expiry
            new_expiry = datetime.now(timezone.utc) + timedelta(hours=hours)
        else:
            # Extend from current expiry
            new_expiry = instance.expires_at + timedelta(hours=hours)

        # Calculate TTL duration from now
        ttl_seconds = int((new_expiry - datetime.now(timezone.utc)).total_seconds())
        ttl_hours = ttl_seconds // 3600

        return self.set_lifecycle(
            instance_id=instance_id,
            ttl=f"PT{ttl_hours}H",
        )
```

---

## Additional Mapping Methods

Add these methods to `MappingResource`:

```python
# Additional methods for resources/mappings.py

    def get_tree(
        self,
        mapping_id: int,
        include_instances: bool = True,
        status: str | None = None,
    ) -> dict:
        """
        Get full resource hierarchy for a mapping.

        Returns versions → snapshots → instances tree structure.

        Args:
            mapping_id: Mapping ID
            include_instances: Include instance details
            status: Filter snapshots by status

        Returns:
            Tree structure with versions, snapshots, and instances
        """
        params = {"include_instances": include_instances}
        if status:
            params["status"] = status

        response = self._http.get(f"/api/mappings/{mapping_id}/tree", params=params)
        return response["data"]

    def diff_versions(
        self,
        mapping_id: int,
        from_version: int,
        to_version: int,
    ) -> dict:
        """
        Compare two mapping versions.

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
```

