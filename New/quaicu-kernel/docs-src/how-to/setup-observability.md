# Set Up Observability

!!! info "Coming soon"
    This guide covers OpenTelemetry configuration in `kernel.toml`, the metrics and traces the kernel emits, and how to connect to Grafana or Cloud Monitoring.

The kernel emits OpenTelemetry traces for every governance lifecycle phase (PROPOSE → SEAL), Prometheus metrics for decision rates and latency, and structured logs via Loki.
