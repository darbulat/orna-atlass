from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr

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
    id: UUID
    email: EmailStr
    role: Literal["member", "editor", "admin"]
    is_active: bool
    created_at: datetime
    membership: MembershipAbsentRead | MembershipRead

    model_config = ConfigDict(from_attributes=True)
