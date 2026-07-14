import ast
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from orna_atlas.app.core.domain_errors import (
    AuthenticationError,
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from orna_atlas.app.core.errors import register_error_handlers


@pytest.mark.parametrize(
    ("error_type", "status_code"),
    [
        (NotFoundError, 404),
        (ConflictError, 409),
        (ValidationError, 422),
        (AuthenticationError, 401),
        (ForbiddenError, 403),
        (ServiceUnavailableError, 503),
    ],
)
def test_app_maps_domain_errors_to_http_responses(
    error_type: type[DomainError], status_code: int
) -> None:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/probe")
    async def probe() -> None:
        raise error_type("domain failure")

    response = TestClient(app).get("/probe")

    assert response.status_code == status_code
    assert response.json() == {"detail": "domain failure"}


def test_domain_services_do_not_import_fastapi() -> None:
    modules_root = Path(__file__).parents[1] / "modules"
    service_files = sorted(modules_root.glob("*/service.py"))

    assert service_files
    for service_file in service_files:
        tree = ast.parse(service_file.read_text())
        fastapi_imports = [
            node
            for node in ast.walk(tree)
            if (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.module.startswith("fastapi")
            )
            or (
                isinstance(node, ast.Import)
                and any(alias.name.startswith("fastapi") for alias in node.names)
            )
        ]
        assert not fastapi_imports, f"{service_file} imports FastAPI transport primitives"
