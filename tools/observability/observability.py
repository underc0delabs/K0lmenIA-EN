#!/usr/bin/env python3
"""
Read-only, dependency-free survey (urllib + stdlib regex) of a service's observability:
healthchecks and the Prometheus-style metrics endpoint.

Usage (from the repo root):
    python tools/observability/observability.py --url https://my-service
        [--health /health] [--metrics /metrics] [--expected http_requests_total,http_request_duration_seconds]
        [--output output/observability/svc.json]

What it does (GET only):
- Queries the healthcheck(s) (liveness/readiness) and reports their status and response time.
- Fetches the metrics endpoint (Prometheus/OpenMetrics text format), lists the metrics with their TYPE and
  HELP, and checks which of the expected ones are missing.

It does not generate load (for that, performance-mapper). The observability-analyst agent validates
logs/traces and that alerts fire using this input, the logs (log-analyst) and the database/APM.
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

UA = "k0lmenIA-QA/1.0 (read-only observability)"


def parse_prometheus(text):
    """Metrics from a Prometheus-style endpoint. Returns {name: {type, help}}. Pure and testable."""
    metrics = {}
    types, helps = {}, {}
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith("# TYPE "):
            parts = line[len("# TYPE "):].split()
            if len(parts) >= 2:
                types[parts[0]] = parts[1]
        elif line.startswith("# HELP "):
            parts = line[len("# HELP "):].split(maxsplit=1)
            if parts:
                helps[parts[0]] = parts[1] if len(parts) > 1 else ""
        elif line and not line.startswith("#"):
            m = re.match(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)", line)
            if m:
                name = m.group(1)
                base = re.sub(r"_(bucket|sum|count)$", "", name)
                for n in {name, base}:
                    metrics.setdefault(n, {"type": types.get(n), "help": helps.get(n)})
    # fill in known type/help
    for n, v in metrics.items():
        v["type"] = v["type"] or types.get(n)
        v["help"] = v["help"] or helps.get(n)
    return metrics


def missing(metrics, expected):
    """Expected metrics that are not present. Pure and testable."""
    present = set(metrics or {})
    return [e for e in expected or [] if e and e not in present]


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read(3 * 1024 * 1024).decode(r.headers.get_content_charset() or "utf-8", "replace")
            return r.status, txt, int((time.monotonic() - t0) * 1000), None
    except urllib.error.HTTPError as ex:
        return ex.code, "", int((time.monotonic() - t0) * 1000), None
    except Exception as ex:
        return 0, "", int((time.monotonic() - t0) * 1000), f"{type(ex).__name__}: {ex}"


def survey(base, health, metrics, expected):
    base = base.rstrip("/")
    inv = {"url": base, "health": [], "metrics": {}, "errors": {}}
    for path in [p for p in (health or "").split(",") if p.strip()]:
        st, _, ms, err = _get(base + path)
        inv["health"].append({"path": path, "status": st, "ok": bool(st and 200 <= st < 300), "ms": ms, "error": err})
    st, txt, ms, err = _get(base + metrics)
    if err or not (st and 200 <= st < 300):
        inv["errors"]["metrics"] = err or f"HTTP {st} on {metrics}"
    else:
        inv["metrics"] = parse_prometheus(txt)
    inv["missing"] = missing(inv["metrics"], expected)
    inv["summary"] = {"health_ok": all(h["ok"] for h in inv["health"]) if inv["health"] else None,
                      "metrics": len(inv["metrics"]), "missing": len(inv["missing"])}
    return inv


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Observability survey (healthchecks and metrics), read-only.")
    ap.add_argument("--url", required=True, help="service base URL")
    ap.add_argument("--health", default="/health,/healthz,/readyz", help="comma-separated healthcheck paths")
    ap.add_argument("--metrics", default="/metrics", help="path of the metrics endpoint (Prometheus)")
    ap.add_argument("--expected", default="", help="comma-separated metrics that must exist")
    ap.add_argument("--output", default="")
    args = ap.parse_args(argv)
    inv = survey(args.url, args.health, args.metrics, [m.strip() for m in args.expected.split(",") if m.strip()])
    text = json.dumps(inv, ensure_ascii=False, indent=2)
    if args.output:
        p = Path(args.output)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        print(f"[observability] Data in {p}", file=sys.stderr)
    print(text)
    r = inv["summary"]
    print(f"[observability] health_ok={r['health_ok']} metrics={r['metrics']} missing={r['missing']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
