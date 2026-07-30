from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, model_validator

from orna_atlas.app.modules.memberships.schemas import MembershipAbsentRead, MembershipRead


class UserRead(BaseModel):
    id: UUID
    email: EmailStr
    email_verified: bool
    role: Literal["member", "editor", "admin"]
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserRoleUpdate(BaseModel):
    role: Literal["member", "editor", "admin"]


class AdminUserRead(BaseModel):
    user: UserRead
    membership: MembershipAbsentRead | MembershipRead

    @model_validator(mode="before")
    @classmethod
    def project_user_and_membership(cls, value: Any):
        if isinstance(value, dict) and "user" in value:
            return value
        if hasattr(value, "user"):
            return {"user": value.user, "membership": value.membership}
        membership = value.get("membership") if isinstance(value, dict) else value.membership
        return {"user": value, "membership": membership}

    model_config = ConfigDict(from_attributes=True)
