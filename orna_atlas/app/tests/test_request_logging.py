import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from orna_atlas.app.core.logging import JsonFormatter, RequestLoggingMiddleware


def test_json_formatter_includes_structured_fields() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "completed", (), None)
    record.request_id = "request-1"
    payload = json.loads(formatter.format(record))
    assert payload["message"] == "completed"
    assert payload["request_id"] == "request-1"
    assert payload["level"] == "INFO"


def test_request_middleware_preserves_valid_correlation_id(caplog) -> None:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/probe")
    async def probe() -> dict[str, bool]:
        return {"ok": True}

    with caplog.at_level(logging.INFO, logger="orna_atlas.request"):
        response = TestClient(app).get("/probe", headers={"X-Request-ID": "trace-123"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "trace-123"
    record = next(item for item in caplog.records if item.message == "request_complete")
    assert record.request_id == "trace-123"
    assert record.status_code == 200
    assert record.duration_ms >= 0
