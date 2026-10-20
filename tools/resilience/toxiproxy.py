#!/usr/bin/env python3
"""
Server-side chaos with Toxiproxy: injects real failures into a service's dependencies (latency, outage,
bandwidth, timeout) by placing Toxiproxy as a proxy between the service and its dependency (database, API, cache).
No dependencies: talks to the Toxiproxy REST API (by default http://localhost:8474) with urllib.

Usage (from the repo root, with Toxiproxy running and the proxies configured):
    python tools/resilience/toxiproxy.py --action list
    python tools/resilience/toxiproxy.py --action latency --proxy db --ms 2000 --jitter 500
    python tools/resilience/toxiproxy.py --action down --proxy db        # cuts off the dependency
    python tools/resilience/toxiproxy.py --action recover --proxy db     # restores it
    python tools/resilience/toxiproxy.py --action reset                  # removes all toxics

The actions that inject or remove failures (latency/down/slow/toxic/recover/reset) **have side effects** on
the environment: the resilience-tester agent confirms them and runs them only in QA. `list` is read-only.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request


def toxic_payload(kind, stream="downstream", attributes=None, toxicity=1.0, name=None):
    """Builds the body of a Toxiproxy toxic. Pure and testable."""
    return {"name": name or f"{kind}_{stream}", "type": kind, "stream": stream,
            "toxicity": toxicity, "attributes": attributes or {}}


def proxies_summary(proxies):
    """Testable summary: name, whether it is enabled and how many toxics each proxy has."""
    out = []
    for p in proxies or []:
        out.append({"name": p.get("name"), "enabled": p.get("enabled"),
                    "listen": p.get("listen"), "upstream": p.get("upstream"),
                    "toxics": len(p.get("toxics") or [])})
    return out


def _api(host, method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(host.rstrip("/") + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8", "replace")
            return json.loads(txt) if txt.strip() else {}, None
    except urllib.error.HTTPError as ex:
        return None, f"HTTP {ex.code}: {ex.read().decode('utf-8', 'replace')[:160]}"
    except Exception as ex:
        return None, f"{type(ex).__name__}: {ex} (is Toxiproxy running on {host}?)"


def list_proxies(host):
    d, err = _api(host, "GET", "/proxies")
    if err:
        return None, err
    return proxies_summary(list(d.values()) if isinstance(d, dict) else d), None


def add_toxic(host, proxy, kind, stream, attributes, toxicity=1.0):
    return _api(host, "POST", f"/proxies/{proxy}/toxics", toxic_payload(kind, stream, attributes, toxicity))


def enable(host, proxy, enabled):
    return _api(host, "POST", f"/proxies/{proxy}", {"enabled": enabled})


def reset(host):
    return _api(host, "POST", "/reset")


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Server-side chaos with Toxiproxy (latency, outage, slowness).")
    ap.add_argument("--host", default="http://localhost:8474", help="Toxiproxy API (or TOXIPROXY_URL)")
    ap.add_argument("--action", required=True, choices=["list", "latency", "down", "recover", "slow", "toxic", "reset"])
    ap.add_argument("--proxy", default="", help="proxy name (the dependency)")
    ap.add_argument("--ms", type=int, default=1000, help="latency in ms (latency action)")
    ap.add_argument("--jitter", type=int, default=0)
    ap.add_argument("--rate", type=int, default=100, help="bandwidth in KB/s (slow action)")
    ap.add_argument("--stream", default="downstream", choices=["downstream", "upstream"])
    ap.add_argument("--type", default="", help="toxic type (toxic action)")
    args = ap.parse_args(argv)

    import os
    host = os.environ.get("TOXIPROXY_URL") or args.host

    if args.action == "list":
        res, err = list_proxies(host)
    elif args.action == "latency":
        res, err = add_toxic(host, args.proxy, "latency", args.stream, {"latency": args.ms, "jitter": args.jitter})
    elif args.action == "down":
        res, err = enable(host, args.proxy, False)
    elif args.action == "recover":
        res, err = enable(host, args.proxy, True)
    elif args.action == "slow":
        res, err = add_toxic(host, args.proxy, "bandwidth", args.stream, {"rate": args.rate})
    elif args.action == "toxic":
        res, err = add_toxic(host, args.proxy, args.type, args.stream, {})
    elif args.action == "reset":
        res, err = reset(host)
    else:
        res, err = None, "unsupported action"

    if err:
        print(f"[toxiproxy] {err}", file=sys.stderr)
        return 2
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print(f"[toxiproxy] {args.action} ok" + (f" (proxy {args.proxy})" if args.proxy else ""), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
