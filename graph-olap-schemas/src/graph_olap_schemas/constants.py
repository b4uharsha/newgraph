"""
Constants and type definitions for Graph OLAP schemas.

All values derived from docs/foundation/requirements.md.
"""

from enum import StrEnum


class RyugraphType(StrEnum):
    """
    Supported Ryugraph data types for node/edge properties.

    From requirements.md: "Supported types: STRING, INT64, INT32, INT16, INT8,
    DOUBLE, FLOAT, DATE, TIMESTAMP, BOOL, BLOB, UUID, LIST, MAP, STRUCT"
    """

    STRING = "STRING"
    INT64 = "INT64"
    INT32 = "INT32"
    INT16 = "INT16"
    INT8 = "INT8"
    DOUBLE = "DOUBLE"
    FLOAT = "FLOAT"
    DATE = "DATE"
    TIMESTAMP = "TIMESTAMP"
    BOOL = "BOOL"
    BLOB = "BLOB"
    UUID = "UUID"
    LIST = "LIST"
    MAP = "MAP"
    STRUCT = "STRUCT"


class ChangeType(StrEnum):
    """
    Types of changes in version diffs (nodes/edges).

    Used by NodeDiffResponse and EdgeDiffResponse to indicate
    what kind of change occurred between mapping versions.
    """

    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"


# Validation length constraints from requirements.md
# Section: "Naming & Validation Constraints"

MAX_NODE_LABEL_LENGTH = 64
"""Node label: 1-64 chars"""

MAX_EDGE_TYPE_LENGTH = 64
"""Edge type: 1-64 chars"""

MAX_PROPERTY_NAME_LENGTH = 64
"""Property name: 1-64 chars"""

MAX_RESOURCE_NAME_LENGTH = 255
"""Mapping/Snapshot/Instance name: 1-255 chars"""

MAX_DESCRIPTION_LENGTH = 4000
"""Description: 0-4000 chars"""

MIN_NAME_LENGTH = 1
"""Minimum length for all name fields"""

MAX_PROPERTIES_PER_ENTITY = 100
"""Hard limit: Properties per node/edge (requirements.md Performance section)"""

SOFT_PROPERTIES_PER_ENTITY = 50
"""Soft limit: Properties per node/edge (requirements.md Performance section)"""


# Reserved words from requirements.md
# Section: "Reserved Names"

CYPHER_RESERVED_WORDS: frozenset[str] = frozenset(
    {
        "NODE",
        "RELATIONSHIP",
        "MATCH",
        "WHERE",
        "RETURN",
        "CREATE",
        "DELETE",
        "SET",
        "REMOVE",
        "WITH",
        "ORDER",
        "LIMIT",
        "SKIP",
        "UNION",
        "CALL",
        "YIELD",
    }
)
"""Cypher keywords that cannot be used for node labels or edge types."""

SYSTEM_PREFIXES: tuple[str, ...] = (
    "_internal_",
    "_system_",
    "_ryugraph_",
)
"""System prefixes that cannot be used for node labels or edge types."""


# Regex patterns for validation from requirements.md

NODE_LABEL_PATTERN = r"^[A-Za-z][A-Za-z0-9_]*$"
"""
Node label: ASCII letters, numbers, _ (must start with letter).
From requirements.md: "ASCII letters, numbers, `_` (start with letter)"
"""

EDGE_TYPE_PATTERN = r"^[A-Z][A-Z0-9_]*$"
"""
Edge type: ASCII uppercase letters, numbers, _.
From requirements.md: "ASCII uppercase letters, numbers, `_`"
"""

PROPERTY_NAME_PATTERN = r"^[A-Za-z][A-Za-z0-9_]*$"
"""
Property name: ASCII letters, numbers, _ (must start with letter).
From requirements.md: "ASCII letters, numbers, `_` (start with letter)"
"""

RESOURCE_NAME_PATTERN = r"^[\w\s\-_.]+$"
"""
Resource name (mapping/snapshot/instance): Unicode letters, numbers, spaces, -_.
From requirements.md: "Unicode letters, numbers, spaces, `-_.`"
"""

ISO8601_DURATION_PATTERN = r"^P(\d+D)?(T(\d+H)?(\d+M)?(\d+S)?)?$"
"""
ISO 8601 duration format for TTL and inactivity_timeout.
Examples: P7D (7 days), PT24H (24 hours), P1DT12H (1 day 12 hours)
"""

ISO8601_TIMESTAMP_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
"""
ISO 8601 timestamp format (UTC only).
Example: 2025-01-15T10:30:00Z
"""


def is_reserved_name(name: str) -> bool:
    """
    Check if a name is reserved (Cypher keyword or system prefix).

    Args:
        name: The name to check (node label or edge type)

    Returns:
        True if the name is reserved and cannot be used
    """
    upper_name = name.upper()
    if upper_name in CYPHER_RESERVED_WORDS:
        return True
    lower_name = name.lower()
    return any(lower_name.startswith(prefix) for prefix in SYSTEM_PREFIXES)
