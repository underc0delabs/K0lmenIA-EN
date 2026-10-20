# Observability

**Read-only** survey of a service's observability: healthchecks and Prometheus-style metrics. Used by the `observability-analyst` agent.

- **`observability.py`** (`npm run observability`) — queries the healthcheck(s) (liveness/readiness) and the `/metrics` endpoint (Prometheus/OpenMetrics format), lists the metrics with their TYPE/HELP and checks which of the expected ones are missing.

```bash
npm run observability -- --url https://my-service --expected http_requests_total,http_request_duration_seconds
```

GET only; it does not generate load (for that, `performance-mapper`). The `observability-analyst` validates logs and traces, and that alerts/SLOs fire, using this input, the logs (`log-analyst`) and the APM. No dependencies (stdlib urllib).
