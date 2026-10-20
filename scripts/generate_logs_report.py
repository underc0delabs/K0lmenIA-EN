#!/usr/bin/env python3
"""
Generates the Logs report in HTML (dashboard, dark mode) from logs.json (scripts/analyze_logs.py)
and, optionally, from the log-analyst agent's analysis.

Usage:
    python scripts/generate_logs_report.py <logs.json> <output.html> [--analysis analysis.json]

What it shows: verdict, indicators (lines, errors, warnings, signatures, failed scenarios with server
errors), errors and warnings per minute, the most repeated signatures, each failed scenario with the
errors that happened while it ran, the signatures table with its example and stack trace, and the evolution.

The analysis (optional) provides:
{
  "verdict": "...", "verdict_tone": "bad", "summary": "...",
  "signatures": {"L-01": {"cause": "The database rejects the connection: pool exhausted", "action": "...", "bug": "BUG-012"}},
  "scenarios": {"TC-004": {"cause": "The server's 500 comes from L-01"}},
  "missing_info": [{"id": "MI-01", "what_is_missing": "...", "question": "..."}],   // "description" works as an alias of what_is_missing
  "recommendations": [{"action": "...", "reason": "...", "priority": "High"}],
  "next_steps": ["..."]
}
"""
import argparse
import json
import sys
from pathlib import Path

import _history
from _report_styles import (missing_info, e, page, meta, section, kpi_tiles, banner, doc_list, table, bar_chart, line_chart, two_col,
                            level_badge, status_pill, _pill, CRITICAL, WARNING, NEUTRAL, OK, SERIES)
from generate_exploratory_report import CSS_EXTRA

CSS_LOG = """
<style>
.stack{background:#120F0B;border:1px solid var(--border);border-radius:10px;padding:10px 12px;white-space:pre-wrap;word-break:break-word;
  font-family:var(--mono);font-size:11.5px;color:#FFB8B0;max-height:240px;overflow:auto;margin-top:6px}
details.st summary{cursor:pointer;color:var(--muted);font-size:12px;margin-top:4px}
.level{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:700;padding:3px 9px;border-radius:999px}
.sc{border-top:1px solid var(--border-soft);padding:14px 24px}
.sc:first-child{border-top:0}
.sc h3{font-size:15px;color:var(--ink);display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:6px}
</style>
"""


def level(n):
    return _pill(n, CRITICAL if n == "Error" else WARNING, "✕" if n == "Error" else "!")


def hhmm(iso):
    return (iso or "")[11:19] or "—"


def build_html(data, analysis, hist_html=""):
    r = data.get("summary") or {}
    signatures = data.get("signatures") or []
    af = analysis.get("signatures") or {}
    asc = analysis.get("scenarios") or {}
    body = []
    if r.get("failed_with_errors"):
        tone, text = "bad", f'{r["failed_with_errors"]} of {r["failed"]} failed scenario(s) match server errors'
    elif r.get("errors"):
        tone, text = "warn", f'{r["errors"]} error(s) in the logs ({r["error_signatures"]} distinct)'
    else:
        tone, text = "ok", "No errors in the logs for the period"
    body.append(banner(analysis.get("verdict") or text, analysis.get("verdict_tone") or tone))
    body.append('<div style="margin-top:20px">' + kpi_tiles([
        ("Lines", f'{r.get("lines", 0):,}', "", f'{r.get("files", 0)} file(s) · {r.get("no_date", 0)} events without a date', "page"),
        ("Errors", r.get("errors", 0), "bad" if r.get("errors") else "ok", f'{r.get("error_signatures", 0)} distinct signatures', "bad"),
        ("Warnings", r.get("warnings", 0), "warn" if r.get("warnings") else "ok", "includes 4xx responses", "warn"),
        ("Signatures", r.get("signatures", 0), "", "errors and warnings grouped", "list"),
        ("Failed with errors", f'{r.get("failed_with_errors", 0)}/{r.get("failed", 0)}' if r.get("scenarios") else "—",
         "bad" if r.get("failed_with_errors") else "", "scenarios that failed while the server was returning errors", "bug"),
    ]) + "</div>")
    if analysis.get("summary"):
        body.append(section("Executive summary", f'<div class="cardbody"><p class="lead">{e(analysis["summary"])}</p></div>'))
    tl = data.get("timeline") or []
    if len(tl) >= 2:
        x = list(range(len(tl)))
        fx = lambda v: tl[int(v)]["minute"][11:] if 0 <= int(v) < len(tl) else ""
        chart = line_chart(x, [("Errors", CRITICAL, [t["errors"] for t in tl]), ("Warnings", WARNING, [t["warnings"] for t in tl])], fmt_x=fx, height=260)
        body.append(section("Errors and warnings per minute", chart, "a spike usually matches a deploy, an outage or a test run"))
    if signatures:
        body.append(section("What repeats the most", bar_chart([(f'{f["id"]} · {f["example"][:60]}', f["count"], CRITICAL if f["level"] == "Error" else WARNING) for f in signatures[:10]],
                                                          label_width=520)))
    scs = [c for c in data.get("scenarios") or [] if c["status"] == "Failed"]
    if scs:
        blocks = []
        for c in scs:
            ids = ", ".join(f'{x["signature"]} ×{x["count"]}' for x in c["errors"]) or "none"
            a = asc.get(c.get("case") or "") or asc.get(c["scenario"]) or {}
            lines = "\n".join(c.get("lines") or [])
            blocks.append(f'''<div class="sc"><h3>{e(c.get("case") or "")} · {e(c["scenario"])} {status_pill("Failed")}</h3>
              <p class="muted mono">{e(c.get("story") or "")} · {e(c.get("uri"))}:{e(c.get("line"))} · {e(hhmm(c["start"]))} → {e(hhmm(c["end"]))}</p>
              {f'<p><b>Test error:</b> <span class="mono">{e(c["error"])}</span></p>' if c.get("error") else ""}
              <p><b>Server errors while it ran:</b> {e(ids)}</p>
              {f'<p><b>Cause:</b> {e(a["cause"])}</p>' if a.get("cause") else ""}
              {f'<div class="stack">{e(lines)}</div>' if lines else '<p class="muted">No errors in the logs during the scenario: the cause is not in the server (or in these logs).</p>'}</div>''')
        body.append(section("Failed scenarios and the server", "".join(blocks), "errors from the logs between the start and the end of each scenario (± the margin)"))
    if signatures:
        rows = []
        for f in signatures:
            a = af.get(f["id"]) or {}
            stack = f'<details class="st"><summary>stack trace ({len(f["stack"])} lines)</summary><div class="stack">{e(chr(10).join(f["stack"]))}</div></details>' if f.get("stack") else ""
            extra = "".join(f'<div><b>{k}:</b> {e(a[k2])}</div>' for k, k2 in (("Cause", "cause"), ("What to do", "action"), ("Bug", "bug")) if a.get(k2))
            rows.append([f'<span class="mono" style="white-space:nowrap">{e(f["id"])}</span>', level(f["level"]), e(f["count"]),
                         f'<span class="mono" style="color:var(--ink)">{e(f["example"][:220])}</span>{stack}{extra}'
                         + (f'<div class="muted">Scenarios: {e(", ".join(f["scenarios"]))}</div>' if f.get("scenarios") else ""),
                         e(f'{hhmm(f.get("first"))} → {hhmm(f.get("last"))}'), e(", ".join(f["files"]))])
        body.append(section("Signatures", table(["ID", "Level", "Times", "Example", "First → last", "Files"], rows),
                            "each signature is the same error with different data (numbers, ids and texts normalized)"))
    rows = [[f'<span class="mono">{e(f["file"])}</span>', e(f["lines"])] for f in data.get("sources") or []]
    v = data.get("window") or {}
    rows.append(["Period analyzed", e(f'{(v.get("from") or "all")[:19]} → {(v.get("until") or "all")[:19]}')])
    body.append(section("Sources", table(["File", "Lines"], rows)))
    body.append(missing_info(analysis.get("missing_info")))
    if analysis.get("recommendations"):
        rows = [[f'<strong style="color:var(--ink)">{e(x.get("action"))}</strong>', e(x.get("reason")), level_badge(x.get("priority"))]
                for x in analysis["recommendations"]]
        body.append(section("Recommendations", table(["Action", "Why", "Priority"], rows)))
    if analysis.get("next_steps"):
        body.append(section("Next steps", doc_list(analysis["next_steps"])))
    if hist_html:
        body.append(hist_html)
    m = meta([("Analysis", data.get("name")), ("Run", data.get("run")), ("Date", (data.get("date") or "")[:16].replace("T", " "))])
    return page("Logs", "Log analysis", m, CSS_EXTRA + CSS_LOG + "".join(body))


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="HTML logs report from logs.json")
    ap.add_argument("data_json")
    ap.add_argument("output")
    ap.add_argument("--analysis")
    a = ap.parse_args()
    if not a.output.lower().endswith(".html"):
        sys.exit("The output must end in .html")
    with open(a.data_json, encoding="utf-8") as f:
        data = json.load(f)
    analysis = {}
    if a.analysis:
        with open(a.analysis, encoding="utf-8") as f:
            analysis = json.load(f)
    hist_html = _history.section("logs", Path(a.data_json).resolve().parent, data)
    with open(a.output, "w", encoding="utf-8") as f:
        f.write(build_html(data, analysis, hist_html=hist_html))
    print(f"OK: {a.output}")


if __name__ == "__main__":
    main()
