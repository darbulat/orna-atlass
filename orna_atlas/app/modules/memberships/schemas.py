from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MembershipRead(BaseModel):
    id: UUID | None = None
    user_id: UUID
    status: Literal["inactive", "active", "cancelled", "expired"]
    plan: str
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    is_entitled: bool

    model_config = ConfigDict(from_attributes=True)


class MembershipUpdate(BaseModel):
    status: Literal["inactive", "active", "cancelled", "expired"]
    plan: str = "member"
    expires_at: datetime | None = None


class MembershipAbsentRead(MembershipRead):
    status: Literal["inactive"] = "inactive"
    plan: str = "none"
    is_entitled: bool = False
