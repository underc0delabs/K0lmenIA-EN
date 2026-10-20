#!/usr/bin/env python3
"""
Generates a test Closure report in HTML (dashboard, dark mode) from a JSON.

Usage:
    python scripts/generate_closure_report.py <closure.json> <output.html>

Input JSON (the numbers, preferably from "data": see below):
{
  "title": "Closure report — Account signup",
  "story": "US-001",
  "date": "2026-06-29",
  "recommendation": "Go with remarks",
  "recommendation_tone": "warn",                 // optional: ok | warn | bad (otherwise it is inferred from the text)
  "summary": "Executive summary of the round...",
  "results": { "passed": 12, "failed": 2, "blocked": 1 },
  "scope": { "planned": 18, "run": 15 },          // optional
  "scope_note": "Text about the coverage.",       // optional
  "bugs": {
    "by_severity": { "Critical": 0, "High": 1, "Medium": 2, "Low": 1 },
    "open_critical": [ {"id": "BUG-003", "title": "...", "severity": "High"} ]
  },
  "pending_risks": ["...", "..."],
  "missing_info": [                            // optional (context-research skill)
    {"id": "MI-01", "what_is_missing": "...", "impact": "AC3 · TC-004", "question": "...", "status": "Open"}
  ],
  "conclusion": "Closing text."
}

"data" (recommended): path to the JSON from scripts/collect_results.py. If present, the results,
the bugs, performance and security come from there (from the real files of the round) and are not
written by hand: the report JSON only provides the analysis (summary, recommendation, risks…).

    python scripts/collect_results.py --story US-001 --output output/closure-reports/data-US-001.json

Statuses: Passed | Failed | Blocked     Severity: Critical | High | Medium | Low
The HTML is self-contained (inline CSS and SVG), it does not use the internet.
"""
import sys
import json
from pathlib import Path

from _report_styles import (e, page, meta, section, kpi_tiles, donut, bar_chart, legend,
                            banner, doc_list, table, level_badge, status_pill, LEVEL_COLOR, STATUS_COLOR)

SEVERITIES = ["Critical", "High", "Medium", "Low"]


def _recommendation_tone(rec):
    low = (rec or "").lower()
    if "no-go" in low or "no go" in low or "not ready" in low or "reject" in low:
        return "bad"
    if "remark" in low or "risk" in low or "condition" in low or "reserv" in low or "observ" in low:
        return "warn"
    if "go" in low or "ready" in low:
        return "ok"
    return "warn"


def _legend(pas, fai, blo):
    return legend([("Passed", STATUS_COLOR["Passed"], pas), ("Failed", STATUS_COLOR["Failed"], fai),
                   ("Blocked", STATUS_COLOR["Blocked"], blo)])


def build_html(data):
    res = data.get("results", {}) or {}
    pas = int(res.get("passed", 0) or 0)
    fai = int(res.get("failed", 0) or 0)
    blo = int(res.get("blocked", 0) or 0)
    total = pas + fai + blo
    pct = round(pas / total * 100) if total else 0

    body = []

    # Go/no-go banner
    rec = data.get("recommendation", "")
    if rec:
        tone = data.get("recommendation_tone") or _recommendation_tone(rec)
        body.append(banner(rec, tone))

    # Hero: passed donut + KPIs
    dn = donut([(pas, STATUS_COLOR["Passed"], "Passed"), (fai, STATUS_COLOR["Failed"], "Failed"),
                (blo, STATUS_COLOR["Blocked"], "Blocked")], pct, "passed")
    kpis = kpi_tiles([
        ("Total", total, ""),
        ("Passed", pas, "ok", f"{pct} % of what was run", "", {"pct": pct}),
        ("Failed", fai, "bad"),
        ("Blocked", blo, "blk"),
    ])
    body.append(f'<div class="card hero" style="margin-top:20px">'
                f'<div class="gauge">{dn}{_legend(pas, fai, blo)}</div>{kpis}</div>')

    # Executive summary
    if data.get("summary"):
        body.append(section("Executive summary", f'<div class="cardbody"><p class="lead">{e(data["summary"])}</p></div>'))

    # Scope covered
    scope = data.get("scope", {}) or {}
    planned = scope.get("planned")
    run = scope.get("run")
    note = data.get("scope_note")
    if planned or run or note:
        parts = '<div class="cardbody">'
        if planned and run is not None:
            cov = round(run / planned * 100) if planned else 0
            parts += (f'<p><strong style="color:var(--ink)">{run}</strong> of '
                      f'<strong style="color:var(--ink)">{planned}</strong> planned cases were run '
                      f'(<strong style="color:var(--ink)">{cov}%</strong>).</p>'
                      f'<div class="bar-track" style="width:100%;margin-top:12px">'
                      f'<span class="seg" style="width:{cov}%;background:{STATUS_COLOR["Passed"]}"></span></div>')
        if note:
            parts += f'<p style="margin-top:12px">{e(note)}</p>'
        parts += '</div>'
        body.append(section("Scope covered", parts))

    # Bugs by severity + open critical ones
    bugs = data.get("bugs", {}) or {}
    sev = bugs.get("by_severity", {}) or {}
    critical = bugs.get("open_critical", []) or []
    if sev or critical:
        content = ""
        if sev:
            content += bar_chart([(s, int(sev.get(s, 0) or 0), LEVEL_COLOR[s]) for s in SEVERITIES])
        if critical:
            rows = [[f'<span class="id mono">{e(b.get("id"))}</span>', e(b.get("title")),
                     level_badge(b.get("severity"))] for b in critical]
            content += table(["ID", "Open bug", "Severity"], rows)
        body.append(section("Bugs by severity", content))

    # Missing information: what was never defined and conditions the result of the round
    missing = data.get("missing_info") or []
    if missing:
        open_ = [f for f in missing if str(f.get("status", "Open")).lower() != "resolved"]
        items = [f'{f.get("id", "")} — {f.get("what_is_missing", "")}'
                 + (f' (impact: {f["impact"]})' if f.get("impact") else "")
                 + (f' · Question: {f["question"]}' if f.get("question") else "")
                 + f' · {f.get("status", "Open")}' for f in missing]
        title = f"Missing information ({len(open_)} open)"
        body.append(section(title, doc_list(items)))

    # What comes from collect_results.py (sources, performance, security, cases)
    collected = data.get("_data") or {}
    if collected.get("sources"):
        chips = "".join(f'<span class="chip">{e(f)}</span>' for f in collected["sources"])
        body.append(section("Sources of the results", f'<div class="cardbody"><div class="meta" style="margin-top:0">{chips}</div>'
                            f'<p style="margin-top:12px">A case run several times counts only once, with its most recent result.</p></div>'))
    if collected.get("performance"):
        rows = [[e(x["report"]), e(x["verdict"]), e(x["capacity"] or "—"), e(x["runs"])] for x in collected["performance"]]
        body.append(section("Performance", table(["Report", "Verdict", "Observed capacity", "Runs"], rows)))
    if collected.get("security"):
        rows = [[e(x["scan"])] + [e(x["findings"][n]) for n in ("High", "Medium", "Low", "Informational")] for x in collected["security"]]
        body.append(section("Web security", table(["Scan", "High", "Medium", "Low", "Informational"], rows),
                            "findings of the passive scan, without the discarded false positives"))
    cases = collected.get("cases") or []
    if cases:
        rows = [[f'<span class="id mono">{e(c["id"])}</span>', e(c.get("title", "")), status_pill(c["status"]), e(c["source"])]
                for c in cases]
        body.append(section("Case detail", table(["Case", "Title", "Status", "Source"], rows), f"{len(cases)} cases"))
    if (collected.get("bugs") or {}).get("no_status"):
        body.append(section("Bugs without status", doc_list([f'{b}: the report has no Status field; it counts as open' for b in collected["bugs"]["no_status"]])))

    # Risks and pending items
    if data.get("pending_risks"):
        body.append(section("Risks and pending items", doc_list(data["pending_risks"])))

    # Conclusion
    if data.get("conclusion"):
        body.append(section("Conclusion", f'<div class="cardbody"><p>{e(data["conclusion"])}</p></div>'))

    meta_html = meta([("Story", data.get("story")), ("Date", data.get("date"))])
    title = data.get("title") or "Closure report"
    return page(title, "Closure report", meta_html, "".join(body))


def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/generate_closure_report.py <closure.json> <output.html>")
        sys.exit(1)
    source, output = sys.argv[1], sys.argv[2]
    if not output.lower().endswith(".html"):
        print("The output must end in .html")
        sys.exit(1)
    with open(source, encoding="utf-8") as f:
        data = json.load(f)
    if data.get("data"):
        path = Path(data["data"])
        if not path.is_absolute() and not path.exists():
            path = Path(source).resolve().parent / path
        if not path.exists():
            sys.exit(f"[!] Can't find the collected data: {data['data']} (generate it with scripts/collect_results.py)")
        collected = json.loads(path.read_text(encoding="utf-8"))
        data["results"] = collected["results"]
        data["bugs"] = {"by_severity": collected["bugs"]["by_severity"], "open_critical": collected["bugs"]["open_critical"]}
        data["_data"] = collected
    with open(output, "w", encoding="utf-8") as f:
        f.write(build_html(data))
    print(f"OK: {output}")


if __name__ == "__main__":
    main()
