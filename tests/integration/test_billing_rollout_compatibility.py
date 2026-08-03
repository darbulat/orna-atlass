import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from orna_atlas.app.db import models as _models  # noqa: F401
from orna_atlas.app.modules.billing.models import BillingPurchase
from orna_atlas.app.modules.memberships.models import MembershipEntitlementGrant
from orna_atlas.app.modules.memberships.models import Membership
from orna_atlas.app.modules.users import repository as users_repository
from orna_atlas.app.modules.users.models import User


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 to run disposable dependency tests",
    ),
]


@pytest.mark.asyncio
async def test_old_callback_writes_stay_grant_compatible_after_cutover() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    user_id = uuid4()
    purchase_id = uuid4()
    now = datetime.now(UTC)

    try:
        async with AsyncSession(engine) as session:
            session.add(
                User(
                    id=user_id,
                    email=f"rollout-{user_id}@example.test",
                    password_hash="hashed",
                    email_verified_at=now,
                    is_active=True,
                )
            )
            await session.flush()
            session.add(
                BillingPurchase(
                    id=purchase_id,
                    user_id=user_id,
                    merchant_reference=f"orna-rollout-{purchase_id.hex[:24]}",
                    idempotency_key=f"rollout-{purchase_id}",
                    product_code="lifetime_member",
                    amount_minor=1000,
                    currency="USD",
                    status="creating",
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.commit()

            # Simulate the previous callback implementation, which updated only the purchase.
            await session.execute(
                update(BillingPurchase)
                .where(BillingPurchase.id == purchase_id)
                .values(status="paid", paid_at=now, updated_at=now)
            )
            await session.commit()
            grant = await session.scalar(
                select(MembershipEntitlementGrant).where(
                    MembershipEntitlementGrant.source_type == "billing_purchase",
                    MembershipEntitlementGrant.source_id == purchase_id,
                )
            )
            assert grant is not None
            assert grant.status == "active"

            await session.execute(
                update(BillingPurchase)
                .where(BillingPurchase.id == purchase_id)
                .values(status="refunded", refunded_at=now, updated_at=now)
            )
            await session.commit()
            await session.refresh(grant)
            assert grant.status == "revoked"
            assert grant.revoked_at is not None
    finally:
        async with AsyncSession(engine) as cleanup:
            await cleanup.execute(delete(BillingPurchase).where(BillingPurchase.id == purchase_id))
            await cleanup.execute(delete(User).where(User.id == user_id))
            await cleanup.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_admin_membership_filter_uses_active_grant_union() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    user_id = uuid4()
    membership_id = uuid4()
    grant_id = uuid4()
    now = datetime.now(UTC)

    try:
        async with AsyncSession(engine) as session:
            session.add(
                User(
                    id=user_id,
                    email=f"admin-grant-{user_id}@example.test",
                    password_hash="hashed",
                    email_verified_at=now,
                    is_active=True,
                )
            )
            await session.flush()
            session.add(
                Membership(
                    id=membership_id,
                    user_id=user_id,
                    plan="member",
                    status="cancelled",
                    starts_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                MembershipEntitlementGrant(
                    id=grant_id,
                    user_id=user_id,
                    source_type="billing_purchase",
                    source_id=uuid4(),
                    plan="lifetime_member",
                    status="active",
                    starts_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.commit()

            active = await users_repository.list_for_admin(
                session,
                membership_status="active",
                limit=50,
                offset=0,
            )
            cancelled = await users_repository.list_for_admin(
                session,
                membership_status="cancelled",
                limit=50,
                offset=0,
            )

            assert user_id in {user.id for user in active}
            assert user_id not in {user.id for user in cancelled}
    finally:
        async with AsyncSession(engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == user_id))
            await cleanup.commit()
        await engine.dispose()
