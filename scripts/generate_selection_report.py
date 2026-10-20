#!/usr/bin/env python3
"""
Generates the case selection HTML report (dashboard, dark mode) from selection.json
(scripts/select_cases.py) and, optionally, from the analysis of the test-case-selector agent.

Usage:
    python scripts/generate_selection_report.py <selection.json> <output.html> [--analysis analysis.json]

What it shows: what to run and why. Verdict with the risk of the change, indicators (inventory,
selected, essential, recommended, minimal regression, time and savings, changes without cases),
selection by story and by type, what changed (files with their concepts, commits, stories,
keywords with their weight), the commands ready to copy (bash and PowerShell) for the
automated part, the table of selected cases with their score and their reasons, the uncovered
changes and what was left out.

The analysis (optional) provides:
{
  "verdict": "High-risk change in payments: 14 cases, 22 min", "verdict_tone": "warn",
  "risk": "High", "summary": "Summary for a non-technical person...",
  "adjustments": {"US-003:TC-007": {"group": "Essential", "reason": "It touches the rounding of the total"}},
  "recommendations": [{"action": "...", "reason": "...", "priority": "High"}],
  "next_steps": ["..."]
}
(the adjustments are applied by scripts/select_cases.py: that way the CSV and the commands change too)
"""
import argparse
import json
from pathlib import Path
import sys
from collections import Counter

import _history
from _report_styles import (e, page, meta, section, kpi_tiles, banner, doc_list, table, stacked_bars, donut_panel, two_col,
                              level_badge, status_pill, _pill, NEUTRAL, SERIES, WARNING, CRITICAL, OK, SERIOUS)
from generate_exploratory_report import CSS_EXTRA

GROUPS = ["Essential", "Recommended", "Minimal regression", "Not selected"]
COLOR_GROUP = {"Essential": SERIES[1], "Recommended": SERIES[2], "Minimal regression": SERIES[4], "Not selected": NEUTRAL}
GROUP_ICON = {"Essential": "●", "Recommended": "◐", "Minimal regression": "○", "Not selected": "–"}
RISK = {"High": "bad", "Medium": "warn", "Low": "ok"}

CSS_SEL = """
<style>
.cmdbox{position:relative;background:#120F0B;border:1px solid var(--border);border-radius:12px;padding:14px 16px 14px 16px;margin:10px 0}
.cmdbox .et{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:600;margin-bottom:6px;display:flex;gap:10px;align-items:center}
.cmdbox pre{margin:0;white-space:pre-wrap;word-break:break-all;font-family:var(--mono);font-size:12.5px;color:#FFE58A}
.cmdbox button{position:absolute;top:10px;right:10px;background:var(--tile);border:1px solid var(--border);color:var(--ink);border-radius:8px;
  padding:4px 10px;font:inherit;font-size:12px;cursor:pointer}
.cmdbox button.ok{background:var(--accent);color:#0E0C09;border-color:transparent}
.score{display:flex;align-items:center;gap:8px;min-width:110px}
.score .t{flex:1;height:6px;border-radius:99px;background:rgba(244,239,230,.06);overflow:hidden}
.score .t span{display:block;height:100%;border-radius:99px}
.score b{font-family:var(--mono);font-size:12px;color:var(--ink);min-width:24px;text-align:right}
.reasons{margin:0;padding-left:16px;color:var(--body);font-size:12.5px}
.reasons li{margin:2px 0}
.tags{display:flex;flex-wrap:wrap;gap:8px;padding:16px 24px}
.tags span{font-size:12.5px;padding:5px 11px;border-radius:999px;background:var(--tile);border:1px solid var(--border);color:var(--ink)}
.tags span b{font-family:var(--mono);font-weight:600;color:var(--muted);margin-left:6px;font-size:11px}
.commits li{margin:3px 0;color:var(--body)}
.commits code{font-family:var(--mono);font-size:12px;color:var(--muted);margin-right:6px}
</style>
"""

JS_SEL = """
<script>
document.querySelectorAll('.cmdbox button').forEach(function(b){b.addEventListener('click',function(){
  var t=b.parentNode.querySelector('pre').innerText;
  (navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(function(){b.textContent='Copied';b.classList.add('ok');
    setTimeout(function(){b.textContent='Copy';b.classList.remove('ok')},1600)}).catch(function(){b.textContent='Select and copy'});});});
</script>
"""


def group_pill(g):
    return _pill(g, COLOR_GROUP.get(g, NEUTRAL), GROUP_ICON.get(g, "●"))


def score(p, g):
    color = COLOR_GROUP.get(g, NEUTRAL)
    return f'<div class="score"><div class="t"><span style="width:{max(0, min(100, p))}%;background:{color}"></span></div><b>{e(p)}</b></div>'


def cmdbox(label, cmd):
    return f'<div class="cmdbox"><div class="et">{e(label)}</div><pre>{e(cmd)}</pre><button type="button">Copy</button></div>'


def case_row(c):
    res = (c.get("result") or {}).get("status")
    kind = c["type"] + (f' · {c["suite"]}' if c.get("suite") else "")
    return [group_pill(c["group"]), score(c["score"], c["group"]),
            f'<span class="mono" style="color:var(--ink);white-space:nowrap">{e(c["story"])}</span><div class="mono" style="white-space:nowrap">{e(c["id"])}</div>',
            f'<strong style="color:var(--ink)">{e(c["title"])}</strong>'
            + (f'<div class="muted">{e(c.get("story_title"))}</div>' if c.get("story_title") else ""),
            e(kind), level_badge(c.get("priority") or "Medium"), status_pill(res) if res else '<span class="muted">—</span>',
            f'{e(c["minutes"])} min', f'<ul class="reasons">{"".join(f"<li>{e(r)}</li>" for r in c.get("reasons") or [])}</ul>']


def build_html(data, analysis, hist_html=""):
    cases = data.get("cases") or []
    r = data.get("summary") or {}
    change = data.get("change") or {}
    sel = [c for c in cases if c["group"] != "Not selected"]
    body = []
    risk = analysis.get("risk")
    text = (f'Run {r.get("selected", 0)} of {r.get("cases", 0)} cases ({r.get("automated", 0)} automated, '
            f'{r.get("manual", 0)} manual): about {r.get("selection_minutes", 0)} min, {r.get("savings_pct", 0)} % less than the full regression')
    tone = RISK.get(risk, "warn" if r.get("no_coverage") else "ok")
    body.append(banner(analysis.get("verdict") or text, analysis.get("verdict_tone") or tone))
    n = r.get("cases", 0)
    pg = r.get("by_group") or {}
    body.append('<div style="margin-top:20px">' + kpi_tiles([
        ("Cases in the inventory", n, "", f'{r.get("stories", 0)} story(ies)', "list"),
        ("Selected", r.get("selected", 0), "", f'{round(r.get("selected", 0) / n * 100) if n else 0} % of the inventory', "filter",
         {"pct": r.get("selected", 0) / n * 100 if n else 0}),
        ("Essential", pg.get("Essential", 0), "bad" if pg.get("Essential") else "", "they touch what changed", "target"),
        ("Recommended", pg.get("Recommended", 0), "warn" if pg.get("Recommended") else "", "related to the change", "search"),
        ("Minimal regression", pg.get("Minimal regression", 0), "", "smoke and Critical priority", "ok"),
        ("Estimated time", f'{r.get("selection_minutes", 0)} min', "", f'of {r.get("total_minutes", 0)} min for the full regression', "clock"),
        ("Savings", f'{r.get("savings_pct", 0)} %', "ok" if r.get("savings_pct", 0) >= 30 else "", "versus running everything", "bolt",
         {"pct": r.get("savings_pct", 0)}),
        ("Changes without cases", r.get("no_coverage", 0), "warn" if r.get("no_coverage") else "ok", "files no case covers", "warn"),
    ]) + "</div>")
    if analysis.get("summary") or risk:
        txt = (f'<p class="lead">{e(analysis.get("summary") or "")}</p>' if analysis.get("summary") else "")
        if risk:
            txt += f'<p style="margin-top:10px">Change risk: {level_badge(risk)}</p>'
        body.append(section("Executive summary", f'<div class="cardbody">{txt}</div>'))

    # By story (stacked by group) and by type
    by_us = {}
    for c in cases:
        by_us.setdefault(c["story"], Counter())[c["group"]] += 1
    rows = sorted(((us, [cnt[g] for g in GROUPS[:3]]) for us, cnt in by_us.items()), key=lambda x: -sum(x[1]))[:14]
    kinds = Counter(c["type"] for c in sel)
    body.append(two_col(
        section("Selection by story", stacked_bars(rows, [(g, COLOR_GROUP[g]) for g in GROUPS[:3]]),
                f'{r.get("selected_stories", 0)} of {r.get("stories", 0)} stories have selected cases'),
        section("Selected by type", donut_panel([(kinds.get("Automated", 0), SERIES[1], "Automated (npm test)"),
                                                 (kinds.get("Manual", 0), SERIES[3], "Manual")],
                                                round(kinds.get("Automated", 0) / len(sel) * 100) if sel else 0, "automated"))))

    # How to run it
    cmds = data.get("commands") or []
    block = ""
    for c in cmds:
        block += cmdbox(f'Suite {c["suite"]} · {c["cases"]} case(s) · bash', c["bash"]) + cmdbox(f'Suite {c["suite"]} · PowerShell', c["powershell"])
    manual = [c for c in sel if c["type"] == "Manual"]
    if manual:
        block += f'<p style="margin-top:10px">The {len(manual)} manual case(s) are in <span class="mono">selection.csv</span> (it opens with Excel), sorted by group and score.</p>'
    if not block:
        block = '<p class="muted">There are no selected cases to run.</p>'
    body.append(section("How to run it", f'<div class="cardbody">{block}</div>', "the automated part runs with no agents and no tokens"))

    # What changed
    parts = []
    if change.get("stories") or change.get("keys") or data.get("affected_stories"):
        parts.append(f'<div class="lbl" style="padding:14px 24px 0">Stories and issues</div><div class="tags">'
                     + "".join(f"<span>{e(h)}</span>" for h in sorted(set(change.get("stories") or []) | set(change.get("keys") or []) | set(data.get("affected_stories") or [])))
                     + "</div>")
    if change.get("words"):
        parts.append('<div class="lbl" style="padding:6px 24px 0">Concepts of the change (with their weight)</div><div class="tags">'
                     + "".join(f'<span>{e(p["word"])}<b>{e(p["weight"])}</b></span>' for p in change["words"][:20]) + "</div>")
    if change.get("files"):
        uncovered = {x["file"] for x in data.get("no_coverage") or []}
        rows = [[f'<span class="mono">{e(f)}</span>', _pill("No cases", WARNING, "!") if f in uncovered else _pill("With cases", OK, "✓")]
                for f in change["files"][:60]]
        parts.append(table(["File", "Coverage"], rows))
    if change.get("commits"):
        parts.append('<div class="cardbody"><ul class="commits">' + "".join(
            f'<li><code>{e(c["hash"])}</code>{e(c["message"])}</li>' for c in change["commits"][:20]) + "</ul></div>")
    if change.get("text"):
        parts.append(f'<div class="cardbody"><p class="muted" style="white-space:pre-wrap">{e(change["text"][:1200])}</p></div>')
    if parts:
        body.append(section("What changed", "".join(parts), " · ".join(change.get("sources") or [])))

    if sel:
        body.append(section("Selected cases", table(["Group", "Score", "Case", "Title", "Type", "Priority", "Latest result", "Time", "Why"],
                                                    [case_row(c) for c in sel]),
                            "sorted by group and score · filter by group or search for a case"))
    if data.get("no_coverage"):
        rows = [[f'<span class="mono">{e(x["file"])}</span>', e(", ".join(x.get("words") or []))] for x in data["no_coverage"]]
        body.append(section("Uncovered changes", table(["File", "Concepts that do not appear in any case"], rows),
                            "risk: what changed here is not tested by any case → generate cases (manual-case-generator or BDD)"))
    left_out = [c for c in cases if c["group"] == "Not selected"]
    if left_out:
        body.append(section("Not selected", table(["Group", "Score", "Case", "Title", "Type", "Priority", "Latest result", "Time", "Why"],
                                                  [case_row(c) for c in left_out[:200]]),
                            f"{len(left_out)} case(s) that do not touch the change · it is still worth running the full regression before a big release"))
    if analysis.get("recommendations"):
        rows = [[f'<strong style="color:var(--ink)">{e(x.get("action"))}</strong>', e(x.get("reason")), level_badge(x.get("priority"))]
                for x in analysis["recommendations"]]
        body.append(section("Recommendations", table(["Action", "Why", "Priority"], rows)))
    if analysis.get("next_steps"):
        body.append(section("Next steps", doc_list(analysis["next_steps"])))
    body.append(section("How it is chosen", doc_list([
        "Essential: the story is in the change (through the commit key, the PR or the request) or the case strongly matches what changed (score 60 or more).",
        "Recommended: the case shares concepts with the change (files, functions, commits, notes), with synonyms in English and Spanish.",
        "Minimal regression: the smoke cases (@smoke) and the Critical priority ones, which always run.",
        "The score adds up the affected story (60), the concept match (up to 45), the priority (up to 15), whether it failed last time (10), whether it is flaky (6) and whether the story has open bugs (5).",
        "It is an aid for deciding, not a replacement for judgment: the agent's analysis can move cases between groups (it is noted in Why).",
    ])))

    if hist_html:
        body.append(hist_html)
    meta_html = meta([("Selection", data.get("name")), ("Date", (data.get("date") or "")[:16].replace("T", " ")),
                      ("Budget", f'{data["budget_min"]} min' if data.get("budget_min") else None),
                      ("Risk", risk)])
    return page("Case selection", "What to test in this change", meta_html, CSS_EXTRA + CSS_SEL + "".join(body) + JS_SEL)


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Case selection HTML report from selection.json")
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
    hist_html = _history.section("selection", Path(a.data_json).resolve().parent, data)
    with open(a.output, "w", encoding="utf-8") as f:
        f.write(build_html(data, analysis, hist_html=hist_html))
    print(f"OK: {a.output}")


if __name__ == "__main__":
    main()
