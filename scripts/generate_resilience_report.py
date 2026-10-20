#!/usr/bin/env python3
"""
Generates the Resilience report in HTML (dashboard, dark mode) from resilience.json
(npm run resilience) and, optionally, from the resilience-tester agent's analysis.

Usage:
    python scripts/generate_resilience_report.py <resilience.json> <output.html> [--analysis analysis.json]

What it shows: verdict, indicators (tests, how many hold up, with findings, blank screens, silent
failures, no recovery), the page × scenario matrix, the findings by type and by scenario, each
page with its normal load and the screenshot of each scenario (visible messages, retries, JavaScript
errors and recovery), the findings table, the Missing information and the evolution of the runs.

The analysis (optional) provides:
{
  "verdict": "...", "verdict_tone": "bad", "summary": "...",
  "findings": {"R-01": {"severity": "High", "note": "..."}},
  "discarded": [{"id": "R-05", "reason": "..."}],
  "manual": [{"id": "RM-01", "title": "...", "severity": "Medium", "scenario": "...", "page": "...",
                "steps": ["..."], "expected": "...", "actual": "...", "fix": "...",
                "evidence": "screenshots/manual/rm-01.png"}],
  "missing_info": [{"id": "MI-01", "what_is_missing": "...", "question": "..."}],   // "description" works as an alias of what_is_missing
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
from _report_styles import (missing_info, warn_analysis, e, page, meta, section, kpi_tiles, banner, doc_list, table, bar_chart, two_col,
                              level_badge, _pill, thumbnail, CRITICAL, WARNING, NEUTRAL, OK, SERIES)
from generate_exploratory_report import CSS_EXTRA

SEV = ["Critical", "High", "Medium", "Low"]

# "Evolution of the runs" section: registered here so the rest of the types are not touched.
_history.TYPES.setdefault("resilience", {
    "file": "resilience.json", "items": lambda d: d.get("findings") or [],
    "key": lambda h: f'{h.get("scenario")}|{h.get("type")}|{h.get("page")}',
    "title": lambda h: f'{h.get("scenario")} · {h.get("title")}',
    "metrics": [("Findings", _history._r("findings"), ""), ("Blank screens", _history._r("blank_screens"), ""),
                 ("Silent failures", _history._r("silent_failures"), ""), ("No recovery", _history._r("no_recovery"), "")]})

CSS_RE = """
<style>
.matrix td,.matrix th{text-align:center}
.matrix td:first-child,.matrix th:first-child{text-align:left}
.pag{border-top:1px solid var(--border-soft);padding:18px 24px}
.pag:first-child{border-top:0}
.pag h3{font-size:16px;color:var(--ink);display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
.escs{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px;margin-top:10px}
.esc{border:1px solid var(--border-soft);border-radius:12px;padding:10px}
.esc .thumb{display:grid;width:100%;height:170px;margin:6px 0}
.esc h4{font-size:13px;color:var(--ink);display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.esc ul{margin:4px 0 0 16px;font-size:12px;color:var(--muted)}
.discarded{opacity:.55}
</style>
"""

STATUS = {"ok": ("Holds up", OK, "✓"), "finding": ("With findings", CRITICAL, "✕"), "not-applicable": ("Not applicable", NEUTRAL, "–"), "error": ("Error", WARNING, "!")}


def status_pill(status, n=0):
    t, c, i = STATUS.get(status, (status, NEUTRAL, "?"))
    if status == "finding" and n:
        t = f"{n} finding(s)"
    return _pill(t, c, i)


def build_html(data, analysis, hist_html=""):
    adjustments = analysis.get("findings") or {}
    disc = {str(d.get("id")): d.get("reason") for d in analysis.get("discarded") or []}
    findings = []
    for h in data.get("findings") or []:
        h = dict(h)
        a = adjustments.get(h["id"]) or {}
        if a.get("severity") in SEV:
            h["severity"] = a["severity"]
        h["_note"], h["_disc"] = a.get("note"), disc.get(h["id"])
        findings.append(h)
    manual = analysis.get("manual") or []
    live = [h for h in findings if not h["_disc"]] + [dict(m, type="Manual exploration") for m in manual]
    r = data.get("summary") or {}
    pages = data.get("pages") or []
    scenarios = data.get("scenarios") or []
    serious = [h for h in live if h.get("severity") in ("Critical", "High")]
    with_result = r.get("tests", 0) - r.get("not_applicable", 0) - r.get("errors", 0)
    if not with_result:
        tone, text = "warn", "There were no applicable scenarios: the page makes no API calls and loads no resources that could fail"
    elif serious:
        tone, text = "bad", f"{len(serious)} serious problem(s): the interface goes blank or does not recover when something fails"
    elif live:
        tone, text = "warn", "The interface holds up under the failures, but the way it warns the user needs improvement"
    else:
        tone, text = "ok", "The interface holds up well under the simulated failures"
    body = [banner(analysis.get("verdict") or text, analysis.get("verdict_tone") or tone)]
    body.append('<div style="margin-top:20px">' + kpi_tiles([
        ("Tests", r.get("tests", 0), "", f'{r.get("pages", 0)} page(s) × {r.get("scenarios", 0)} scenario(s) · {r.get("not_applicable", 0)} not applicable', "target"),
        ("Hold up", r.get("ok", 0), "ok" if not r.get("with_findings") else "", f'{round(r.get("ok", 0) / with_result * 100) if with_result else 0} % of the applicable scenarios', "ok",
         {"pct": r.get("ok", 0) / with_result * 100 if with_result else 0}),
        ("With findings", r.get("with_findings", 0), ("bad" if serious else "warn") if r.get("with_findings") else "ok", "scenarios where something went wrong", "warn"),
        ("Blank", r.get("blank_screens", 0), "bad" if r.get("blank_screens") else "ok", "the screen is left almost empty", "bad"),
        ("Silent failures", r.get("silent_failures", 0), "warn" if r.get("silent_failures") else "ok", "something fails and the person does not find out", "bug"),
        ("No recovery", r.get("no_recovery", 0), "bad" if r.get("no_recovery") else "ok", "it does not work again when the network comes back", "bad"),
    ]) + "</div>")
    if analysis.get("summary"):
        body.append(section("Executive summary", f'<div class="cardbody"><p class="lead">{e(analysis["summary"])}</p></div>'))

    # Page × scenario matrix
    if pages and scenarios:
        rows = []
        for p in pages:
            by_scenario = {x["scenario"]: x for x in p.get("results") or []}
            cells = [f'<a href="#{e(p["id"])}" style="color:var(--ink)">{e(p["url"])}</a>']
            for s in scenarios:
                x = by_scenario.get(s["id"])
                cells.append(status_pill(x["status"], len(x.get("findings") or [])) if x else "—")
            rows.append(cells)
        body.append(section("Page × scenario matrix", f'<div class="matrix">{table(["Page"] + [e(s["name"]) for s in scenarios], rows)}</div>',
                            "what happened on each page with each simulated failure"))

    types = Counter(h["type"] for h in live)
    scenario_name = {s["id"]: s["name"] for s in scenarios}
    by_scenario = Counter(scenario_name.get(h.get("scenario"), h.get("scenario") or "Manual") for h in live)
    body.append(two_col(
        section("Problems by type", bar_chart([(t, k, SERIES[i % len(SERIES)]) for i, (t, k) in enumerate(types.most_common())], label_width=170)
                if types else '<p class="muted" style="padding:16px 24px">No problems.</p>'),
        section("Problems by scenario", bar_chart([(t, k, SERIES[(i + 2) % len(SERIES)]) for i, (t, k) in enumerate(by_scenario.most_common())], label_width=230)
                if by_scenario else '<p class="muted" style="padding:16px 24px">No problems.</p>')))

    blocks = []
    for p in pages:
        b = p.get("base") or {}
        cards = []
        if p.get("baseline_screenshot"):
            cards.append(f'<div class="esc"><h4>Normal load {_pill("baseline", NEUTRAL, "•")}</h4>{thumbnail(p["baseline_screenshot"], p["url"] + " · normal load")}'
                            f'<ul><li>{b.get("text_len", 0)} characters · {b.get("elements", 0)} elements</li>'
                            f'<li>{len(b.get("api_calls") or [])} API call(s) · {b.get("time_ms", 0)} ms</li></ul></div>')
        for x in p.get("results") or []:
            o = x.get("observed") or {}
            det = []
            if x["status"] in ("not-applicable", "error"):
                det.append(e(x.get("reason") or ""))
            else:
                det.append(f'{o.get("text_len", 0)} characters · {o.get("elements", 0)} elements · {x.get("intercepted", 0)} request(s) intercepted')
                det.append("Messages: " + (" · ".join(f"“{e(m)}”" for m in o.get("messages") or []) or "none"))
                if x.get("retries"):
                    det.append(f'Retries: {x["retries"]} ({e(x.get("url_retries"))})')
                if x.get("js_errors"):
                    det.append(f'JavaScript errors: {len(x["js_errors"])} · {e(x["js_errors"][0])}')
                rec = x.get("recovery") or {}
                if rec.get("recovers") is not None:
                    det.append("Recovers when the network comes back: " + ("yes" if rec["recovers"] else "<b>no</b>"))
                if x.get("note"):
                    det.append(e(x["note"]))
            img = thumbnail(x["screenshot"], f'{p["url"]} · {x["name"]}') if x.get("screenshot") else ""
            cards.append(f'<div class="esc"><h4>{e(x["name"])} {status_pill(x["status"], len(x.get("findings") or []))}</h4>{img}'
                            f'<ul>{"".join(f"<li>{d}</li>" for d in det)}</ul></div>')
        blocks.append(f'<div class="pag" id="{e(p["id"])}"><h3>{e(b.get("title") or p["url"])}</h3><p class="muted mono">{e(p["url"])}</p>'
                       f'<div class="escs">{"".join(cards)}</div></div>')
    if blocks:
        body.append(section("Each page", "".join(blocks), "the normal load and what was seen in each scenario"))

    if findings or manual:
        rows = [[e(h["id"]), level_badge(h["severity"]), e(h["type"]), e(scenario_name.get(h.get("scenario"), h.get("scenario"))),
                  f'<strong style="color:var(--ink)">{e(h["title"])}</strong><div class="muted">{e(h.get("detail"))}</div>'
                  + (f'<div><i>{e(h["_note"])}</i></div>' if h.get("_note") else "") + (f'<div class="muted">Discarded: {e(h["_disc"])}</div>' if h.get("_disc") else ""),
                  thumbnail(h["screenshot"], h["title"]) if h.get("screenshot") else "—"] for h in findings]
        rows += [[e(m.get("id")), level_badge(m.get("severity")), "Manual exploration", e(m.get("scenario")),
                   f'<strong style="color:var(--ink)">{e(m.get("title"))}</strong><div class="muted mono">{e(m.get("page") or "")}</div>'
                   f'<div class="muted">Steps: {e(" → ".join(map(str, m["steps"])) if isinstance(m.get("steps"), list) else m.get("steps"))}</div>'
                   f'<div class="muted">Expected: {e(m.get("expected"))} · Actual: {e(m.get("actual"))}</div>'
                   + (f'<div><b>How to fix it:</b> {e(m["fix"])}</div>' if m.get("fix") else ""),
                   thumbnail(m["evidence"], m.get("title")) if m.get("evidence") else "—"] for m in manual]
        body.append(section("Findings", table(["ID", "Severity", "Type", "Scenario", "Finding", "Evidence"], rows)))
    body.append(missing_info(analysis.get("missing_info"), "how the app must react to a failure, when no source defines it"))
    if analysis.get("recommendations"):
        rows = [[f'<strong style="color:var(--ink)">{e(x.get("action"))}</strong>', e(x.get("reason")), level_badge(x.get("priority"))]
                 for x in analysis["recommendations"]]
        body.append(section("Recommendations", table(["Action", "Why", "Priority"], rows)))
    if analysis.get("next_steps"):
        body.append(section("Next steps", doc_list(analysis["next_steps"])))
    if hist_html:
        body.append(hist_html)
    m = meta([("Story", data.get("story")), ("Site", data.get("host")), ("Date", (data.get("date") or "")[:16].replace("T", " ")),
              ("Wait per scenario", f'{round((data.get("timeout_ms") or 0) / 1000)} s'), ("API", data.get("api_pattern") or "fetch / XHR")])
    return page("Resilience", "Interface resilience", m, CSS_EXTRA + CSS_RE + "".join(body))


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Resilience HTML report from resilience.json")
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
        warn_analysis(analysis, [h.get("id") for h in data.get("findings") or []])
    hist_html = _history.section("resilience", Path(a.data_json).resolve().parent, data)
    with open(a.output, "w", encoding="utf-8") as f:
        f.write(build_html(data, analysis, hist_html=hist_html))
    print(f"OK: {a.output}")


if __name__ == "__main__":
    main()
