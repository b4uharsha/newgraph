"""Favorites API router."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.infrastructure.database import get_async_session
from control_plane.middleware.identity import CurrentUser
from control_plane.models.requests import AddFavoriteRequest
from control_plane.models.responses import (
    DataResponse,
    FavoriteCreatedResponse,
    FavoriteDeletedResponse,
    FavoriteResponse,
)
from control_plane.repositories.favorites import FavoritesRepository
from control_plane.repositories.instances import InstanceRepository
from control_plane.repositories.mappings import MappingRepository
from control_plane.services.favorites_service import FavoritesService

router = APIRouter(prefix="/api/favorites", tags=["Favorites"])


def get_favorites_service(
    session: AsyncSession = Depends(get_async_session),
) -> FavoritesService:
    """Dependency to get favorites service."""
    return FavoritesService(
        favorites_repo=FavoritesRepository(session),
        mapping_repo=MappingRepository(session),
        instance_repo=InstanceRepository(session),
    )


FavoritesServiceDep = Annotated[FavoritesService, Depends(get_favorites_service)]


@router.get("", response_model=DataResponse[list[FavoriteResponse]])
async def list_favorites(
    user: CurrentUser,
    service: FavoritesServiceDep,
    resource_type: str | None = None,
) -> DataResponse[list[FavoriteResponse]]:
    """List current user's favorites.

    Args:
        user: Current authenticated user
        service: Favorites service
        resource_type: Optional filter by resource type (mapping, instance)

    Returns:
        List of favorites with resource metadata
    """
    favorites = await service.list_favorites(user, resource_type)

    return DataResponse(
        data=[
            FavoriteResponse(
                resource_type=fav.resource_type,
                resource_id=fav.resource_id,
                resource_name=fav.resource_name,
                resource_owner=fav.resource_owner,
                created_at=fav.created_at,
                resource_exists=fav.resource_exists,
            )
            for fav in favorites
        ]
    )


@router.post(
    "",
    response_model=DataResponse[FavoriteCreatedResponse],
    status_code=status.HTTP_201_CREATED,
)
async def add_favorite(
    user: CurrentUser,
    service: FavoritesServiceDep,
    request: AddFavoriteRequest,
) -> DataResponse[FavoriteCreatedResponse]:
    """Add a resource to favorites.

    Args:
        user: Current authenticated user
        service: Favorites service
        request: Favorite request with resource_type and resource_id

    Returns:
        Created favorite

    Raises:
        NotFoundError: If resource doesn't exist
        AlreadyExistsError: If already favorited
    """
    favorite = await service.add_favorite(
        user,
        request.resource_type,
        request.resource_id,
    )

    return DataResponse(
        data=FavoriteCreatedResponse(
            resource_type=favorite.resource_type,
            resource_id=favorite.resource_id,
            created_at=(
                datetime.fromisoformat(favorite.created_at.replace("Z", "+00:00"))
                if favorite.created_at
                else None
            ),
        )
    )


@router.delete(
    "/{resource_type}/{resource_id}",
    response_model=DataResponse[FavoriteDeletedResponse],
    status_code=status.HTTP_200_OK,
)
async def remove_favorite(
    resource_type: str,
    resource_id: int,
    user: CurrentUser,
    service: FavoritesServiceDep,
) -> DataResponse[FavoriteDeletedResponse]:
    """Remove a resource from favorites.

    Idempotent operation - succeeds even if favorite doesn't exist.

    Args:
        resource_type: Type of resource (mapping, instance)
        resource_id: Resource ID
        user: Current authenticated user
        service: Favorites service

    Returns:
        Confirmation of deletion
    """
    await service.remove_favorite(user, resource_type, resource_id)
    return DataResponse(data=FavoriteDeletedResponse(deleted=True))
