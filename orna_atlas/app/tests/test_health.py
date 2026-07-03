from fastapi.testclient import TestClient

from orna_atlas.app.main import app


def test_openapi_is_available() -> None:
    response = TestClient(app).get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "ORNA Atlas API"
