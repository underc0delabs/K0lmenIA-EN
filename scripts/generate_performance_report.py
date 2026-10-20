#!/usr/bin/env python3
"""
Generates the Performance report in HTML (dashboard, dark mode) from a JSON.

Usage:
    python scripts/generate_performance_report.py <report.json> <output.html>

The METRICS are not written by hand: they come from the JSON summaries left by each run of
`npm run perf` (tools/k0lmena/reports/performance/<tool>/<script>-<profile>-<date>.json).
The input JSON provides the plan agreed with the person and the analysis:

{
  "title": "Performance report — Login",
  "story": "US-001",
  "date": "2026-10-09",
  "verdict": "Pass with observations",          // conclusion of the analysis
  "verdict_tone": "warn",                       // optional: ok | warn | bad (otherwise it is inferred)
  "summary": "Executive summary...",
  "plan": {
    "objective": "Validate that the login supports the 9 a.m. peak",
    "types": ["load", "stress"],
    "tool": "k6",
    "tool_reason": "HTTP APIs; scales with little hardware",
    "environment": "https://staging.example.com",
    "scope": ["POST /login (70 %)", "GET /profile (30 %)"],
    "load": {"Concurrent users": "50", "Ramp": "1 min", "Duration": "5 min"},
    "thresholds": {"p95": "< 500 ms", "Errors": "< 1 %"},
    "assumptions": ["Think time of 1 s (suggested and accepted)"]
  },
  "runs": [                                       // JSON summary of each run (path or {summary, label})
    {"summary": "tools/k0lmena/reports/performance/k6/US-001-login-load-20261009-101500.json",
     "label": "Load · 50 users"}
  ],
  "capacity": "Up to 100 users with p95 < 500 ms; at 150 it degrades.",   // optional
  "findings": [{"title": "...", "detail": "...", "severity": "High"}],
  "recommendations": [{"action": "...", "reason": "...", "priority": "High"}],
  "missing_info": [{"id": "MI-01", "what_is_missing": "...", "impact": "...", "question": "...", "status": "Open"}],
  "next_steps": ["..."]
}

Severity / priority: Critical | High | Medium | Low.
The HTML is self-contained (inline CSS and SVG), it does not use the internet.
"""
import json
import os
import sys
from pathlib import Path

from _report_styles import (e, page, meta, section, kpi_tiles, banner, doc_list, table,
                            level_badge, two_col, grouped_columns, line_chart, SERIES, CRITICAL)

CSS_EXTRA = """
<style>
.ok-t{color:#7BD36A;font-weight:600}.bad-t{color:#FF8F85;font-weight:600}.warn-t{color:#FFE066;font-weight:600}
.ok-t::before{content:"✓ "}.bad-t::before{content:"✕ "}.warn-t::before{content:"! "}
.plan dl{display:grid;grid-template-columns:190px 1fr;gap:9px 16px}
.plan dt{color:var(--muted);font-size:13px}.plan dd{color:var(--ink)}
@media (max-width:720px){.plan dl{grid-template-columns:1fr}}
</style>
"""


# ------------------------------------------------------------------ utilities
def ms(x):
    if x is None:
        return "—"
    return f"{x / 1000:.2f} s" if x >= 1000 else f"{x:.0f} ms"


def num(x, dec=2):
    return "—" if x is None else (f"{x:,.0f}" if dec == 0 else f"{x:.{dec}f}")


def duration(sec):
    if sec is None:
        return "—"
    m, s = divmod(round(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m" if h else (f"{m}m {s}s" if m else f"{s}s")


def tone_for_verdict(text):
    low = (text or "").lower()
    if "fail" in low or "not met" in low or "no-go" in low or "does not" in low:
        return "bad"
    if "observ" in low or "risk" in low or "condition" in low or "partial" in low or "remark" in low:
        return "warn"
    return "ok" if ("pass" in low or "meets" in low or " met" in f" {low}" or "go" in low) else "warn"


RUN_VERDICT = {"pass": ("Pass", "ok-t"), "fail": ("Fail", "bad-t"),
               "no thresholds": ("No thresholds", "warn-t"), "error": ("Error", "bad-t")}


def load_runs(entries, base_html):
    runs = []
    for entry in entries:
        path = entry.get("summary") if isinstance(entry, dict) else entry
        label = entry.get("label") if isinstance(entry, dict) else None
        if not os.path.exists(path):
            sys.exit(f"[!] I cannot find the run summary: {path}")
        with open(path, encoding="utf-8") as f:
            r = json.load(f)
        run_html = (r.get("files") or {}).get("html") or path[:-5] + ".html"
        r["_link"] = None
        if os.path.exists(run_html):
            try:
                r["_link"] = os.path.relpath(run_html, base_html).replace(os.sep, "/")
            except ValueError:  # on another drive (Windows): absolute link
                r["_link"] = Path(os.path.abspath(run_html)).as_uri()
        users = (r.get("kpis") or {}).get("max_users")
        r["_name"] = label or (f'{r.get("profile", "?")} · {users:.0f} user{"" if users == 1 else "s"}' if users else r.get("profile", "?"))
        runs.append(r)
    # If two runs end up with the same name, they are numbered.
    seen = {}
    for c in runs:
        seen[c["_name"]] = seen.get(c["_name"], 0) + 1
    counter = {}
    for c in runs:
        if seen[c["_name"]] > 1:
            counter[c["_name"]] = counter.get(c["_name"], 0) + 1
            c["_name"] = f'{c["_name"]} (#{counter[c["_name"]]})'
    return runs


# ------------------------------------------------------------------ evolution over time
def evolution(runs, key, fmt):
    """One line per run over the time relative to its start (seconds), on a single axis."""
    series, times = [], set()
    for i, c in enumerate(runs):
        pts = [p for p in c.get("timeline") or [] if p.get(key) is not None]
        if len(pts) < 2:
            continue
        t0 = pts[0]["t"]
        data = {round((p["t"] - t0) / 1000): p[key] for p in pts}
        times.update(data)
        series.append((c["_name"], SERIES[i % len(SERIES)], data))
    if not series:
        return '<p class="muted">No evolution over time: k6 only delivers the final summary, or the runs lasted less than two 10 s intervals.</p>'
    x = sorted(times)
    return line_chart(x, [(n, col, [d.get(s) for s in x]) for n, col, d in series], fmt=fmt,
                      fmt_x=lambda s: duration(s), area=len(series) == 1)


# ------------------------------------------------------------------ build
def build_html(data, runs):
    body = []
    if data.get("verdict"):
        body.append(banner(data["verdict"], data.get("verdict_tone") or tone_for_verdict(data["verdict"])))

    # KPIs of the whole set
    reqs = sum((c.get("kpis") or {}).get("requests") or 0 for c in runs)
    p95s = [(c.get("latency") or {}).get("p95") for c in runs if (c.get("latency") or {}).get("p95") is not None]
    errs = [(c.get("kpis") or {}).get("error_pct") for c in runs if (c.get("kpis") or {}).get("error_pct") is not None]
    passing = sum(1 for c in runs if c.get("verdict") == "pass")
    rps_max = max(((c.get("kpis") or {}).get("rps") or 0) for c in runs)
    max_users = max(((c.get("kpis") or {}).get("max_users") or 0) for c in runs)
    row1 = kpi_tiles([
        ("Runs", len(runs), ""),
        ("Meet thresholds", f"{passing}/{len(runs)}", "ok" if passing == len(runs) else "bad", "", "", {"pct": passing / len(runs) * 100 if runs else 0}),
        ("Worst p95", ms(max(p95s)) if p95s else "—", ""),
        ("Worst error %", f"{max(errs):.2f} %" if errs else "—", "bad" if errs and max(errs) > 0 else "ok"),
    ])
    row2 = kpi_tiles([
        ("Total requests", num(reqs, 0), ""),
        ("Max req/s", num(rps_max), ""),
        ("Max users", num(max_users, 0), ""),
        ("Total duration", duration(sum(c.get("duration_s") or 0 for c in runs)), ""),
    ])
    body.append(f'<div style="margin-top:20px">{row1}</div><div style="margin-top:12px">{row2}</div>')

    if data.get("summary"):
        body.append(section("Executive summary", f'<div class="cardbody"><p class="lead">{e(data["summary"])}</p></div>'))
    if data.get("capacity"):
        body.append(section("Observed capacity", f'<div class="cardbody"><p class="lead">{e(data["capacity"])}</p></div>'))

    # Agreed plan
    plan = data.get("plan") or {}
    if plan:
        rows = []
        for label, key in [("Objective", "objective"), ("Test types", "types"), ("Tool", "tool"),
                           ("Why that tool", "tool_reason"), ("Environment", "environment"), ("Scope", "scope")]:
            v = plan.get(key)
            if v:
                rows.append((label, ", ".join(v) if isinstance(v, list) else v))
        for group in ("load", "thresholds"):
            for k, v in (plan.get(group) or {}).items():
                rows.append((f'{"Load" if group == "load" else "Threshold"} · {k}', v))
        dl = "".join(f"<dt>{e(k)}</dt><dd>{e(v)}</dd>" for k, v in rows)
        assumptions = plan.get("assumptions") or []
        extra = (f'<div class="subhead" style="margin-top:16px">Assumptions and accepted suggestions</div>'
                 f'<ul class="doclist">{"".join(f"<li>{e(s)}</li>" for s in assumptions)}</ul>') if assumptions else ""
        body.append(section("Agreed plan", f'<div class="cardbody plan"><dl>{dl}</dl>{extra}</div>'))

    # Results per run
    rows = []
    for c in runs:
        k, l = c.get("kpis") or {}, c.get("latency") or {}
        ver, cls = RUN_VERDICT.get(c.get("verdict"), (c.get("verdict") or "—", ""))
        name = f'<a href="{e(c["_link"])}" style="color:var(--ink)">{e(c["_name"])}</a>' if c["_link"] else e(c["_name"])
        rows.append([name, num(k.get("max_users"), 0), duration(c.get("duration_s")), num(k.get("requests"), 0),
                     num(k.get("rps")), f'{num(k.get("error_pct"))} %', ms(l.get("p50")), ms(l.get("p95")), ms(l.get("p99")),
                     f'<span class="{cls}">{e(ver)}</span>'])
    body.append(section("Results per run", table(
        ["Run", "Users", "Duration", "Requests", "Req/s", "Errors", "p50", "p95", "p99", "Verdict"], rows)))

    # Comparison charts
    groups = [c["_name"] for c in runs]
    lat = grouped_columns(groups, [
        ("p50", SERIES[1], [(c.get("latency") or {}).get("p50") for c in runs]),
        ("p95", SERIES[3], [(c.get("latency") or {}).get("p95") for c in runs]),
        ("p99", SERIES[2], [(c.get("latency") or {}).get("p99") for c in runs]),
    ], fmt=ms)
    body.append(section("Latency per run", lat, "response time percentiles"))
    thr = grouped_columns(groups, [("Req/s", SERIES[0], [(c.get("kpis") or {}).get("rps") for c in runs])], height=260, width=660)
    err = grouped_columns(groups, [("Error %", CRITICAL, [(c.get("kpis") or {}).get("error_pct") for c in runs])],
                          fmt=lambda v: f"{v:.2f}".rstrip("0").rstrip(".") + " %", height=260, width=660)
    body.append(two_col(section("Throughput", thr, "requests per second"), section("Errors", err, "% of failed requests")))

    # Evolution over time: one chart per metric (never two scales in the same chart)
    body.append(section("Throughput evolution", f'<div class="chart">{evolution(runs, "rps", lambda v: f"{v:.0f}" if v >= 10 else f"{v:.1f}" if v >= 1 else f"{v:.2f}")}</div>',
                        "req/s per 10 s interval, from the start of each run"))
    body.append(section("p95 evolution", f'<div class="chart">{evolution(runs, "p95", ms)}</div>',
                        "p95 per 10 s interval, from the start of each run"))

    # Thresholds
    rows = []
    for c in runs:
        for u in c.get("thresholds") or []:
            rows.append([e(c["_name"]), f'<span class="mono">{e(u.get("metric"))}</span>', e(u.get("condition")),
                         e(u.get("value")), '<span class="ok-t">Pass</span>' if u.get("ok") else '<span class="bad-t">Fail</span>'])
    if rows:
        body.append(section("Thresholds", table(["Run", "Metric", "Condition", "Measured", "Result"], rows)))

    # Endpoints / steps: p95 of each one in each run
    names = []
    for c in runs:
        for f in (c.get("detail") or {}).get("rows") or []:
            if f.get("name") not in names:
                names.append(f.get("name"))
    if names:
        idx = [{f.get("name"): f for f in (c.get("detail") or {}).get("rows") or []} for c in runs]
        rows = [[f'<span class="mono">{e(n)}</span>'] + [ms((i.get(n) or {}).get("p95")) for i in idx] for n in names]
        body.append(section("p95 per endpoint or step", table(["Endpoint / step"] + groups, rows)))

    # Errors
    errors = {}
    for c in runs:
        for reason, n in (c.get("errors") or {}).items():
            errors[reason] = errors.get(reason, 0) + n
    if errors:
        rows = [[e(m), f'<span class="bad-t">{num(n, 0)}</span>'] for m, n in sorted(errors.items(), key=lambda x: -x[1])[:15]]
        body.append(section("Most frequent errors", table(["Error", "Count"], rows)))

    # Analysis
    if data.get("findings"):
        rows = [[f'<strong style="color:var(--ink)">{e(h.get("title"))}</strong>', e(h.get("detail")), level_badge(h.get("severity"))]
                for h in data["findings"]]
        body.append(section("Findings and bottlenecks", table(["Finding", "Detail", "Severity"], rows)))
    if data.get("recommendations"):
        rows = [[f'<strong style="color:var(--ink)">{e(r.get("action"))}</strong>', e(r.get("reason")), level_badge(r.get("priority"))]
                for r in data["recommendations"]]
        body.append(section("Recommendations", table(["Action", "Why", "Priority"], rows)))

    missing = data.get("missing_info") or []
    if missing:
        items = [f'{f.get("id", "")} — {f.get("what_is_missing") or f.get("description", "")}' + (f' (impact: {f["impact"]})' if f.get("impact") else "")
                 + (f' · Question: {f["question"]}' if f.get("question") else "") + f' · {f.get("status", "Open")}' for f in missing]
        body.append(section("Missing information", doc_list(items)))
    if data.get("next_steps"):
        body.append(section("Next steps", doc_list(data["next_steps"])))

    meta_html = meta([("Story", data.get("story")), ("Date", data.get("date")),
                      ("Tool", plan.get("tool")), ("Environment", plan.get("environment"))])
    return page(data.get("title") or "Performance report", "Performance report", meta_html,
                CSS_EXTRA + "".join(body))


def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/generate_performance_report.py <report.json> <output.html>")
        sys.exit(1)
    source, output = sys.argv[1], sys.argv[2]
    if not output.lower().endswith(".html"):
        sys.exit("The output must end in .html")
    with open(source, encoding="utf-8") as f:
        data = json.load(f)
    if not data.get("runs"):
        sys.exit("[!] The report needs at least one run in \"runs\" (JSON summary from npm run perf).")
    runs = load_runs(data["runs"], os.path.dirname(os.path.abspath(output)))
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        f.write(build_html(data, runs))
    print(f"OK: {output}")


if __name__ == "__main__":
    main()
