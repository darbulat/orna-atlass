from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from orna_atlas.app.core.domain_errors import (
    AuthenticationError,
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)


DOMAIN_ERROR_STATUS_CODES: dict[type[DomainError], int] = {
    NotFoundError: 404,
    ConflictError: 409,
    ValidationError: 422,
    AuthenticationError: 401,
    ForbiddenError: 403,
    ServiceUnavailableError: 503,
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
        status_code = DOMAIN_ERROR_STATUS_CODES.get(type(exc), 500)
        return JSONResponse(status_code=status_code, content={"detail": exc.detail})
