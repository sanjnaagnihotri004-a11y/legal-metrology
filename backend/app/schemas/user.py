
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Role, UtcDatetime


class UserBrief(BaseModel):
    """Used inside the login response and /auth/me."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: Role


class UserOut(UserBrief):
    """Used by the admin user list."""
    is_active: bool
    created_at: UtcDatetime


class LoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserBrief


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8)
    role: Role


class UserUpdate(BaseModel):
    role: Role | None = None
    is_active: bool | None = None