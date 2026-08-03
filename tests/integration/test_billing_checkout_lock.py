import asyncio
from datetime import UTC, datetime
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from orna_atlas.app.db import models as _models  # noqa: F401
from orna_atlas.app.integrations.bereke import HostedCheckout
from orna_atlas.app.modules.billing import service
from orna_atlas.app.modules.billing.models import BillingPurchase
from orna_atlas.app.modules.users.models import User


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 to run disposable dependency tests",
    ),
]


class BlockingCheckoutProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0
        self.customer_emails: list[str | None] = []

    async def create_checkout(
        self,
        *,
        merchant_reference: str,
        amount_minor: int,
        currency: str,
        description: str,
        customer_email: str | None = None,
    ) -> HostedCheckout:
        self.calls += 1
        self.customer_emails.append(customer_email)
        self.started.set()
        await self.release.wait()
        return HostedCheckout(
            provider_order_id="provider-order-1",
            checkout_url="https://checkout.example/order-1",
        )


@pytest.mark.asyncio
async def test_different_idempotency_keys_share_one_in_flight_checkout() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = uuid4()
    provider = BlockingCheckoutProvider()
    settings = SimpleNamespace(billing_enabled=True)

    try:
        async with AsyncSession(engine) as setup:
            setup.add(
                User(
                    id=user_id,
                    email=f"billing-{user_id}@example.test",
                    password_hash="hashed",
                    email_verified_at=datetime.now(UTC),
                    is_active=True,
                )
            )
            await setup.commit()

        async def create(key: str):
            async with session_factory() as session:
                return await service.create_checkout(
                    session,
                    user_id,
                    key,
                    provider,
                    settings,
                )

        first_task = asyncio.create_task(create("checkout-first"))
        await asyncio.wait_for(provider.started.wait(), timeout=2)
        second = await asyncio.wait_for(create("checkout-second"), timeout=2)

        assert second.status == "provider_outcome_unknown"
        assert second.checkout_url is None
        assert provider.calls == 1
        assert provider.customer_emails == [f"billing-{user_id}@example.test"]

        provider.release.set()
        first = await asyncio.wait_for(first_task, timeout=2)
        assert first.purchase_id == second.purchase_id
        assert first.status == "pending"
        assert provider.calls == 1
    finally:
        provider.release.set()
        async with AsyncSession(engine) as cleanup:
            await cleanup.execute(delete(BillingPurchase).where(BillingPurchase.user_id == user_id))
            await cleanup.execute(delete(User).where(User.id == user_id))
            await cleanup.commit()
        await engine.dispose()
