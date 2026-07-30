from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from orna_atlas.app.modules.admin import repository
from orna_atlas.app.modules.admin.models import AuditEvent
from orna_atlas.app.core.domain_errors import ValidationError


async def list_audit_events(
    session: AsyncSession,
    *,
    event_type: str | None = None,
    actor_user_id=None,
    subject_type: str | None = None,
    subject_id: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditEvent]:
    if created_from is not None and created_from.tzinfo is None:
        raise ValidationError("created_from must be timezone-aware")
    if created_to is not None and created_to.tzinfo is None:
        raise ValidationError("created_to must be timezone-aware")
    if created_from is not None and created_to is not None and created_from > created_to:
        raise ValidationError("created_from must be before or equal created_to")
    return await repository.list_audit_events(
        session,
        event_type=event_type,
        actor_user_id=actor_user_id,
        subject_type=subject_type,
        subject_id=subject_id,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
        offset=offset,
    )
