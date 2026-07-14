import os

from prometheus_client import (
    REGISTRY,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
    start_http_server,
)
from prometheus_client.exposition import CONTENT_TYPE_LATEST
from starlette.responses import Response

HTTP_REQUESTS = Counter(
    "orna_http_requests_total",
    "Completed HTTP requests",
    ("method", "route", "status"),
)
HTTP_DURATION = Histogram(
    "orna_http_request_duration_seconds",
    "HTTP request latency",
    ("method", "route"),
)
PIPELINE_JOBS = Counter(
    "orna_pipeline_jobs_total",
    "Audio pipeline job outcomes",
    ("status",),
)
PIPELINE_QUEUE_JOBS = Counter(
    "orna_pipeline_queue_operations_total",
    "Audio pipeline enqueue outcomes",
    ("status",),
)
PIPELINE_STAGE_DURATION = Histogram(
    "orna_pipeline_stage_duration_seconds",
    "Audio pipeline stage latency",
    ("stage", "status"),
)


def _collector_registry():
    if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return registry
    return REGISTRY


def metrics_response() -> Response:
    return Response(
        generate_latest(_collector_registry()),
        media_type=CONTENT_TYPE_LATEST,
    )


def start_metrics_http_server(port: int) -> None:
    """Expose the registry of a standalone worker process."""
    start_http_server(port, registry=_collector_registry())
