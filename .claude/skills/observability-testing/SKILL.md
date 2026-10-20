---
name: observability-testing
description: How to test a service's observability — that it properly emits the three pillars (logs, metrics and traces) and everything related — structured logs (JSON format, correct levels, correlation with trace/request id, no PII or secrets, no stack traces dumped to the user), Prometheus/OpenMetrics-style metrics (the expected ones exist, RED method —rate/errors/duration— and USE, consistent names and labels, cardinality under control, counters that go up), distributed traces (OpenTelemetry — spans with name and attributes, context propagation between services —traceparent—, sampling, per-span latency), healthchecks (liveness vs. readiness, /health and /metrics, readiness reflecting dependencies that are down), error tracking (Sentry or another — the error arrives with stack, user and release), SLIs/SLOs and alerts (an alert fires when the threshold is violated and resolves when things normalize), dashboards, telemetry retention and cost; how to automate (healthchecks and /metrics with the observability tool, generate traffic and verify in Prometheus/Grafana/Loki/Jaeger or in the logs), typical bugs and questions for the team. Used by the observability-analyst; relies on the log-analyst and synthetic monitoring.
---

# Observability testing

A system is observable if, when something fails in production, **you can understand what happened** from the outside: through its **logs, metrics and traces**. Here you validate that the app **properly emits** those signals (not that the features work), plus the healthchecks and the alerts. It complements `log-analyst` (log analysis) and synthetic monitoring (`npm run monitor`).

## 1. Logs (structured logging)

- **Structured format** (JSON), not loose text; with the correct **level** (error/warn/info/debug) and a timestamp.
- **Correlation**: every log of a request carries a **request id / trace id** that lets you follow the whole flow.
- **No PII or secrets** in the logs (tokens, cards, passwords, personal data) — it's the most common and most serious finding.
- An error is logged **once**, with useful context (not 50 lines of noise, nor a stack trace shown to the user).

## 2. Metrics (Prometheus/OpenMetrics)

- The **expected metrics** exist (the `npm run observability` tool lists them and flags the missing ones).
- **RED** for services (Rate, Errors, Duration) and **USE** for resources (Utilization, Saturation, Errors).
- Consistent, meaningful **names and labels**; controlled **cardinality** (a label with the user id blows up the metric).
- **Counters** go up under real traffic; latency **histograms** have reasonable buckets.

## 3. Distributed traces (OpenTelemetry)

- Each operation generates **spans** with a name and attributes; the **context propagates** between services (`traceparent` header), so a request can be seen end to end.
- **Sampling** configured (not 100% in prod unless appropriate); per-span latency helps find the bottleneck.
- A call to a dependency (DB, API) shows up as a child span.

## 4. Healthchecks

- **Liveness** (is the process alive?) vs. **readiness** (can it serve traffic?): they're different. Readiness must report **not-ready** if a critical dependency is down (overlaps with `resilience-tester`), so the load balancer takes it out of rotation.
- `/health`, `/healthz`, `/readyz` and `/metrics` respond quickly and without heavy authentication.

## 5. Error tracking

- Errors reach the tracker (Sentry, etc.) with **stack, request id, user and release/version**; without massive duplicates; with useful breadcrumbs.

## 6. SLIs / SLOs and alerts

- Define the **SLIs** (availability, p95/p99 latency, error rate) and verify that **alerts fire** when the threshold is violated and **resolve** when things normalize (test it by triggering the condition in QA, e.g. with `resilience-tester` chaos).
- Actionable alerts (no noise/fatigue): they should point to a runbook.

## 7. Automating

- `npm run observability` (`tools/observability/observability.py`) checks the healthchecks and `/metrics` (present/missing metrics) — read-only, no load.
- Generate traffic (with `api-runner` or Playwright) and **verify the signal**: in the observability backend (Prometheus/Grafana, Loki, Jaeger/Tempo, ELK) or in the logs (`log-analyst`); correlation by trace id.
- For load and seeing the behavior under stress, `performance-mapper`.

## 8. Typical observability bugs

- **PII or secrets in the logs**.
- Logs without a trace id → impossible to correlate a request across services.
- An expected metric that doesn't exist; a high-cardinality label (user/request id) that bloats the TSDB.
- Readiness that reports OK even though the database is down → the load balancer sends traffic to a pod that can't serve it.
- Trace context that **doesn't propagate** (each service starts its own trace).
- An alert that never fires (wrong threshold) or always fires (noise).
- A stack trace shown to the end user.

## 9. Typical questions for the team

When it isn't written down, they are `MI-XX`:

- Which observability stack do you use (Prometheus/Grafana, OTel, ELK, Datadog…)?
- Which metrics and SLOs are the official ones? What latency/error is acceptable?
- What should make readiness not-ready (which dependencies are critical)?
- What can be logged and what is forbidden (PII, secrets)?
- How are alerts tested in QA?
