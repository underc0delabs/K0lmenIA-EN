#!/usr/bin/env python3
"""
Generates the case review HTML report (dashboard, dark mode) from review.json
(scripts/review_cases.py) and, optionally, from the analysis of the case-reviewer agent.

Usage:
    python scripts/generate_review_report.py <review.json> <output.html> [--analysis analysis.json]

What it shows: verdict, indicators (cases, average score, to improve, without issues, duplicates, without
expected result, manual execution time), the score distribution, the issues by type, the
summary per story (cases, negatives, score and time), each case with its score, time, issues,
suggestions and the improved version the agent proposes, and the evolution of the reviews.

The analysis (optional) provides:
{
  "verdict": "...", "verdict_tone": "warn", "summary": "...",
  "proposals": {"US-001:TC-003": {"title": "...", "steps": "1. ...\\n2. ...", "result": "...", "note": "..."}},
  "discarded": [{"case": "US-001:TC-004", "type": "Duplicate", "reason": "They test different devices"}],
  "recommendations": [{"action": "...", "reason": "...", "priority": "High"}],
  "next_steps": ["..."]
}
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import _history
from _report_styles import (e, page, meta, section, kpi_tiles, banner, doc_list, table, bar_chart, column_chart, two_col,
                              level_badge, _pill, CRITICAL, WARNING, NEUTRAL, OK, SERIES)
from generate_exploratory_report import CSS_EXTRA
from estimation import format_time

CSS_REV = """
<style>
.score{display:flex;align-items:center;gap:8px;min-width:110px}
.score .t{flex:1;height:6px;border-radius:99px;background:rgba(244,239,230,.06);overflow:hidden}
.score .t span{display:block;height:100%;border-radius:99px}
.score b{font-family:var(--mono);font-size:12px;color:var(--ink);min-width:24px;text-align:right}
.probs{margin:0;padding-left:16px;font-size:12.5px;color:var(--body)}
.probs li{margin:3px 0}
.probs .sug{color:var(--muted)}
.prop{margin-top:8px;border:1px solid rgba(92,191,74,.35);background:rgba(92,191,74,.06);border-radius:10px;padding:10px 12px;font-size:12.5px;color:#C6EDB9;white-space:pre-wrap}
.prop b{color:#E6FBE6}
.discarded{text-decoration:line-through;opacity:.6}
</style>
"""


def score(p):
    color = OK if p >= 85 else WARNING if p >= 70 else CRITICAL
    return f'<div class="score"><div class="t"><span style="width:{p}%;background:{color}"></span></div><b>{p}</b></div>'


def build_html(data, analysis, hist_html=""):
    cases = data.get("cases") or []
    r = data.get("summary") or {}
    props = analysis.get("proposals") or {}
    disc = {(d.get("case"), d.get("type")): d.get("reason") for d in analysis.get("discarded") or []}
    body = []
    avg = r.get("avg_score")
    if avg is None:
        tone, text = "warn", "There are no cases to review"
    elif avg >= 85 and not r.get("no_result"):
        tone, text = "ok", f"Cases in good shape (average score {avg})"
    elif avg >= 70:
        tone, text = "warn", f"Acceptable cases with details to improve (average score {avg})"
    else:
        tone, text = "bad", f"Many cases to improve (average score {avg})"
    body.append(banner(analysis.get("verdict") or text, analysis.get("verdict_tone") or tone))
    n = r.get("cases", 0)
    body.append('<div style="margin-top:20px">' + kpi_tiles([
        ("Cases reviewed", n, "", f'{r.get("manual", 0)} manual · {r.get("bdd", 0)} BDD', "list"),
        ("Average score", avg if avg is not None else "—", "" if avg is None else ("ok" if avg >= 85 else "warn" if avg >= 70 else "bad"),
         "100 = no issues", "target", {"pct": avg or 0}),
        ("To improve", r.get("to_improve", 0), "bad" if r.get("to_improve") else "ok", "score below 70", "warn"),
        ("No issues", r.get("no_issues", 0), "ok" if r.get("no_issues") == n and n else "", f'{round(r.get("no_issues", 0) / n * 100) if n else 0} % of the cases', "ok"),
        ("Possible duplicates", r.get("duplicates", 0), "warn" if r.get("duplicates") else "ok", "nearly identical steps and titles", "search"),
        ("No expected result", r.get("no_result", 0), "bad" if r.get("no_result") else "ok", "or scenarios without Then", "bad"),
        ("Manual run", r.get("total_time", "—"), "", "estimated time of all the cases (scripts/estimation.py)", "clock"),
        ("Problems", r.get("findings", 0), "", ", ".join(f"{k} {v}" for k, v in (r.get("by_severity") or {}).items() if v) or "none", "code"),
    ]) + "</div>")
    if analysis.get("summary"):
        body.append(section("Executive summary", f'<div class="cardbody"><p class="lead">{e(analysis["summary"])}</p></div>'))

    ranges = [("0–49", 0, 49), ("50–69", 50, 69), ("70–84", 70, 84), ("85–99", 85, 99), ("100", 100, 100)]
    dist = [(lbl, sum(1 for c in cases if lo <= c["score"] <= hi), CRITICAL if hi < 70 else WARNING if hi < 85 else OK) for lbl, lo, hi in ranges]
    kinds = Counter(x["type"] for c in cases for x in c["findings"])
    body.append(two_col(section("Case scores", column_chart(dist, width=660), "how many cases there are in each range"),
                        section("Issues by type", bar_chart([(t, k, SERIES[i % len(SERIES)]) for i, (t, k) in enumerate(kinds.most_common())], label_width=150)
                                if kinds else '<p class="muted" style="padding:16px 24px">No issues.</p>')))

    rows = []
    for h in data.get("by_story") or []:
        probs = "".join(f'<div>{level_badge(x["severity"])} {e(x["title"])}</div>' for x in h["findings"]) or '<span class="muted">—</span>'
        rows.append([f'<strong style="color:var(--ink)">{e(h["story"])}</strong>', e(h["cases"]), e(h["negatives"]), score(h["avg_score"]),
                     e(format_time(h["time_min"])), probs])
    if rows:
        body.append(section("By story", table(["Story", "Cases", "Negative or edge", "Score", "Manual run", "Problems"], rows)))

    rows = []
    for c in cases:
        key = f'{c["story"]}:{c["id"]}'
        items = ""
        for x in c["findings"]:
            struck = ' class="discarded"' if (key, x["type"]) in disc else ""
            sug = f' <span class="sug">— {e(x["suggestion"])}</span>' if x.get("suggestion") else ""
            items += f'<li{struck}>{level_badge(x["severity"])} <strong style="color:var(--ink)">{e(x["title"])}</strong>{sug}</li>'
        prop = props.get(key) or props.get(c["id"])
        prop_block = ""
        if prop:
            parts = [f'<b>{e(k.capitalize())}:</b> {e(v)}' for k, v in prop.items() if k != "note" and v]
            note = f'\n<i>{e(prop["note"])}</i>' if prop.get("note") else ""
            prop_block = f'<div class="prop"><b>Proposed version</b>\n' + "\n".join(parts) + note + "</div>"
        kind = "BDD" if c["type"] != "manual" else "Manual"
        rows.append([f'<span class="mono" style="color:var(--ink);white-space:nowrap">{e(c["story"])}</span><div class="mono" style="white-space:nowrap">{e(c["id"])}</div>',
                     f'<strong style="color:var(--ink)">{e(c["title"])}</strong><div class="muted">{e(kind)} · {e(c.get("file", ""))}</div>',
                     score(c["score"]), e(c.get("time", "—")),
                     (f'<ul class="probs">{items}</ul>' if items else _pill("No issues", OK, "✓")) + prop_block])
    if rows:
        body.append(section("Each case", table(["Case", "Title", "Score", "Time", "Issues and proposal"], rows),
                            "sorted from the lowest score to the highest"))
    if analysis.get("recommendations"):
        rows = [[f'<strong style="color:var(--ink)">{e(x.get("action"))}</strong>', e(x.get("reason")), level_badge(x.get("priority"))]
                for x in analysis["recommendations"]]
        body.append(section("Recommendations", table(["Action", "Why", "Priority"], rows)))
    if analysis.get("next_steps"):
        body.append(section("Next steps", doc_list(analysis["next_steps"])))
    if hist_html:
        body.append(hist_html)
    meta_html = meta([("Story", data.get("story")), ("Review", data.get("name")), ("Date", (data.get("date") or "")[:16].replace("T", " ")),
                      ("Files", str(len(data.get("sources") or [])))])
    return page("Case review", "Test case quality", meta_html, CSS_EXTRA + CSS_REV + "".join(body))


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Case review HTML report from review.json")
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
    hist_html = _history.section("review", Path(a.data_json).resolve().parent, data)
    with open(a.output, "w", encoding="utf-8") as f:
        f.write(build_html(data, analysis, hist_html=hist_html))
    print(f"OK: {a.output}")


if __name__ == "__main__":
    main()
