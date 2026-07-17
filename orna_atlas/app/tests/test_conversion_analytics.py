from fastapi.testclient import TestClient

from orna_atlas.app.main import app


def test_conversion_event_accepts_bounded_non_personal_fields() -> None:
    response = TestClient(app).post(
        "/api/v1/analytics/events",
        json={"name": "registration_completed", "placement": "membership_form"},
    )

    assert response.status_code == 202
    assert response.json() == {"accepted": True}
    metrics = TestClient(app).get("/metrics").text
    assert 'orna_conversion_events_total{name="registration_completed",placement="membership_form"}' in metrics


def test_conversion_event_rejects_unknown_labels_and_extra_personal_data() -> None:
    client = TestClient(app)

    assert client.post(
        "/api/v1/analytics/events",
        json={"name": "arbitrary_event", "placement": "membership_form"},
    ).status_code == 422
    assert client.post(
        "/api/v1/analytics/events",
        json={
            "name": "registration_completed",
            "placement": "membership_form",
            "email": "listener@example.com",
        },
    ).status_code == 422
