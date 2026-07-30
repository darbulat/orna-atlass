from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


PurchaseStatus = Literal[
    "creating", "pending", "paid", "failed", "expired", "refund_requested", "refunded"
]


class BillingOfferRead(BaseModel):
    product_code: Literal["lifetime_member"] = "lifetime_member"
    name: str = "Lifetime Member Access"
    description: str = "Permanent access to available members-only field recordings."
    amount_minor: int = Field(default=1000, gt=0)
    currency: Literal["USD", "KZT"] = "USD"
    is_recurring: Literal[False] = False
    checkout_available: bool
    refund_summary: str = "Full refund requests are accepted within 14 calendar days."


class CheckoutCreate(BaseModel):
    product_code: Literal["lifetime_member"] = "lifetime_member"


class CheckoutRead(BaseModel):
    purchase_id: UUID
    merchant_reference: str
    status: PurchaseStatus
    checkout_url: str | None = None
    expires_at: datetime | None = None


class PurchaseRead(BaseModel):
    id: UUID
    merchant_reference: str
    product_code: Literal["lifetime_member"]
    amount_minor: int = Field(gt=0)
    currency: Literal["USD", "KZT"]
    status: PurchaseStatus
    paid_at: datetime | None = None
    refunded_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class RefundRequestCreate(BaseModel):
    acknowledge_full_refund: Literal[True] = Field(
        description="Confirms that the request is for a full refund and ends paid access when completed."
    )


class RefundRequestRead(BaseModel):
    id: UUID
    purchase_id: UUID
    status: Literal["requested", "processing", "completed", "rejected"]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
