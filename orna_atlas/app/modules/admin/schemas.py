from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
