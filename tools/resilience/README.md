# Resilience (server-side chaos)

Injection of **real failures into the dependencies** of a service with **Toxiproxy**, to test how the system behaves when a database, an API or a cache becomes slow or goes down. It complements the `resilience-tester`, which simulates failures **on the browser side** (by intercepting requests); this is on the **server side**.

- **`toxiproxy.py`** (`npm run toxiproxy`) — talks to the Toxiproxy REST API (by default `http://localhost:8474`, or `TOXIPROXY_URL`) with the stdlib. It lists proxies and injects **latency**, **outage** (disables the proxy), **slowness** (bandwidth) and other toxics, and removes them (`recover`/`reset`).

```bash
npm run toxiproxy -- --action list
npm run toxiproxy -- --action latency --proxy db --ms 2000 --jitter 500
npm run toxiproxy -- --action down --proxy db        # cuts off the dependency
npm run toxiproxy -- --action recover --proxy db     # restores it
npm run toxiproxy -- --action reset                  # removes all toxics
```

How to use it: put **Toxiproxy between the service and its dependency** (the service points to the Toxiproxy port, and Toxiproxy forwards to the real dependency). Then inject the failure, observe how the service degrades (timeouts, retries, circuit breaker, fallback, clear message) and **run `reset` when you are done**.

`list` is **read-only**; injecting/removing failures **has side effects**, so the `resilience-tester` confirms it and runs it only in **QA**, never in production.

**Requirements**: **Toxiproxy** running (the `toxiproxy-server` binary or the `ghcr.io/shopify/toxiproxy` container) with the proxies configured toward the dependencies. The tool needs no extra libraries.
