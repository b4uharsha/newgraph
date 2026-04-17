"""Schema metadata models for SDK.

These models wrap the canonical graph_olap_schemas models with SDK-specific
conveniences like from_api_response() factory methods and immutability.
"""

from __future__ import annotations

from graph_olap_schemas import (
    CacheStatsResponse,
    CatalogResponse,
    ColumnResponse,
    SchemaResponse,
    TableResponse,
)
from pydantic import ConfigDict


class Catalog(CatalogResponse):
    """Starburst catalog metadata.

    Wraps CatalogResponse from graph_olap_schemas with SDK conveniences.
    """

    model_config = ConfigDict(frozen=True)

    @classmethod
    def from_api_response(cls, data: dict) -> Catalog:
        """Create from API response."""
        return cls(**data)


class Schema(SchemaResponse):
    """Starburst schema metadata.

    Wraps SchemaResponse from graph_olap_schemas with SDK conveniences.
    """

    model_config = ConfigDict(frozen=True)

    @classmethod
    def from_api_response(cls, data: dict) -> Schema:
        """Create from API response."""
        return cls(**data)


class Table(TableResponse):
    """Starburst table metadata.

    Wraps TableResponse from graph_olap_schemas with SDK conveniences.
    """

    model_config = ConfigDict(frozen=True)

    @classmethod
    def from_api_response(cls, data: dict) -> Table:
        """Create from API response."""
        return cls(**data)


class Column(ColumnResponse):
    """Starburst column metadata.

    Wraps ColumnResponse from graph_olap_schemas with SDK conveniences.
    """

    model_config = ConfigDict(frozen=True)

    @classmethod
    def from_api_response(cls, data: dict) -> Column:
        """Create from API response."""
        return cls(**data)


class CacheStats(CacheStatsResponse):
    """Schema cache statistics.

    Wraps CacheStatsResponse from graph_olap_schemas with SDK conveniences.
    """

    model_config = ConfigDict(frozen=True)

    @classmethod
    def from_api_response(cls, data: dict) -> CacheStats:
        """Create from API response."""
        return cls(**data)
