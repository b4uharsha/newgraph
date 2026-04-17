"""Favorites service for business logic."""

from dataclasses import dataclass
from datetime import datetime

from control_plane.models.domain import User
from control_plane.models.errors import AlreadyExistsError, NotFoundError
from control_plane.repositories.favorites import Favorite, FavoritesRepository
from control_plane.repositories.instances import InstanceRepository
from control_plane.repositories.mappings import MappingRepository


@dataclass
class FavoriteWithMetadata:
    """A favorite with enriched resource metadata."""

    resource_type: str
    resource_id: int
    resource_name: str | None
    resource_owner: str | None
    created_at: datetime | None
    resource_exists: bool


class FavoritesService:
    """Service for favorites business logic."""

    def __init__(
        self,
        favorites_repo: FavoritesRepository,
        mapping_repo: MappingRepository,
        instance_repo: InstanceRepository,
    ):
        """Initialize service with repositories.

        Args:
            favorites_repo: Favorites repository
            mapping_repo: Mapping repository
            instance_repo: Instance repository
        """
        self._favorites_repo = favorites_repo
        self._mapping_repo = mapping_repo
        self._instance_repo = instance_repo

    async def list_favorites(
        self,
        user: User,
        resource_type: str | None = None,
    ) -> list[FavoriteWithMetadata]:
        """List favorites for the current user with resource metadata.

        Args:
            user: Current user
            resource_type: Optional filter by resource type

        Returns:
            List of favorites with metadata
        """
        favorites = await self._favorites_repo.list_by_user(
            username=user.username,
            resource_type=resource_type,
        )

        result = []
        for fav in favorites:
            metadata = await self._get_resource_metadata(fav.resource_type, fav.resource_id)
            result.append(
                FavoriteWithMetadata(
                    resource_type=fav.resource_type,
                    resource_id=fav.resource_id,
                    resource_name=metadata.get("name"),
                    resource_owner=metadata.get("owner"),
                    created_at=(
                        datetime.fromisoformat(fav.created_at.replace("Z", "+00:00"))
                        if fav.created_at
                        else None
                    ),
                    resource_exists=metadata.get("exists", False),
                )
            )

        return result

    async def add_favorite(
        self,
        user: User,
        resource_type: str,
        resource_id: int,
    ) -> Favorite:
        """Add a resource to the user's favorites.

        Args:
            user: Current user
            resource_type: Type of resource
            resource_id: Resource ID

        Returns:
            Created favorite

        Raises:
            NotFoundError: If resource doesn't exist
            AlreadyExistsError: If already favorited
        """
        # Check if resource exists
        exists = await self._resource_exists(resource_type, resource_id)
        if not exists:
            raise NotFoundError(resource_type, resource_id)

        # Check if already favorited
        existing = await self._favorites_repo.get(
            username=user.username,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        if existing:
            raise AlreadyExistsError(
                resource_type="favorite",
                message="Resource already in favorites",
            )

        return await self._favorites_repo.add(
            username=user.username,
            resource_type=resource_type,
            resource_id=resource_id,
        )

    async def remove_favorite(
        self,
        user: User,
        resource_type: str,
        resource_id: int,
    ) -> bool:
        """Remove a resource from the user's favorites.

        Idempotent operation - succeeds even if favorite doesn't exist.

        Args:
            user: Current user
            resource_type: Type of resource
            resource_id: Resource ID

        Returns:
            True if removed, False if didn't exist
        """
        removed = await self._favorites_repo.remove(
            username=user.username,
            resource_type=resource_type,
            resource_id=resource_id,
        )

        return removed

    async def _resource_exists(self, resource_type: str, resource_id: int) -> bool:
        """Check if a resource exists.

        Args:
            resource_type: Type of resource
            resource_id: Resource ID

        Returns:
            True if resource exists
        """
        if resource_type == "mapping":
            mapping = await self._mapping_repo.get_by_id(resource_id)
            return mapping is not None
        elif resource_type == "instance":
            instance = await self._instance_repo.get_by_id(resource_id)
            return instance is not None
        return False

    async def _get_resource_metadata(self, resource_type: str, resource_id: int) -> dict:
        """Get metadata for a resource.

        Args:
            resource_type: Type of resource
            resource_id: Resource ID

        Returns:
            Dict with name, owner, and exists fields
        """
        if resource_type == "mapping":
            mapping = await self._mapping_repo.get_by_id(resource_id)
            if mapping:
                return {
                    "name": mapping.name,
                    "owner": mapping.owner_username,
                    "exists": True,
                }
        elif resource_type == "instance":
            instance = await self._instance_repo.get_by_id(resource_id)
            if instance:
                return {
                    "name": instance.name,
                    "owner": instance.owner_username,
                    "exists": True,
                }

        # Resource doesn't exist (deleted)
        return {"name": f"[deleted {resource_type} {resource_id}]", "owner": None, "exists": False}
