from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.modules.admin.models import AuditEvent


async def add_audit_event(
    session: AsyncSession,
    *,
    event_type: str,
    subject_type: str,
    subject_id: str | None = None,
    actor_user_id: UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        event_type=event_type,
        subject_type=subject_type,
        subject_id=subject_id,
        actor_user_id=actor_user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata_=metadata or {},
    )
    session.add(event)
    await session.flush()
    return event


async def list_audit_events(
    session: AsyncSession,
    *,
    event_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditEvent]:
    query = select(AuditEvent)
    if event_type:
        query = query.where(AuditEvent.event_type == event_type)
    result = await session.execute(
        query.order_by(AuditEvent.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars())
