import json
import logging
import os
from pathlib import Path
import subprocess
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

from orna_atlas.app.core.logging import JsonFormatter, RequestLoggingMiddleware
from orna_atlas.app.core.metrics import metrics_response
from orna_atlas.app.main import app as atlas_app


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


def test_request_middleware_logs_route_template_without_hls_token(caplog) -> None:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/media/hls/{asset_id}/{token}/{object_name:path}")
    async def hls_probe(asset_id: str, token: str, object_name: str) -> dict[str, str]:
        return {"asset_id": asset_id, "token": token, "object_name": object_name}

    canary = "canary-secret-playback-token"
    with caplog.at_level(logging.INFO, logger="orna_atlas.request"):
        response = TestClient(app).get(
            f"/media/hls/asset-1/{canary}/segments/segment-1.m4s"
        )

    assert response.status_code == 200
    record = next(item for item in caplog.records if item.message == "request_complete")
    assert record.path == "/media/hls/{asset_id}/{token}/{object_name:path}"
    assert canary not in record.getMessage()
    assert canary not in json.dumps(record.__dict__, default=str)


def test_nginx_access_log_redacts_hls_token_paths() -> None:
    config = Path("deploy/nginx.conf.template").read_text()
    log_format = config.split("log_format orna_access", 1)[1].split(";", 1)[0]

    assert "~^/api/v1/media/hls/ /api/v1/media/hls/[REDACTED]" in config
    assert config.count("access_log /var/log/nginx/access.log orna_access;") == 2
    assert "$orna_log_path" in log_format
    assert "$request " not in log_format
    assert "$request_uri" not in log_format
    assert "$http_" not in log_format


def test_api_image_disables_uvicorn_access_log() -> None:
    dockerfile = Path("Dockerfile.api").read_text()

    assert '"--no-access-log"' in dockerfile


def test_https_compose_mounts_token_safe_nginx_config() -> None:
    compose = Path("docker-compose.https.yml").read_text()

    assert "ports: !override []" in compose
    assert "./deploy/nginx.conf.template:/etc/nginx/templates/default.conf.template:ro" in compose


def test_metrics_endpoint_exposes_prometheus_payload() -> None:
    response = TestClient(atlas_app).get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "orna_http_requests_total" in response.text


def test_unmatched_paths_share_one_bounded_metrics_label() -> None:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)
    client = TestClient(app)

    assert client.get("/missing-one-unique").status_code == 404
    assert client.get("/missing-two-unique").status_code == 404

    payload = metrics_response().body.decode()
    assert 'route="__unmatched__"' in payload
    assert "missing-one-unique" not in payload
    assert "missing-two-unique" not in payload


def test_worker_metrics_aggregate_forked_processes(tmp_path: Path) -> None:
    environment = {
        **os.environ,
        "PROMETHEUS_MULTIPROC_DIR": str(tmp_path),
    }
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from orna_atlas.app.core.metrics import PIPELINE_JOBS; "
                "PIPELINE_JOBS.labels('succeeded').inc()"
            ),
        ],
        check=True,
        env=environment,
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from orna_atlas.app.core.metrics import metrics_response; "
                "print(metrics_response().body.decode())"
            ),
        ],
        check=True,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert 'orna_pipeline_jobs_total{status="succeeded"} 1.0' in result.stdout
