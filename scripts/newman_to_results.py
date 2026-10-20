#!/usr/bin/env python3
"""
Converts the JSON that Newman exports (--reporter-json-export) to the results
format that scripts/generate_report.py consumes. That way API runs
reuse the same HTML report (dashboard, dark mode) as the E2E runs.

Usage:
    python scripts/newman_to_results.py <newman.json> <results-output.json> [title]

How it maps each executed request to a "case":
  - With asserts and none failed      -> Passed.
  - With at least one failed assert   -> Failed (reason = first assert that failed).
  - Without any pm.test               -> Blocked (reason = "No validations (pm.test)"): nothing was verified.
  - The request could not be made     -> Blocked (reason = network/connection error).

The id and priority can (optionally) be encoded in the request NAME in Postman:
    "API-001 — Create post (High)"
  - id: a CODE-XXX style prefix followed by — · - or :
  - priority: Critical | High | Medium | Low, in parentheses at the end
If the name does not include them, the id is auto-numbered (API-001, API-002, …) and the
priority is left empty.

Missing information: if the request depends on missing data, put its ID in the name
("TC-API-003 — Create user [MI-01]"): the case is flagged with that MI in the report.
The duration of each case is the response time of the request.

GraphQL: if the request uses Postman's GraphQL mode (or sends a JSON body with "query"), the title
adds the operation ("[GraphQL query Country]") to tell apart requests that all go to the same endpoint.
"""
import sys
import json
import re
from datetime import datetime

PRIO_CANON = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low"}


def parse_name(name):
    """Returns (id, title, priority) from the request name."""
    title = (name or "").strip()
    priority = ""
    m = re.search(r"\(([^)]+)\)\s*$", title)
    if m and m.group(1).strip().lower() in PRIO_CANON:
        priority = PRIO_CANON[m.group(1).strip().lower()]
        title = title[:m.start()].strip()
    idv = ""
    m = re.match(r"^([A-Za-z]+-[A-Za-z0-9-]+)\s*[—\-:·]\s*(.+)$", title)
    if m:
        idv, title = m.group(1).strip(), m.group(2).strip()
    return idv, title, priority


def find_base_url(nm):
    """Looks for a base_url variable in the environment or in the collection."""
    for cont in (nm.get("environment") or {}, nm.get("collection") or {}):
        for v in (cont.get("values") or cont.get("variable") or []):
            if (v.get("key") or "").lower() in ("base_url", "baseurl", "url"):
                return v.get("value") or ""
    return ""


def fmt_request_error(err):
    """Turns Newman's request error into readable text."""
    if isinstance(err, dict):
        if err.get("message"):
            return err["message"]
        code = err.get("code") or err.get("name") or "Connection error"
        addr, port = err.get("address") or "", err.get("port")
        loc = f"{addr}:{port}" if addr and port else (addr or "")
        return " ".join(p for p in [code, err.get("syscall") or "", loc] if p).strip()
    return str(err)


def graphql_operation(ex):
    """'query Country' / 'mutation CreatePost' / 'query (anonymous)' if the request is GraphQL; otherwise ''."""
    for source in (ex.get("request"), (ex.get("item") or {}).get("request")):
        body = (source or {}).get("body") or {}
        query = None
        if body.get("mode") == "graphql":
            query = (body.get("graphql") or {}).get("query")
        elif body.get("mode") == "raw" and '"query"' in (body.get("raw") or ""):
            try:
                query = json.loads(body["raw"]).get("query")
            except (ValueError, AttributeError):
                query = None
        if query:
            m = re.match(r"\s*(query|mutation|subscription)\b\s*([A-Za-z_]\w*)?", query)
            if m:
                return f"{m.group(1)} {m.group(2) or '(anonymous)'}"
            return "query (anonymous)"  # short form: { field { ... } }
    return ""


def convert(nm, title_arg=""):
    run = nm.get("run") or {}
    cases = []
    for i, ex in enumerate(run.get("executions", []), start=1):
        name = (ex.get("item") or {}).get("name") or f"Request {i}"
        missing = re.findall(r"MI-\d+", name, re.I)
        name = re.sub(r"\s*[\[(@]?MI-\d+[\])]?", "", name, flags=re.I).strip()
        idv, title, priority = parse_name(name)
        if not idv:
            idv = f"API-{i:03d}"
        operation = graphql_operation(ex)
        if operation and operation.split()[-1] not in title:
            title = f"{title} [GraphQL {operation}]"

        if ex.get("requestError"):
            status, reason = "Blocked", fmt_request_error(ex.get("requestError"))
        elif not ex.get("assertions"):  # without pm.test nothing was verified: it cannot be Passed
            status, reason = "Blocked", "No validations (pm.test)"
        else:
            failed = [a for a in (ex.get("assertions") or []) if a.get("error")]
            if failed:
                err = failed[0].get("error") or {}
                detail = err.get("message") or err.get("name") or ""
                reason = f'{failed[0].get("assertion", "")}: {detail}'.strip(": ").strip()
                status = "Failed"
            else:
                status, reason = "Passed", ""

        elapsed = (ex.get("response") or {}).get("responseTime")
        case = {"id": idv, "title": title, "priority": priority, "status": status, "reason": reason}
        if isinstance(elapsed, (int, float)):
            case["duration_s"] = round(elapsed / 1000, 3)
        if missing:
            case["missing_info"] = [f.upper() for f in missing]
        cases.append(case)

    info = (nm.get("collection") or {}).get("info") or {}
    started = (run.get("timings") or {}).get("started")
    date = (datetime.fromtimestamp(started / 1000) if started else datetime.now()
            ).strftime("%Y-%m-%d %H:%M")

    return {
        "title": title_arg or info.get("name") or "API run",
        "date": date,
        "mode": "API (Newman)",
        "url": find_base_url(nm),
        "cases": cases,
    }


def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/newman_to_results.py <newman.json> <output.json> [title]")
        sys.exit(1)
    source, output = sys.argv[1], sys.argv[2]
    title_arg = sys.argv[3] if len(sys.argv) > 3 else ""

    with open(source, encoding="utf-8") as f:
        nm = json.load(f)
    out = convert(nm, title_arg)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"OK: {output} ({len(out['cases'])} cases)")


if __name__ == "__main__":
    main()
