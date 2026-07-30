from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from uuid import UUID

from fastapi import HTTPException, Request, status

from orna_atlas.app.core.security import CurrentUser


@dataclass
class AdminMutationContext:
    actor_user_id: UUID | None
    actor_mode: str | None
    ip_address: str | None
    user_agent: str | None


def build_admin_mutation_context(
    current_user: CurrentUser, request: Request | None = None
) -> AdminMutationContext:
    actor_mode = None
    actor_user_id: UUID | None = None

    if current_user.id != "local-admin":
        actor_user_id = UUID(current_user.id)
    else:
        actor_mode = "local"

    ip_address = request.client.host if request is not None and request.client else None
    user_agent_header = request.headers.get("user-agent") if request is not None else None
    user_agent = user_agent_header[:512] if user_agent_header else None

    return AdminMutationContext(
        actor_user_id=actor_user_id,
        actor_mode=actor_mode,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def apply_actor_mode_metadata(
    metadata: dict[str, object] | None, actor_mode: str | None
) -> dict[str, object] | None:
    if actor_mode is None:
        return metadata

    normalized = dict(metadata or {})
    normalized["actor_mode"] = actor_mode
    return normalized


def build_admin_etag(*, resource_id: UUID | str, updated_at: datetime | None) -> str:
    """Build a stable ETag for admin entity concurrency control."""

    timestamp = int(updated_at.timestamp() * 1_000_000) if updated_at is not None else 0
    token = f"{resource_id}:{timestamp}"
    digest = sha256(token.encode("utf-8")).hexdigest()[:16]
    # If-Match requires a strong validator; weak ETags can never satisfy it.
    return f'"{digest}"'


def build_admin_user_etag(
    *,
    user_id: UUID | str,
    user_updated_at: datetime,
    membership_updated_at: datetime | None,
) -> str:
    """Build the Tier-C aggregate user/membership precondition."""

    aggregate_updated_at = max(
        timestamp
        for timestamp in (user_updated_at, membership_updated_at)
        if timestamp is not None
    )
    return build_admin_etag(resource_id=user_id, updated_at=aggregate_updated_at)


def validate_if_match_or_fail(
    *,
    if_match: str | None,
    expected: str,
) -> None:
    if if_match is None:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail="If-Match required for this operation",
        )

    if if_match != expected:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail="Precondition failed: resource was modified",
        )
