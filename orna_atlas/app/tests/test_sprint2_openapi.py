import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from orna_atlas.app.main import app
from orna_atlas.app.modules.locations.schemas import LocationUpdate
from orna_atlas.app.modules.sessions.schemas import SessionUpdate


def test_sprint2_routes_are_registered() -> None:
    schema = TestClient(app).get("/openapi.json").json()

    assert "/api/v1/locations" in schema["paths"]
    assert "/api/v1/locations/{locator}" in schema["paths"]
    assert "/api/v1/sessions" in schema["paths"]
    assert "/api/v1/sessions/{locator}" in schema["paths"]
    assert "/api/v1/admin/me" in schema["paths"]
    assert "/api/v1/admin/locations" in schema["paths"]
    assert "/api/v1/admin/sessions" in schema["paths"]


def test_public_routes_are_read_only_and_admin_routes_mutate() -> None:
    schema = TestClient(app).get("/openapi.json").json()

    assert set(schema["paths"]["/api/v1/locations"]) == {"get"}
    assert set(schema["paths"]["/api/v1/locations/{locator}"]) == {"get"}
    assert set(schema["paths"]["/api/v1/sessions"]) == {"get"}
    assert set(schema["paths"]["/api/v1/sessions/{locator}"]) == {"get"}
    assert {"post"}.issubset(schema["paths"]["/api/v1/admin/locations"])
    assert {"post"}.issubset(schema["paths"]["/api/v1/admin/sessions"])


def test_admin_local_mode_stub() -> None:
    client = TestClient(app)

    unauthorized = client.get("/api/v1/admin/me")
    authorized = client.get("/api/v1/admin/me", headers={"X-ORNA-Admin": "local"})

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json() == {"id": "local-admin", "is_admin": True, "mode": "local"}


def test_public_schemas_do_not_expose_exact_coordinates_or_storage_keys() -> None:
    schema = TestClient(app).get("/openapi.json").json()

    location_fields = schema["components"]["schemas"]["LocationRead"]["properties"]
    media_fields = schema["components"]["schemas"]["MediaAssetRead"]["properties"]

    assert "exact_latitude" not in location_fields
    assert "exact_longitude" not in location_fields
    assert "latitude" in location_fields
    assert "longitude" in location_fields
    assert "storage_key" not in media_fields


@pytest.mark.parametrize(
    ("schema_class", "payload"),
    [
        (LocationUpdate, {"slug": None}),
        (LocationUpdate, {"metadata": None}),
        (SessionUpdate, {"slug": None}),
        (SessionUpdate, {"access_level": None}),
    ],
)
def test_patch_schemas_reject_nulls_for_required_columns(schema_class: type, payload: dict) -> None:
    with pytest.raises(ValidationError):
        schema_class.model_validate(payload)
