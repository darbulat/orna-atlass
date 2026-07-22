from fastapi.testclient import TestClient
import pytest

from orna_atlas.app.main import app


@pytest.mark.parametrize(
    ("name", "placement"),
    [
        ("globe_view", "globe"),
        ("session_preview_start", "session_overlay"),
        ("session_preview_second", "session_overlay"),
        ("locked_point_hit", "globe_marker"),
        ("paywall_shown", "soft_paywall"),
        ("signup_started", "membership_form"),
        ("signup_completed", "membership_form"),
        ("member_session_play", "session_overlay"),
        ("subscription_intent", "membership_form"),
        ("marker_click", "globe_marker"),
        ("card_inline_play", "popular_locations"),
        ("favorite_requires_login", "session_overlay"),
        ("timeline_species_click", "session_overlay"),
    ],
)
def test_required_ux_funnel_events_are_bounded(name: str, placement: str) -> None:
    response = TestClient(app).post(
        "/api/v1/analytics/events",
        json={"name": name, "placement": placement},
    )

    assert response.status_code == 202
    assert response.json() == {"accepted": True}


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
