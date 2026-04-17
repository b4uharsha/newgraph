"""User management API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.infrastructure.database import get_async_session
from control_plane.middleware.identity import CurrentUser
from control_plane.models import UserRole
from control_plane.models.user_models import (
    AssignRoleRequest,
    CreateUserRequest,
    UpdateUserRequest,
    UserResponse,
)
from control_plane.repositories.users import UserRepository
from control_plane.services.user_service import UserService

router = APIRouter(prefix="/api/users", tags=["Users"])


def _require_admin(user: CurrentUser):
    if user.role not in (UserRole.ADMIN, UserRole.OPS):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Ops role required",
        )


def _to_response(user) -> UserResponse:
    return UserResponse(
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        role=user.role.value if hasattr(user.role, "value") else str(user.role),
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
        role_changed_at=getattr(user, "role_changed_at", None),
        role_changed_by=getattr(user, "role_changed_by", None),
    )


@router.post(
    "/bootstrap",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def bootstrap_user(
    request: CreateUserRequest,
    session: AsyncSession = Depends(get_async_session),
):
    repo = UserRepository(session)
    service = UserService(repo)
    try:
        user = await service.bootstrap(request)
        return _to_response(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(e),
        )


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    request: CreateUserRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
):
    _require_admin(user)
    repo = UserRepository(session)
    service = UserService(repo)
    try:
        new_user = await service.create_user(request, user)
        return _to_response(new_user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(e),
        )


@router.get("", response_model=list[UserResponse])
async def list_users(
    user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
    is_active: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    _require_admin(user)
    repo = UserRepository(session)
    service = UserService(repo)
    users = await service.list_users(
        is_active=is_active, limit=limit, offset=offset,
    )
    return [_to_response(u) for u in users]


@router.get("/{username}", response_model=UserResponse)
async def get_user(
    username: str,
    user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
):
    if user.role not in (UserRole.ADMIN, UserRole.OPS) and user.username != username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot view other users",
        )
    repo = UserRepository(session)
    service = UserService(repo)
    found = await service.get_user(username)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found",
        )
    return _to_response(found)


@router.put("/{username}", response_model=UserResponse)
async def update_user(
    username: str,
    request: UpdateUserRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
):
    _require_admin(user)
    repo = UserRepository(session)
    service = UserService(repo)
    updated = await service.update_user(username, request, user)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found",
        )
    return _to_response(updated)


@router.put("/{username}/role", response_model=UserResponse)
async def assign_role(
    username: str,
    request: AssignRoleRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
):
    _require_admin(user)
    repo = UserRepository(session)
    service = UserService(repo)
    updated = await service.assign_role(username, request, user)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found",
        )
    return _to_response(updated)


@router.delete("/{username}", response_model=UserResponse)
async def deactivate_user(
    username: str,
    user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
):
    _require_admin(user)
    repo = UserRepository(session)
    service = UserService(repo)
    deactivated = await service.deactivate_user(username, user)
    if not deactivated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found",
        )
    return _to_response(deactivated)
