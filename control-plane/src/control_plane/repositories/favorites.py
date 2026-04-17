"""User favorites repository for database operations."""

from dataclasses import dataclass

from control_plane.repositories.base import (
    BaseRepository,
    utc_now,
)


@dataclass
class Favorite:
    """A user's favorite resource."""

    username: str
    resource_type: str  # 'mapping', 'snapshot', 'instance'
    resource_id: int
    created_at: str | None


class FavoritesRepository(BaseRepository):
    """Repository for user favorites database operations."""

    async def list_by_user(
        self,
        username: str,
        resource_type: str | None = None,
    ) -> list[Favorite]:
        """List favorites for a user.

        Args:
            username: User's username
            resource_type: Optional filter by resource type

        Returns:
            List of Favorite objects
        """
        if resource_type:
            sql = """
                SELECT username, resource_type, resource_id, created_at
                FROM user_favorites
                WHERE username = :username AND resource_type = :resource_type
                ORDER BY created_at DESC
            """
            rows = await self._fetch_all(
                sql, {"username": username, "resource_type": resource_type}
            )
        else:
            sql = """
                SELECT username, resource_type, resource_id, created_at
                FROM user_favorites
                WHERE username = :username
                ORDER BY created_at DESC
            """
            rows = await self._fetch_all(sql, {"username": username})

        return [self._row_to_favorite(row) for row in rows]

    async def get(
        self,
        username: str,
        resource_type: str,
        resource_id: int,
    ) -> Favorite | None:
        """Get a specific favorite.

        Args:
            username: User's username
            resource_type: Type of resource
            resource_id: Resource ID

        Returns:
            Favorite or None if not found
        """
        sql = """
            SELECT username, resource_type, resource_id, created_at
            FROM user_favorites
            WHERE username = :username
              AND resource_type = :resource_type
              AND resource_id = :resource_id
        """
        row = await self._fetch_one(
            sql,
            {
                "username": username,
                "resource_type": resource_type,
                "resource_id": resource_id,
            },
        )
        if row is None:
            return None
        return self._row_to_favorite(row)

    async def add(
        self,
        username: str,
        resource_type: str,
        resource_id: int,
    ) -> Favorite:
        """Add a resource to favorites.

        Args:
            username: User's username
            resource_type: Type of resource ('mapping', 'snapshot', 'instance')
            resource_id: Resource ID

        Returns:
            Created Favorite
        """
        now = utc_now()
        sql = """
            INSERT INTO user_favorites (username, resource_type, resource_id, created_at)
            VALUES (:username, :resource_type, :resource_id, :created_at)
            ON CONFLICT (username, resource_type, resource_id) DO NOTHING
        """
        await self._execute(
            sql,
            {
                "username": username,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "created_at": now,
            },
        )

        return Favorite(
            username=username,
            resource_type=resource_type,
            resource_id=resource_id,
            created_at=now,
        )

    async def remove(
        self,
        username: str,
        resource_type: str,
        resource_id: int,
    ) -> bool:
        """Remove a resource from favorites.

        Args:
            username: User's username
            resource_type: Type of resource
            resource_id: Resource ID

        Returns:
            True if favorite was removed
        """
        sql = """
            DELETE FROM user_favorites
            WHERE username = :username
              AND resource_type = :resource_type
              AND resource_id = :resource_id
        """
        result = await self._execute(
            sql,
            {
                "username": username,
                "resource_type": resource_type,
                "resource_id": resource_id,
            },
        )
        return result.rowcount > 0

    async def remove_for_resource(
        self,
        resource_type: str,
        resource_id: int,
    ) -> int:
        """Remove all favorites for a deleted resource.

        Should be called when a resource is deleted to clean up orphaned favorites.

        Args:
            resource_type: Type of resource
            resource_id: Resource ID

        Returns:
            Number of favorites removed
        """
        sql = """
            DELETE FROM user_favorites
            WHERE resource_type = :resource_type
              AND resource_id = :resource_id
        """
        result = await self._execute(
            sql,
            {
                "resource_type": resource_type,
                "resource_id": resource_id,
            },
        )
        return result.rowcount

    async def is_favorite(
        self,
        username: str,
        resource_type: str,
        resource_id: int,
    ) -> bool:
        """Check if a resource is in user's favorites.

        Args:
            username: User's username
            resource_type: Type of resource
            resource_id: Resource ID

        Returns:
            True if resource is a favorite
        """
        sql = """
            SELECT 1 FROM user_favorites
            WHERE username = :username
              AND resource_type = :resource_type
              AND resource_id = :resource_id
        """
        row = await self._fetch_one(
            sql,
            {
                "username": username,
                "resource_type": resource_type,
                "resource_id": resource_id,
            },
        )
        return row is not None

    async def count_by_user(self, username: str) -> int:
        """Count total favorites for a user.

        Args:
            username: User's username

        Returns:
            Number of favorites
        """
        sql = "SELECT COUNT(*) FROM user_favorites WHERE username = :username"
        return await self._fetch_scalar(sql, {"username": username}) or 0

    def _row_to_favorite(self, row) -> Favorite:
        """Convert database row to Favorite object."""
        return Favorite(
            username=row.username,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            created_at=row.created_at,
        )
