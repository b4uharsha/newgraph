"""User management resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from graph_olap.http import HTTPClient


class UserResource:
    """User management operations.

    Requires admin or ops role for most operations.

    Example:
        >>> client = GraphOLAPClient(api_url=api_url, username="admin-user")
        >>> users = client.users.list()
        >>> new_user = client.users.create(
        ...     username="analyst1",
        ...     email="analyst1@example.com",
        ...     display_name="First Analyst",
        ... )
    """

    def __init__(self, http: HTTPClient):
        """Initialize user resource.

        Args:
            http: HTTP client for API requests
        """
        self._http = http

    def create(
        self,
        username: str,
        email: str,
        display_name: str,
        role: str = "analyst",
    ) -> dict[str, Any]:
        """Create a new user.

        Requires: Admin or Ops role.

        Args:
            username: Unique username
            email: Email address
            display_name: Display name
            role: User role (analyst, admin, or ops)

        Returns:
            Created user data
        """
        return self._http.post(
            "/api/users",
            json={
                "username": username,
                "email": email,
                "display_name": display_name,
                "role": role,
            },
        )

    def list(
        self,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List users with optional filters.

        Requires: Admin or Ops role.

        Args:
            is_active: Filter by active status
            limit: Maximum results (1-200)
            offset: Number of results to skip

        Returns:
            List of user data dictionaries
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if is_active is not None:
            params["is_active"] = is_active
        return self._http.get("/api/users", params=params)

    def get(self, username: str) -> dict[str, Any]:
        """Get a user by username.

        Admin/Ops can view any user. Other roles can only view themselves.

        Args:
            username: Username to look up

        Returns:
            User data dictionary
        """
        return self._http.get(f"/api/users/{username}")

    def update(self, username: str, **kwargs) -> dict[str, Any]:
        """Update user fields.

        Requires: Admin or Ops role.

        Args:
            username: Username to update
            **kwargs: Fields to update (email, display_name, is_active)

        Returns:
            Updated user data
        """
        return self._http.put(f"/api/users/{username}", json=kwargs)

    def assign_role(self, username: str, role: str) -> dict[str, Any]:
        """Assign a role to a user.

        Requires: Admin or Ops role.

        Args:
            username: Username to update
            role: New role (analyst, admin, or ops)

        Returns:
            Updated user data
        """
        return self._http.put(
            f"/api/users/{username}/role", json={"role": role},
        )

    def deactivate(self, username: str) -> dict[str, Any]:
        """Deactivate a user account.

        Requires: Admin or Ops role.

        Args:
            username: Username to deactivate

        Returns:
            Deactivated user data
        """
        return self._http.delete(f"/api/users/{username}")

    def bootstrap(
        self,
        username: str,
        email: str,
        display_name: str,
    ) -> dict[str, Any]:
        """Bootstrap the first user (ops role).

        Only works when no users exist in the database.

        Args:
            username: Username for the first user
            email: Email address
            display_name: Display name

        Returns:
            Created user data with ops role
        """
        return self._http.post(
            "/api/users/bootstrap",
            json={
                "username": username,
                "email": email,
                "display_name": display_name,
                "role": "ops",
            },
        )
