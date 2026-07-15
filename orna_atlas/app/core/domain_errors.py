class DomainError(Exception):
    """Business/application failure that is independent of an HTTP transport."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class NotFoundError(DomainError):
    pass


class ConflictError(DomainError):
    pass


class ValidationError(DomainError):
    pass


class AuthenticationError(DomainError):
    pass


class ForbiddenError(DomainError):
    pass


class ServiceUnavailableError(DomainError):
    pass
