"""
ALIS Prometheus Metrics Registry

Centralises all application-level Prometheus metric objects.
Imported by main.py (for /metrics endpoint) and domain_events.py / tasks.
Safe to import anywhere — fails open if prometheus_client is not installed.
"""

try:
    from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST  # noqa: F401

    HTTP_REQUESTS_TOTAL = Counter(
        "alis_http_requests_total",
        "Total HTTP requests",
        ["method", "path", "status_code"],
    )
    HTTP_REQUEST_DURATION = Histogram(
        "alis_http_request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "path"],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
    )
    ACTIVE_REQUESTS = Gauge("alis_active_requests", "Number of in-flight HTTP requests")
    DOMAIN_EVENTS_PUBLISHED = Counter(
        "alis_domain_events_published_total",
        "Domain events published",
        ["event_type"],
    )
    DOMAIN_EVENTS_PROCESSED = Counter(
        "alis_domain_events_processed_total",
        "Domain events processed by the event bus",
        ["event_type", "status"],
    )
    CELERY_TASK_DURATION = Histogram(
        "alis_celery_task_duration_seconds",
        "Celery task duration in seconds",
        ["task_name"],
    )
    AVAILABLE = True

except ImportError:
    HTTP_REQUESTS_TOTAL = None  # type: ignore[assignment]
    HTTP_REQUEST_DURATION = None  # type: ignore[assignment]
    ACTIVE_REQUESTS = None  # type: ignore[assignment]
    DOMAIN_EVENTS_PUBLISHED = None  # type: ignore[assignment]
    DOMAIN_EVENTS_PROCESSED = None  # type: ignore[assignment]
    CELERY_TASK_DURATION = None  # type: ignore[assignment]
    generate_latest = None  # type: ignore[assignment]
    CONTENT_TYPE_LATEST = "text/plain"
    AVAILABLE = False
