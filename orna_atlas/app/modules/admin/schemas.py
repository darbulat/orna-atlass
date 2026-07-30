from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from orna_atlas.app.modules.admin.context import build_admin_etag, build_admin_user_etag
from orna_atlas.app.modules.collections.schemas import CollectionAdminRead
from orna_atlas.app.modules.locations.schemas import AdminLocationRead as AdminLocationReadBase
from orna_atlas.app.modules.sessions.schemas import SessionRead
from orna_atlas.app.modules.users.schemas import AdminUserRead


class AdminIdentityRead(BaseModel):
    id: str
    is_admin: bool
    role: Literal["admin"]
    mode: Literal["token", "local"]


class AdminErrorResponse(BaseModel):
    detail: str


class _RevisionMixin:
    id: UUID
    updated_at: datetime

    @computed_field(return_type=str)
    @property
    def revision(self) -> str:
        return build_admin_etag(resource_id=self.id, updated_at=self.updated_at)


class AdminLocationRead(_RevisionMixin, AdminLocationReadBase):
    pass


class AdminSessionResource(_RevisionMixin, SessionRead):
    pass


class AdminCollectionResource(_RevisionMixin, CollectionAdminRead):
    pass


class AdminUserResource(AdminUserRead):
    revision: str

    @model_validator(mode="before")
    @classmethod
    def add_aggregate_revision(cls, value):
        if (
            isinstance(value, dict)
            and "user" in value
            and "revision" in value
        ):
            return value
        user = value.get("user", value) if isinstance(value, dict) else value.user
        resource_id = user.get("id") if isinstance(user, dict) else user.id
        updated_at = value.get("updated_at") if isinstance(value, dict) else value.updated_at
        membership = value.get("membership") if isinstance(value, dict) else value.membership
        membership_updated_at = (
            value.get("membership_updated_at")
            if isinstance(value, dict)
            else value.membership_updated_at
        )
        assert resource_id is not None and updated_at is not None
        return {
            "user": user,
            "membership": membership,
            "revision": build_admin_user_etag(
                user_id=resource_id,
                user_updated_at=updated_at,
                membership_updated_at=membership_updated_at,
            ),
        }


class AuditEventRead(BaseModel):
    id: UUID
    actor_user_id: UUID | None
    event_type: str
    subject_type: str
    subject_id: str | None
    ip_address: str | None
    user_agent: str | None
    metadata: dict = Field(validation_alias="metadata_")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
