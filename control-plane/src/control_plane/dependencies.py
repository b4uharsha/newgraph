"""FastAPI dependency injection functions."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from control_plane.cache.schema_cache import SchemaMetadataCache


def get_schema_cache(request: Request) -> SchemaMetadataCache:
    """
    Dependency to inject schema metadata cache.

    The cache is initialized during app lifespan and stored in app.state.

    Args:
        request: FastAPI request object

    Returns: SchemaMetadataCache instance

    Example:
        @router.get("/catalogs")
        async def list_catalogs(
            cache: Annotated[SchemaMetadataCache, Depends(get_schema_cache)]
        ):
            return cache.list_catalogs()
    """
    return request.app.state.schema_cache


# Type alias for convenience
SchemaCacheDep = Annotated[SchemaMetadataCache, Depends(get_schema_cache)]
