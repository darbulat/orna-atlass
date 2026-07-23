from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.modules.admin import repository
from orna_atlas.app.modules.admin.models import AuditEvent


async def list_audit_events(
    session: AsyncSession,
    *,
    event_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditEvent]:
    return await repository.list_audit_events(
        session,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
