"""API schemas for Starburst schema metadata endpoints.

Response models for schema browsing APIs:
- Catalogs, schemas, tables, columns
- Search results
- Cache statistics

All structures used by both control-plane API and SDK client.
"""

from pydantic import BaseModel, Field


class CatalogResponse(BaseModel):
    """Catalog metadata response."""

    catalog_name: str = Field(description="Catalog name")
    schema_count: int = Field(description="Number of schemas in catalog")
    cached_at: str | None = Field(
        default=None, description="ISO 8601 timestamp of when metadata was cached"
    )


class SchemaResponse(BaseModel):
    """Schema metadata response."""

    catalog_name: str = Field(description="Catalog name")
    schema_name: str = Field(description="Schema name")
    table_count: int = Field(description="Number of tables in schema")
    cached_at: str | None = Field(
        default=None, description="ISO 8601 timestamp of when metadata was cached"
    )


class TableResponse(BaseModel):
    """Table metadata response."""

    catalog_name: str = Field(description="Catalog name")
    schema_name: str = Field(description="Schema name")
    table_name: str = Field(description="Table name")
    table_type: str = Field(description="Table type (BASE TABLE, VIEW, etc.)")
    column_count: int = Field(description="Number of columns in table")
    cached_at: str | None = Field(
        default=None, description="ISO 8601 timestamp of when metadata was cached"
    )


class ColumnResponse(BaseModel):
    """Column metadata response."""

    catalog_name: str = Field(description="Catalog name")
    schema_name: str = Field(description="Schema name")
    table_name: str = Field(description="Table name")
    column_name: str = Field(description="Column name")
    data_type: str = Field(description="Column data type")
    is_nullable: bool = Field(description="Whether column accepts NULL values")
    ordinal_position: int = Field(description="Column position in table (1-indexed)")
    column_default: str | None = Field(default=None, description="Default value expression")
    cached_at: str | None = Field(
        default=None, description="ISO 8601 timestamp of when metadata was cached"
    )


class CacheStatsResponse(BaseModel):
    """Schema cache statistics response."""

    total_catalogs: int = Field(description="Total number of cached catalogs")
    total_schemas: int = Field(description="Total number of cached schemas")
    total_tables: int = Field(description="Total number of cached tables")
    total_columns: int = Field(description="Total number of cached columns")
    last_refresh: str | None = Field(
        default=None, description="ISO 8601 timestamp of last cache refresh"
    )
    index_size_bytes: int = Field(description="Estimated memory usage of search indices")
