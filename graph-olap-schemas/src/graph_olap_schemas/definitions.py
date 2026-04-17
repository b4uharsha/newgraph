"""
Mapping definition schemas for nodes and edges.

These schemas define the structure of graph mappings used across all components:
- Control Plane: API validation, database storage
- Export Worker: Job payload parsing, query generation
- Ryugraph Wrapper: Schema creation (DDL generation)
- Jupyter SDK: Client-side validation

All structures derived from docs/foundation/requirements.md.
"""

from typing import Annotated, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from graph_olap_schemas.constants import (
    CYPHER_RESERVED_WORDS,
    EDGE_TYPE_PATTERN,
    MAX_EDGE_TYPE_LENGTH,
    MAX_NODE_LABEL_LENGTH,
    MAX_PROPERTIES_PER_ENTITY,
    MAX_PROPERTY_NAME_LENGTH,
    MIN_NAME_LENGTH,
    NODE_LABEL_PATTERN,
    PROPERTY_NAME_PATTERN,
    SYSTEM_PREFIXES,
    RyugraphType,
)


class PropertyDefinition(BaseModel):
    """
    Property definition for nodes or edges.

    From requirements.md Node/Edge Definition Structure:
    ```json
    {"name": "city", "type": "STRING"}
    ```

    Properties define additional data columns beyond the primary/foreign keys.
    The order of properties in the array must match the SELECT column order.
    """

    name: Annotated[
        str,
        Field(
            min_length=MIN_NAME_LENGTH,
            max_length=MAX_PROPERTY_NAME_LENGTH,
            pattern=PROPERTY_NAME_PATTERN,
            description="Property column name (ASCII letters, numbers, underscore; starts with letter)",
            examples=["name", "city", "amount", "purchase_date"],
        ),
    ]

    type: Annotated[
        RyugraphType,
        Field(
            description="Ryugraph data type for this property",
            examples=["STRING", "INT64", "DOUBLE", "DATE"],
        ),
    ]

    @field_validator("name")
    @classmethod
    def name_not_reserved(cls, v: str) -> str:
        """Ensure property name is not a reserved word."""
        if v.upper() in CYPHER_RESERVED_WORDS:
            raise ValueError(f"Property name '{v}' is a reserved Cypher keyword")
        lower_v = v.lower()
        for prefix in SYSTEM_PREFIXES:
            if lower_v.startswith(prefix):
                raise ValueError(f"Property name '{v}' uses reserved system prefix '{prefix}'")
        return v


class PrimaryKeyDefinition(BaseModel):
    """
    Primary key definition for nodes.

    From requirements.md Node Definition Structure:
    ```json
    "primary_key": {"name": "customer_id", "type": "STRING"}
    ```

    The primary key column must be the first column in the SQL SELECT statement.
    """

    name: Annotated[
        str,
        Field(
            min_length=MIN_NAME_LENGTH,
            max_length=MAX_PROPERTY_NAME_LENGTH,
            pattern=PROPERTY_NAME_PATTERN,
            description="Primary key column name",
            examples=["customer_id", "product_id", "id"],
        ),
    ]

    type: Annotated[
        RyugraphType,
        Field(
            description="Ryugraph data type for the primary key",
            examples=["STRING", "INT64", "UUID"],
        ),
    ]


class NodeDefinition(BaseModel):
    """
    Node definition in a mapping.

    From requirements.md:
    ```json
    {
      "label": "Customer",
      "sql": "SELECT customer_id, name, city FROM analytics.customers",
      "primary_key": {"name": "customer_id", "type": "STRING"},
      "properties": [
        {"name": "name", "type": "STRING"},
        {"name": "city", "type": "STRING"}
      ]
    }
    ```

    Constraints:
    - label: 1-64 chars, ASCII letters/numbers/underscore, starts with letter
    - label: unique per mapping version
    - label: cannot be a Cypher reserved word or use system prefix
    - sql: Starburst SQL query (primary_key column must be first in SELECT)
    - properties: in SELECT order (after primary key)
    """

    label: Annotated[
        str,
        Field(
            min_length=MIN_NAME_LENGTH,
            max_length=MAX_NODE_LABEL_LENGTH,
            pattern=NODE_LABEL_PATTERN,
            description="Ryugraph node table name (ASCII letters, numbers, underscore; starts with letter)",
            examples=["Customer", "Product", "Transaction"],
        ),
    ]

    sql: Annotated[
        str,
        Field(
            min_length=1,
            description="Starburst SQL query (primary_key column must be first in SELECT)",
            examples=["SELECT customer_id, name, city FROM analytics.customers"],
        ),
    ]

    primary_key: Annotated[
        PrimaryKeyDefinition,
        Field(description="Primary key column definition"),
    ]

    properties: Annotated[
        list[PropertyDefinition],
        Field(
            default_factory=list,
            max_length=MAX_PROPERTIES_PER_ENTITY,
            description="Property columns in SELECT order (after primary key)",
        ),
    ]

    @field_validator("label")
    @classmethod
    def label_not_reserved(cls, v: str) -> str:
        """Ensure node label is not a reserved word."""
        if v.upper() in CYPHER_RESERVED_WORDS:
            raise ValueError(f"Node label '{v}' is a reserved Cypher keyword")
        lower_v = v.lower()
        for prefix in SYSTEM_PREFIXES:
            if lower_v.startswith(prefix):
                raise ValueError(f"Node label '{v}' uses reserved system prefix '{prefix}'")
        return v

    @model_validator(mode="after")
    def validate_unique_property_names(self) -> Self:
        """Ensure property names are unique within the node."""
        names = [p.name for p in self.properties]
        # Include primary key in uniqueness check
        names.append(self.primary_key.name)
        if len(names) != len(set(names)):
            raise ValueError("Property names must be unique within a node definition")
        return self


class EdgeDefinition(BaseModel):
    """
    Edge definition in a mapping.

    From requirements.md:
    ```json
    {
      "type": "PURCHASED",
      "from_node": "Customer",
      "to_node": "Product",
      "sql": "SELECT customer_id, product_id, amount, purchase_date FROM analytics.transactions",
      "from_key": "customer_id",
      "to_key": "product_id",
      "properties": [
        {"name": "amount", "type": "DOUBLE"},
        {"name": "purchase_date", "type": "DATE"}
      ]
    }
    ```

    Constraints:
    - type: 1-64 chars, ASCII uppercase letters/numbers/underscore
    - type: unique per mapping version
    - type: cannot be a Cypher reserved word or use system prefix
    - from_node/to_node: must reference existing node labels in the mapping
    - sql: Starburst SQL (from_key first, to_key second, then properties in SELECT)
    - from_key/to_key: types inferred from referenced node primary keys
    """

    type: Annotated[
        str,
        Field(
            min_length=MIN_NAME_LENGTH,
            max_length=MAX_EDGE_TYPE_LENGTH,
            pattern=EDGE_TYPE_PATTERN,
            description="Ryugraph relationship table name (ASCII uppercase letters, numbers, underscore)",
            examples=["PURCHASED", "KNOWS", "WORKS_AT"],
        ),
    ]

    from_node: Annotated[
        str,
        Field(
            min_length=MIN_NAME_LENGTH,
            max_length=MAX_NODE_LABEL_LENGTH,
            pattern=NODE_LABEL_PATTERN,
            description="Source node label (must exist in node_definitions)",
            examples=["Customer", "Person"],
        ),
    ]

    to_node: Annotated[
        str,
        Field(
            min_length=MIN_NAME_LENGTH,
            max_length=MAX_NODE_LABEL_LENGTH,
            pattern=NODE_LABEL_PATTERN,
            description="Target node label (must exist in node_definitions)",
            examples=["Product", "Company"],
        ),
    ]

    sql: Annotated[
        str,
        Field(
            min_length=1,
            description="Starburst SQL query (from_key first, to_key second, then properties)",
            examples=[
                "SELECT customer_id, product_id, amount, purchase_date FROM analytics.transactions"
            ],
        ),
    ]

    from_key: Annotated[
        str,
        Field(
            min_length=MIN_NAME_LENGTH,
            max_length=MAX_PROPERTY_NAME_LENGTH,
            pattern=PROPERTY_NAME_PATTERN,
            description="Column name for source node reference (first in SELECT)",
            examples=["customer_id", "from_id"],
        ),
    ]

    to_key: Annotated[
        str,
        Field(
            min_length=MIN_NAME_LENGTH,
            max_length=MAX_PROPERTY_NAME_LENGTH,
            pattern=PROPERTY_NAME_PATTERN,
            description="Column name for target node reference (second in SELECT)",
            examples=["product_id", "to_id"],
        ),
    ]

    properties: Annotated[
        list[PropertyDefinition],
        Field(
            default_factory=list,
            max_length=MAX_PROPERTIES_PER_ENTITY,
            description="Property columns in SELECT order (after from/to keys)",
        ),
    ]

    @field_validator("type")
    @classmethod
    def type_not_reserved(cls, v: str) -> str:
        """Ensure edge type is not a reserved word."""
        if v.upper() in CYPHER_RESERVED_WORDS:
            raise ValueError(f"Edge type '{v}' is a reserved Cypher keyword")
        lower_v = v.lower()
        for prefix in SYSTEM_PREFIXES:
            if lower_v.startswith(prefix):
                raise ValueError(f"Edge type '{v}' uses reserved system prefix '{prefix}'")
        return v

    @model_validator(mode="after")
    def validate_unique_property_names(self) -> Self:
        """Ensure property names are unique within the edge."""
        names = [p.name for p in self.properties]
        # Include from_key and to_key in uniqueness check
        names.extend([self.from_key, self.to_key])
        if len(names) != len(set(names)):
            raise ValueError("Property names must be unique within an edge definition")
        return self

    @model_validator(mode="after")
    def validate_keys_differ(self) -> Self:
        """Ensure from_key and to_key are different columns."""
        if self.from_key == self.to_key:
            raise ValueError("from_key and to_key must be different columns")
        return self
