#!/usr/bin/env python3
"""
Generates the Coverage and traceability report in HTML (dashboard, dark mode) from
coverage.json (scripts/analyze_coverage.py) and, optionally, from the analysis by the
coverage-analyst agent.

Usage:
    python scripts/generate_coverage_report.py <coverage.json> <output.html> [--analysis analysis.json]

What it shows: verdict, indicators (covered criteria, cases, automated, run,
passed, gaps), the funnel US → cases → automated → run → passed, the summary per
story (if there are several), the coverage per criterion, the traceability matrix of each case
(source, criteria, automation, management, latest result and bugs) and the prioritized gaps.

The analysis (optional) provides:
{
  "verdict": "US-001 ready to close; US-002 with untested criteria", "verdict_tone": "warn",
  "summary": "Summary for a non-technical person...",
  "notes": {"C-03": "TC-004 gets automated next sprint"},
  "discarded": [{"id": "C-07", "reason": "TC-009 is exploratory: it is not automated"}],
  "recommendations": [{"action": "...", "reason": "...", "priority": "High"}],
  "next_steps": ["..."]
}
"""
import argparse
import json
from pathlib import Path
import sys

import _history
from _report_styles import (e, page, meta, section, kpi_tiles, banner, doc_list, table, bar_chart, column_chart, two_col,
                            level_badge, _pill, CRITICAL, WARNING, NEUTRAL, OK, SERIES)
from generate_exploratory_report import CSS_EXTRA, JS_EXTRA

ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}

CSS_COV = """
<style>
.prog{display:flex;align-items:center;gap:10px;min-width:150px}
.prog .t{flex:1;height:8px;border-radius:999px;background:rgba(244,239,230,.06);overflow:hidden}
.prog .t span{display:block;height:100%;border-radius:999px}
.prog b{font-size:12.5px;color:var(--ink);font-variant-numeric:tabular-nums;min-width:38px;text-align:right}
.tag{display:inline-block;font-family:var(--mono);font-size:11.5px;padding:1px 7px;
  border-radius:6px;background:var(--tile);border:1px solid var(--border);color:var(--ink);margin:1px 3px 1px 0;white-space:nowrap}
.us-title{font-size:15px;font-weight:700;color:var(--ink)}
</style>
"""


def pct(a, b):
    return round(a / b * 100) if b else 0


def progress(a, b):
    p = pct(a, b)
    color = OK if p >= 90 else WARNING if p >= 60 else CRITICAL
    return (f'<div class="prog" data-tip="{a} of {b}"><div class="t"><span style="width:{p}%;background:{color}"></span></div>'
            f'<b>{p} %</b></div>') if b else '<span class="muted">—</span>'


def yes(text="Yes"):
    return _pill(text, OK, "✓")


def no(text="No", color=CRITICAL, icon="✕"):
    return _pill(text, color, icon)


def result_pill(r):
    if not r:
        return '<span class="muted">Not run</span>'
    return {"Passed": yes("Passed"), "Failed": no("Failed"), "Blocked": no("Blocked", NEUTRAL, "⊘")}.get(r["status"], e(r["status"]))


def build_html(data, analysis, hist_html=""):
    discarded = {str(d.get("id")): d.get("reason", "") for d in analysis.get("discarded") or []}
    notes = analysis.get("notes") or {}
    hist = data.get("stories") or []
    tot = {k: sum(h["metrics"][k] for h in hist) for k in ("criteria", "covered_criteria", "cases", "automated",
                                                          "with_result", "passed", "failed", "open_bugs")}
    gaps = [dict(x, story=h["story"]) for h in hist for x in h["gaps"] if x["id"] not in discarded]
    gaps.sort(key=lambda x: ORDER.get(x["severity"], 9))
    serious = [x for x in gaps if x["severity"] in ("Critical", "High")]

    body = []
    if serious:
        tone, text = "bad", f"{len(serious)} important gap(s): untested criteria or failing cases"
    elif gaps:
        tone, text = "warn", "Coverage is good; minor gaps remain to be closed"
    else:
        tone, text = "ok", "Full coverage: every criterion has cases, automated and passed"
    body.append(banner(analysis.get("verdict") or text, analysis.get("verdict_tone") or tone))

    body.append('<div style="margin-top:20px">' + kpi_tiles([
        ("Covered criteria", f'{tot["covered_criteria"]}/{tot["criteria"]}' if tot["criteria"] else "—",
         "" if not tot["criteria"] else "ok" if tot["covered_criteria"] == tot["criteria"] else "bad",
         f'{pct(tot["covered_criteria"], tot["criteria"])} % with at least one case' if tot["criteria"] else "no criteria found", "target",
         {"pct": pct(tot["covered_criteria"], tot["criteria"])} if tot["criteria"] else {}),
        ("Cases", tot["cases"], "", f'{len(hist)} story(ies)', "list"),
        ("Automated", tot["automated"], "ok" if tot["cases"] and tot["automated"] == tot["cases"] else "warn" if tot["cases"] else "",
         f'{pct(tot["automated"], tot["cases"])} % of the cases', "code", {"pct": pct(tot["automated"], tot["cases"])}),
        ("With result", tot["with_result"], "", f'{pct(tot["with_result"], tot["cases"])} % run at least once', "load",
         {"pct": pct(tot["with_result"], tot["cases"])}),
        ("Passed", tot["passed"], "ok" if tot["with_result"] and tot["passed"] == tot["with_result"] else "warn" if tot["with_result"] else "",
         f'{pct(tot["passed"], tot["with_result"])} % of what was run · {tot["failed"]} failed', "ok",
         {"pct": pct(tot["passed"], tot["with_result"])}),
        ("Gaps", len(gaps), "bad" if serious else "warn" if gaps else "ok", f'{len(serious)} of high severity', "search"),
        ("Open bugs", tot["open_bugs"], "bad" if tot["open_bugs"] else "ok", "", "bug"),
    ]) + "</div>")

    if analysis.get("summary"):
        body.append(section("Executive summary", f'<div class="cardbody"><p class="lead">{e(analysis["summary"])}</p></div>'))

    funnel = column_chart([("Criteria", tot["criteria"]), ("Covered", tot["covered_criteria"]), ("Cases", tot["cases"]),
                           ("Automated", tot["automated"]), ("Run", tot["with_result"]), ("Passed", tot["passed"])],
                          height=300, width=660)
    gaps_by_type = {}
    for x in gaps:
        gaps_by_type[x["type"]] = gaps_by_type.get(x["type"], 0) + 1
    body.append(two_col(section("From story to result", funnel, "how much of each stage makes it to the next"),
                        section("Gaps by type", bar_chart(sorted([(k, v, SERIES[0]) for k, v in gaps_by_type.items()], key=lambda x: -x[1]),
                                                          label_width=200) if gaps_by_type else '<div class="cardbody"><p>No gaps.</p></div>')))

    if len(hist) > 1:
        rows = [[f'<span class="us-title">{e(h["story"])}</span>', progress(h["metrics"]["covered_criteria"], h["metrics"]["criteria"]),
                 e(h["metrics"]["cases"]), progress(h["metrics"]["automated"], h["metrics"]["cases"]),
                 progress(h["metrics"]["with_result"], h["metrics"]["cases"]), progress(h["metrics"]["passed"], h["metrics"]["with_result"]),
                 e(len(h["gaps"]))] for h in hist]
        body.append(section("Summary by story", table(["Story", "Covered criteria", "Cases", "Automated", "Run", "Passed", "Gaps"], rows)))

    if gaps:
        rows = []
        for x in gaps:
            note = f'<div class="muted" style="margin-top:4px">{e(notes[x["id"]])}</div>' if x["id"] in notes else ""
            rows.append([f'<span class="id">{e(x["id"])}</span>', e(x["story"]), level_badge(x["severity"]), e(x["type"]),
                         f'{e(x["detail"])}{note}'])
        body.append(section("Coverage gaps", table(["ID", "Story", "Severity", "Type", "Detail"], rows), "what is left to close each story"))

    for h in hist:
        m = h["metrics"]
        if h["criteria"]:
            rows = [[f'<span class="tag">{e(c["id"])}</span>', e(c["description"] or "—"),
                     "".join(f'<span class="tag">{e(tc)}</span>' for tc in c["cases"]) or '<span class="muted">—</span>',
                     yes("Covered") if c["cases"] else no("No cases")] for c in h["criteria"]]
            body.append(section(f'{h["story"]} · Coverage by criterion', table(["Criterion", "Description", "Cases that cover it", "Coverage"], rows),
                                "criteria taken from " + (", ".join(h["criteria_source"]) or "—")))
        if h["cases"]:
            rows = []
            for x in h["cases"]:
                aut = "".join((no(a["suite"], NEUTRAL, "⊘") if a["blocked"] else yes(a["suite"])) for a in x["automated"]) \
                    or '<span class="muted">No</span>'
                mgmt = " ".join(f'<span class="tag">{e(k)}</span>' for k in x["management"].values()) or '<span class="muted">—</span>'
                res = result_pill(x["result"]) + (f'<div class="muted" style="font-size:11.5px">{e(x["result"]["source"])}</div>' if x["result"] else "")
                rows.append([f'<span class="id">{e(x["id"])}</span>', f'{e(x["title"] or "—")}' + (f'<div>{level_badge(x["priority"])}</div>' if x["priority"] else ""),
                             e(", ".join(x["sources"]) or "Automation only"),
                             "".join(f'<span class="tag">{e(c)}</span>' for c in x["criteria"]) or '<span class="muted">—</span>',
                             aut, mgmt, res, " ".join(f'<span class="tag">{e(b)}</span>' for b in x["bugs"]) or '<span class="muted">—</span>'])
            body.append(section(f'{h["story"]} · Traceability matrix', table(
                ["Case", "Title", "Origin", "Criteria", "Automated", "Management", "Latest result", "Bugs"], rows),
                f'{m["cases"]} cases · {m["automated"]} automated · {m["with_result"]} with result'))

    if discarded:
        body.append(section("Discarded", table(["ID", "Reason"], [[e(i), e(r)] for i, r in discarded.items()])))
    if analysis.get("recommendations"):
        rows = [[f'<strong style="color:var(--ink)">{e(x.get("action"))}</strong>', e(x.get("reason")), level_badge(x.get("priority"))]
                for x in analysis["recommendations"]]
        body.append(section("Recommendations", table(["Action", "Why", "Priority"], rows)))
    if analysis.get("next_steps"):
        body.append(section("Next steps", doc_list(analysis["next_steps"])))

    if hist_html:
        body.append(hist_html)
    meta_html = meta([("Scope", data.get("scope")), ("Date", (data.get("date") or "")[:16].replace("T", " ")),
                      ("Stories", ", ".join(h["story"] for h in hist))])
    return page("Coverage and traceability", "Coverage", meta_html, CSS_EXTRA + CSS_COV + "".join(body) + JS_EXTRA)


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Coverage HTML report from coverage.json")
    ap.add_argument("coverage_json")
    ap.add_argument("output")
    ap.add_argument("--analysis")
    a = ap.parse_args()
    if not a.output.lower().endswith(".html"):
        sys.exit("The output must end in .html")
    with open(a.coverage_json, encoding="utf-8") as f:
        data = json.load(f)
    analysis = {}
    if a.analysis:
        with open(a.analysis, encoding="utf-8") as f:
            analysis = json.load(f)
    hist_html = _history.section("coverage", Path(a.coverage_json).resolve().parent, data)
    with open(a.output, "w", encoding="utf-8") as f:
        f.write(build_html(data, analysis, hist_html=hist_html))
    print(f"OK: {a.output}")


if __name__ == "__main__":
    main()
