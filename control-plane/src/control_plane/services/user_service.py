"""User management service."""

import structlog

from control_plane.models import RequestUser, User, UserRole
from control_plane.models.user_models import (
    AssignRoleRequest,
    CreateUserRequest,
    UpdateUserRequest,
)
from control_plane.repositories.users import UserRepository

logger = structlog.get_logger(__name__)


class UserService:
    def __init__(self, user_repo: UserRepository):
        self._repo = user_repo

    async def create_user(self, request: CreateUserRequest, actor: RequestUser) -> User:
        existing = await self._repo.get_by_username(request.username)
        if existing:
            raise ValueError(f"User {request.username} already exists")
        return await self._repo.create_with_role(
            username=request.username,
            email=request.email,
            display_name=request.display_name,
            role=UserRole(request.role),
        )

    async def get_user(self, username: str) -> User | None:
        return await self._repo.get_by_username(username)

    async def list_users(
        self,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[User]:
        users, _total = await self._repo.list_users(
            is_active=is_active, limit=limit, offset=offset,
        )
        return users

    async def update_user(
        self,
        username: str,
        request: UpdateUserRequest,
        actor: RequestUser,
    ) -> User | None:
        user = await self._repo.get_by_username(username)
        if user is None:
            return None
        return await self._repo.update_fields(
            username,
            email=request.email,
            display_name=request.display_name,
            is_active=request.is_active,
        )

    async def assign_role(
        self,
        username: str,
        request: AssignRoleRequest,
        actor: RequestUser,
    ) -> User | None:
        return await self._repo.assign_role(
            username, role=UserRole(request.role), changed_by=actor.username,
        )

    async def deactivate_user(self, username: str, actor: RequestUser) -> User | None:
        user = await self._repo.get_by_username(username)
        if user is None:
            return None
        return await self._repo.update_fields(username, is_active=False)

    async def bootstrap(self, request: CreateUserRequest) -> User:
        count = await self._repo.count()
        if count > 0:
            raise ValueError("Bootstrap only works when no users exist")
        return await self._repo.create_with_role(
            username=request.username,
            email=request.email,
            display_name=request.display_name,
            role=UserRole.OPS,
        )
