"""Favorite resource management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from graph_olap.models.common import Favorite

if TYPE_CHECKING:
    from graph_olap.http import HTTPClient


class FavoriteResource:
    """Manage user favorites/bookmarks.

    Favorites allow users to quickly access frequently used resources.

    Example:
        >>> client = GraphOLAPClient(api_url=api_url, username="user@example.com")

        >>> # List all favorites
        >>> favorites = client.favorites.list()
        >>> for f in favorites:
        ...     print(f"{f.resource_type}: {f.resource_name}")

        >>> # Add a mapping to favorites
        >>> client.favorites.add("mapping", 1)

        >>> # Remove from favorites
        >>> client.favorites.remove("mapping", 1)
    """

    def __init__(self, http: HTTPClient):
        """Initialize favorite resource.

        Args:
            http: HTTP client for API requests
        """
        self._http = http

    def list(self, resource_type: str | None = None) -> list[Favorite]:
        """List current user's favorites.

        Args:
            resource_type: Filter by type (mapping, instance)

        Returns:
            List of Favorite objects
        """
        params: dict[str, Any] = {}
        if resource_type:
            params["resource_type"] = resource_type

        response = self._http.get("/api/favorites", params=params)
        return [Favorite.from_api_response(f) for f in response["data"]]

    def add(self, resource_type: str, resource_id: int) -> Favorite:
        """Add a resource to favorites.

        Args:
            resource_type: Resource type (mapping, instance)
            resource_id: Resource ID

        Returns:
            Created Favorite object

        Raises:
            NotFoundError: If resource doesn't exist
            ConflictError: If already favorited
        """
        response = self._http.post(
            "/api/favorites",
            json={"resource_type": resource_type, "resource_id": resource_id},
        )
        return Favorite.from_api_response(response["data"])

    def remove(self, resource_type: str, resource_id: int) -> None:
        """Remove a resource from favorites.

        Args:
            resource_type: Resource type (mapping, instance)
            resource_id: Resource ID

        Raises:
            NotFoundError: If favorite doesn't exist
        """
        self._http.delete(f"/api/favorites/{resource_type}/{resource_id}")
