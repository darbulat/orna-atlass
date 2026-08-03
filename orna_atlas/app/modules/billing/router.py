from typing import Annotated
from urllib.parse import parse_qsl
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response, Security, status
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.config import Settings, get_settings
from orna_atlas.app.core.security import CurrentUser, get_current_user
from orna_atlas.app.db.session import get_db_session
from orna_atlas.app.core.domain_errors import ValidationError
from orna_atlas.app.integrations.bereke import BerekeHostedCheckoutClient
from orna_atlas.app.modules.billing import service
from orna_atlas.app.modules.billing.schemas import (
    BillingOfferRead,
    CheckoutCreate,
    CheckoutRead,
    PurchaseRead,
    RefundRequestCreate,
    RefundRequestRead,
)

router = APIRouter(prefix="/billing", tags=["billing"])

CALLBACK_MAX_BYTES = 16 * 1024
CALLBACK_MAX_PARAMETERS = 32
CALLBACK_MAX_NAME_BYTES = 128
CALLBACK_MAX_VALUE_BYTES = 4096


async def _read_callback_pairs(request: Request) -> list[tuple[str, str]]:
    raw_query = request.scope.get("query_string", b"")
    if len(raw_query) > CALLBACK_MAX_BYTES:
        raise ValidationError("Bereke callback is too large")
    if raw_query and raw_query.count(b"&") + 1 > CALLBACK_MAX_PARAMETERS:
        raise ValidationError("Bereke callback has too many parameters")
    try:
        pairs = list(
            parse_qsl(
                raw_query.decode("ascii"),
                keep_blank_values=True,
                strict_parsing=True,
                max_num_fields=CALLBACK_MAX_PARAMETERS,
            )
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValidationError("Invalid Bereke callback query") from exc

    body = bytearray()
    async for chunk in request.stream():
        if len(raw_query) + len(body) + len(chunk) > CALLBACK_MAX_BYTES:
            raise ValidationError("Bereke callback is too large")
        body.extend(chunk)
    if body:
        content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type != "application/x-www-form-urlencoded":
            raise ValidationError("Invalid Bereke callback content type")
        try:
            pairs.extend(
                parse_qsl(
                    body.decode(),
                    keep_blank_values=True,
                    strict_parsing=True,
                    max_num_fields=CALLBACK_MAX_PARAMETERS,
                )
            )
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValidationError("Invalid Bereke callback form") from exc
    if len(pairs) > CALLBACK_MAX_PARAMETERS:
        raise ValidationError("Bereke callback has too many parameters")
    if any(
        len(name.encode()) > CALLBACK_MAX_NAME_BYTES
        or len(value.encode()) > CALLBACK_MAX_VALUE_BYTES
        for name, value in pairs
    ):
        raise ValidationError("Bereke callback parameter is too large")
    if len({name for name, _value in pairs}) != len(pairs):
        raise ValidationError("Duplicate Bereke callback parameters")
    return pairs
bearer_scheme = HTTPBearer(auto_error=False)
cookie_scheme = APIKeyCookie(name="orna_access", auto_error=False)


async def get_billing_user(
    _credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
    _access_cookie: Annotated[str | None, Security(cookie_scheme)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    return current_user


BillingUser = Annotated[CurrentUser, Depends(get_billing_user)]
Database = Annotated[AsyncSession, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]


@router.get("/offer", response_model=BillingOfferRead)
async def read_offer(db: Database, settings: AppSettings) -> BillingOfferRead:
    return await service.public_offer(db, settings)


@router.post("/checkouts", response_model=CheckoutRead, status_code=status.HTTP_201_CREATED)
async def create_checkout(
    _data: CheckoutCreate,
    current_user: BillingUser,
    db: Database,
    settings: AppSettings,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    ],
) -> CheckoutRead:
    return await service.create_checkout(
        db,
        UUID(current_user.id),
        idempotency_key,
        BerekeHostedCheckoutClient(settings),
        settings,
    )


@router.get("/purchases/me", response_model=list[PurchaseRead])
async def read_my_purchases(current_user: BillingUser, db: Database) -> list[PurchaseRead]:
    return await service.list_purchases(db, UUID(current_user.id))


@router.get("/purchases/{purchase_id}", response_model=PurchaseRead)
async def read_purchase(
    purchase_id: UUID, current_user: BillingUser, db: Database
) -> PurchaseRead:
    return await service.get_purchase(db, UUID(current_user.id), purchase_id)


@router.post(
    "/purchases/{purchase_id}/refund-requests",
    response_model=RefundRequestRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_refund_request(
    purchase_id: UUID,
    _data: RefundRequestCreate,
    current_user: BillingUser,
    db: Database,
) -> RefundRequestRead:
    return await service.request_refund(db, UUID(current_user.id), purchase_id)


@router.api_route(
    "/callbacks/bereke",
    methods=["GET", "POST"],
    status_code=status.HTTP_204_NO_CONTENT,
    include_in_schema=False,
)
async def bereke_callback(
    request: Request,
    db: Database,
    settings: AppSettings,
) -> Response:
    pairs = await _read_callback_pairs(request)
    callback = await BerekeHostedCheckoutClient(settings).resolve_callback(dict(pairs))
    if callback is not None:
        await service.apply_callback(db, callback)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
