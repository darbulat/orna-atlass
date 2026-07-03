from fastapi.testclient import TestClient

from orna_atlas.app.main import app


def test_sprint2_routes_are_registered() -> None:
    schema = TestClient(app).get("/openapi.json").json()

    assert "/api/v1/locations" in schema["paths"]
    assert "/api/v1/sessions" in schema["paths"]
    assert "/api/v1/admin/me" in schema["paths"]


def test_admin_local_mode_stub() -> None:
    client = TestClient(app)

    unauthorized = client.get("/api/v1/admin/me")
    authorized = client.get("/api/v1/admin/me", headers={"X-ORNA-Admin": "local"})

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json() == {"id": "local-admin", "is_admin": True, "mode": "local"}
