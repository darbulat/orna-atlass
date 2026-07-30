from uuid import UUID

from datetime import datetime

from sqlalchemy import and_
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
    actor_user_id: str | UUID | None = None,
    subject_type: str | None = None,
    subject_id: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditEvent]:
    query = select(AuditEvent)
    filters = []
    if event_type:
        filters.append(AuditEvent.event_type == event_type)
    if actor_user_id is not None:
        if isinstance(actor_user_id, UUID):
            filters.append(AuditEvent.actor_user_id == actor_user_id)
        else:
            filters.append(AuditEvent.actor_user_id == UUID(actor_user_id))
    if subject_type:
        filters.append(AuditEvent.subject_type == subject_type)
    if subject_id:
        filters.append(AuditEvent.subject_id == subject_id)
    if created_from is not None:
        filters.append(AuditEvent.created_at >= created_from)
    if created_to is not None:
        filters.append(AuditEvent.created_at <= created_to)

    if filters:
        query = query.where(and_(*filters))
    result = await session.execute(
        query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars())
