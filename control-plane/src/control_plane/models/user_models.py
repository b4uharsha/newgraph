"""User management request and response models."""

from datetime import datetime

from pydantic import BaseModel, Field


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=255)
    email: str
    display_name: str = Field(..., min_length=1, max_length=255)
    role: str = Field(default="analyst", pattern=r"^(analyst|admin|ops)$")


class UpdateUserRequest(BaseModel):
    email: str | None = None
    display_name: str | None = None
    is_active: bool | None = None


class AssignRoleRequest(BaseModel):
    role: str = Field(..., pattern=r"^(analyst|admin|ops)$")


class UserResponse(BaseModel):
    username: str
    email: str
    display_name: str
    role: str
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_login_at: datetime | None = None
    role_changed_at: datetime | None = None
    role_changed_by: str | None = None
