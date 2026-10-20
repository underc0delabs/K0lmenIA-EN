#!/usr/bin/env python3
"""
Generates an HTML report (dashboard, dark mode) of a test run, from a JSON.

Usage:
    python scripts/generate_report.py <results.json> <output.html>

Input JSON:
{
  "title": "Create account",
  "story": "US-001",
  "date": "2026-06-18 14:30",
  "mode": "headed",
  "url": "https://qarmy.ar/practica/automation/",
  "cases": [
    {"id": "TC-001", "title": "Signup with valid data",
     "priority": "Critical", "status": "Passed",
     "duration_s": 4.2, "reason": "", "evidence": "evidence/tc-001.png",
     "missing_info": ["MI-01"]}
  ],
  "missing_info": [
    {"id": "MI-01", "what_is_missing": "Text of the message when the account gets locked", "question": "...", "status": "Open"}
  ]
}

"missing_info" (optional, per case): the case depends on information that is missing (skill
context-research). It is flagged in the case detail and a warning is shown below the summary;
with the top-level "missing_info" (one object per item: id, what_is_missing, question, status) the
"Missing information" section is added at the end.

Statuses:  Passed | Failed | Blocked
Priority:  Critical | High | Medium | Low

The HTML is self-contained: CSS and charts are inline (SVG/CSS), it does not use the internet.
"""
import sys
import json
import os

from _report_styles import (thumbnail, resolve_evidence, e, page, meta, section, kpi_tiles, donut, legend, banner, table,
                            stacked_bars, bar_chart, level_badge, status_pill, STATUS_COLOR, SERIES)

STATUSES = ["Passed", "Failed", "Blocked"]
PRIOS = ["Critical", "High", "Medium", "Low"]


def _mi_ids(c):
    v = c.get("missing_info") or []
    if isinstance(v, str):
        v = v.replace(";", ",").split(",")
    return [str(x).strip() for x in v if str(x).strip()]


def _status(c):
    return (c.get("status") or "").strip()


def _hero(cases):
    total = len(cases)
    counts = {s: sum(1 for c in cases if _status(c) == s) for s in STATUSES}
    pct = round(counts["Passed"] / total * 100) if total else 0
    dn = donut([(counts[s], STATUS_COLOR[s], s) for s in STATUSES], pct, "passed")
    leg = legend([(s, STATUS_COLOR[s], counts[s]) for s in STATUSES])
    durs = [c.get("duration_s") for c in cases if isinstance(c.get("duration_s"), (int, float))]
    kpis = kpi_tiles([
        ("Cases run", total, "", f"{sum(durs):.1f} s in total" if durs else ""),
        ("Passed", counts["Passed"], "ok", f"{pct} % of the total", "", {"pct": pct}),
        ("Failed", counts["Failed"], "bad" if counts["Failed"] else "ok"),
        ("Blocked", counts["Blocked"], "blk" if counts["Blocked"] else ""),
    ])
    return f'<div class="card hero"><div class="gauge">{dn}{leg}</div>{kpis}</div>'


def _by_priority(cases):
    rows = []
    for p in PRIOS:
        cs = [c for c in cases if (c.get("priority") or "").strip() == p]
        if cs:
            rows.append((p, [sum(1 for c in cs if _status(c) == s) for s in STATUSES]))
    return stacked_bars(rows, [(s, STATUS_COLOR[s]) for s in STATUSES])


def _durations(cases):
    timed = [c for c in cases if isinstance(c.get("duration_s"), (int, float))]
    if not timed:
        return ""
    timed = sorted(timed, key=lambda c: -c["duration_s"])[:15]
    rows = [(f'{c.get("id")} · {c.get("title", "")}', round(c["duration_s"], 1), SERIES[0]) for c in timed]
    return section("Duration per case", bar_chart(rows, label_width=260), "seconds · the 15 longest")


def _table(cases, html_dir=None):
    rows = []
    for c in cases:
        ev = c.get("evidence")
        if ev and html_dir:
            ev, exists = resolve_evidence(ev, html_dir)
        else:
            exists = True
        ev_html = thumbnail(ev, f'{c.get("id", "")} · {c.get("title", "")}', "s", exists) if ev else '<span class="muted">—</span>'
        det = e(c.get("reason") or "") or '<span class="muted">—</span>'
        if _mi_ids(c):
            det += f'<br><span style="color:#FFE066">Missing information: {e(", ".join(_mi_ids(c)))}</span>'
        dur = c.get("duration_s")
        rows.append([f'<span class="id mono">{e(c.get("id"))}</span>', e(c.get("title")),
                     level_badge(c.get("priority")), status_pill(_status(c)),
                     f"{dur:.1f} s" if isinstance(dur, (int, float)) else '<span class="muted">—</span>', det, ev_html])
    return table(["ID", "Case", "Priority", "Status", "Duration", "Detail", "Evidence"], rows)


def build_html(data, html_dir=None):
    """html_dir: folder where the HTML is written (to locate the evidence and warn if it is missing)."""
    cases = data.get("cases", []) or []
    body = [_hero(cases)]

    affected = [c for c in cases if _mi_ids(c)]
    if affected:
        ids = sorted({i for c in affected for i in _mi_ids(c)})
        n = len(affected)
        body.append(f'<div style="margin-top:16px">' + banner(
            f'Missing information: {n} case{"s" if n != 1 else ""} depend{"" if n != 1 else "s"} on data that is not '
            f'defined ({", ".join(ids)}). The result may change once it is resolved.', "warn") + '</div>')

    body.append(section("Results by priority", _by_priority(cases)))
    body.append(_durations(cases))
    body.append(section("Case details", _table(cases, html_dir), f"{len(cases)} cases · click the evidence to enlarge it"))

    # The expected format is one object per item; a bare "MI-01" is accepted as {"id": "MI-01"} (it does not break the report).
    missing = [f if isinstance(f, dict) else {"id": str(f)} for f in (data.get("missing_info") or [])]
    if missing:
        rows = [[f'<span class="id mono">{e(f.get("id", ""))}</span>', e(f.get("what_is_missing", "")),
                 e(f.get("question", "")) or '<span class="muted">—</span>', e(f.get("status", "Open"))] for f in missing]
        body.append(section("Missing information", table(["ID", "What is missing", "Question", "Status"], rows)))

    meta_html = meta([("Story", data.get("story")), ("Date", data.get("date")),
                      ("Mode", data.get("mode")), ("URL", data.get("url"))])
    return page(data.get("title") or "Run report", "Run report", meta_html, "".join(body))


def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/generate_report.py <results.json> <output.html>")
        sys.exit(1)
    source, target = sys.argv[1], sys.argv[2]
    if not target.lower().endswith(".html"):
        print("The output must end in .html")
        sys.exit(1)
    with open(source, encoding="utf-8") as f:
        data = json.load(f)
    with open(target, "w", encoding="utf-8") as f:
        f.write(build_html(data, os.path.dirname(os.path.abspath(target))))
    print(f"OK: {target}")


if __name__ == "__main__":
    main()
