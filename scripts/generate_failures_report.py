#!/usr/bin/env python3
"""
Generates the Failure analysis report in HTML (dashboard, dark mode) from failures.json
(scripts/analyze_failures.py) and, optionally, from the failure-analyst agent's analysis.

Usage:
    python scripts/generate_failures_report.py <failures.json> <output.html> [--analysis analysis.json]

What it shows: verdict, indicators (scenarios, passed, with failures, possible bugs, flaky,
environment and automation), failures by cause, by suite and by story, the failures table with the
run history and the screenshot, and the detail of each one (failed step, error, likely cause,
what to do, screenshot, video and trace).

The analysis (optional) provides:
{
  "verdict": "2 real bugs; the rest are tests to stabilize", "verdict_tone": "bad",
  "summary": "Summary for a non-technical person...",
  "failures": {"F-01": {"category": "Possible bug", "cause": "The total does not add the shipping",
                        "action": "Report the bug", "bug": "BUG-004"}},
  "recommendations": [{"action": "...", "reason": "...", "priority": "High"}],
  "next_steps": ["..."]
}
Categories: Possible bug · Flaky · Locator or wait · Environment · Test data ·
Automation error · Undefined step · Unclassified
"""
import argparse
import json
from pathlib import Path
import sys

import _history
from _report_styles import (e, page, meta, section, kpi_tiles, banner, doc_list, table, bar_chart, donut_panel, two_col,
                            level_badge, _pill, CRITICAL, WARNING, NEUTRAL, OK, SERIES)
from generate_exploratory_report import CSS_EXTRA, JS_EXTRA, thumbnail

CATEGORIES = ["Possible bug", "Flaky", "Locator or wait", "Environment", "Test data",
              "Automation error", "Undefined step", "Unclassified"]
# Identity of each cause (categorical, fixed order): never status colors, which are for passed/failed.
COLOR = {c: SERIES[i] for i, c in enumerate(CATEGORIES)}
AUTOMATION = {"Locator or wait", "Automation error", "Undefined step", "Flaky"}

CSS_FAILURES = """
<style>
.err{background:#120F0B;border:1px solid var(--border);border-radius:10px;padding:12px 14px;white-space:pre-wrap;word-break:break-word;
  font-family:var(--mono);font-size:12px;color:#FFB8B0;max-height:320px;overflow:auto}
.runs{display:flex;gap:4px;flex-wrap:wrap}
.cat{display:inline-flex;align-items:center;gap:7px;font-size:12px;font-weight:650;padding:4px 11px;border-radius:999px;
  background:var(--tile);border:1px solid var(--border);color:var(--ink);white-space:nowrap}
.cat i{width:9px;height:9px;border-radius:3px}
.evid{display:flex;gap:12px;flex-wrap:wrap;align-items:flex-start}
.evid video{width:420px;max-width:100%;border-radius:10px;border:1px solid var(--border);background:#000}
</style>
"""


def cat_pill(c):
    return f'<span class="cat"><i style="background:{COLOR.get(c, NEUTRAL)}"></i>{e(c)}</span>'


def run_pill(status, name):
    if status == "Passed":
        return _pill(name, OK, "✓")
    if status == "Failed":
        return _pill(name, CRITICAL, "✕")
    return _pill(name, NEUTRAL, "–")


def build_html(data, analysis, hist_html=""):
    adjustments = analysis.get("failures") or {}
    failures = []
    for f in data.get("failures") or []:
        f = dict(f)
        a = adjustments.get(f["id"]) or {}
        if a.get("category") in CATEGORIES:
            f["category"] = a["category"]
        f["_analysis"] = a
        failures.append(f)
    r = data.get("summary") or {}
    runs = data.get("runs") or []
    count = {c: sum(1 for f in failures if f["category"] == c) for c in CATEGORIES}
    still = [f for f in failures if f.get("final_status") == "Failed"]
    bugs = count["Possible bug"]

    body = []
    if not failures:
        tone, text = "ok", "All the scenarios passed"
    elif not still:
        tone, text = "warn", "Everything passed on the retry: the failures were flakiness, not bugs"
    elif bugs:
        tone, text = "bad", f"{bugs} failure(s) with signs of a bug in the application"
    else:
        tone, text = "warn", "The failures point to the automation, the data or the environment, not to the application"
    body.append(banner(analysis.get("verdict") or text, analysis.get("verdict_tone") or tone))

    total = r.get("scenarios", 0)
    passed = r.get("passed", 0)
    body.append('<div style="margin-top:20px">' + kpi_tiles([
        ("Scenarios", total, "", f'{len(runs)} run(s): {", ".join(c["label"].lower() for c in runs)}', "list"),
        ("Passed", passed, "ok", f"{round(passed / total * 100) if total else 0} % of the total", "ok", {"pct": passed / total * 100 if total else 0}),
        ("With failures", len(failures), "bad" if still else ("warn" if failures else "ok"), f"{len(still)} still failing", "bad"),
        ("Possible bugs", bugs, "bad" if bugs else "ok", "the app responded differently than expected", "bug"),
        ("Flaky", count["Flaky"], "warn" if count["Flaky"] else "ok", "they failed and then passed", "warn"),
        ("Automation", sum(count[c] for c in AUTOMATION - {"Flaky"}),
         "warn" if any(count[c] for c in AUTOMATION) else "ok", "locators, waits, code and undefined steps", "code"),
        ("Environment and data", count["Environment"] + count["Test data"], "warn" if count["Environment"] + count["Test data"] else "ok",
         "infrastructure down or test data", "screen"),
        ("Unclassified", count["Unclassified"], "warn" if count["Unclassified"] else "", "review by hand", "search"),
    ]) + "</div>")

    if analysis.get("summary"):
        body.append(section("Executive summary", f'<div class="cardbody"><p class="lead">{e(analysis["summary"])}</p></div>'))

    if failures:
        segs = [(count[c], COLOR[c], c) for c in CATEGORIES if count[c]]
        main_seg = max(segs, key=lambda s: s[0])
        body.append(two_col(section("Failures by likely cause", donut_panel(segs, round(main_seg[0] / len(failures) * 100), main_seg[2][:14].lower()),
                                    "heuristic based on the error; the analyst confirms it"),
                            section("Failures by suite and by story",
                                    bar_chart([(f'Suite {s}', n, SERIES[2]) for s, n in (r.get("by_suite") or {}).items()]
                                              + sorted([(h, sum(1 for f in failures if f.get("story") == h), SERIES[0])
                                                        for h in {f.get("story") or "No story" for f in failures}], key=lambda x: -x[1]),
                                              label_width=150))))

        rows = []
        for f in failures:
            first = next((l for l in (f.get("error") or "").splitlines() if l.strip()), "")
            cap = next((x["file"] for x in f.get("evidence") or [] if x["type"] == "screenshot"), None)
            hist = "".join(run_pill(s, c["id"]) for s, c in zip(f.get("history") or [], runs))
            ident = " · ".join(x for x in [f.get("story"), f.get("case"), f.get("suite")] if x)
            rows.append([f'<a class="id" href="#{e(f["id"])}" style="color:var(--ink)">{e(f["id"])}</a>', cat_pill(f["category"]),
                         f'<strong style="color:var(--ink)">{e(f["scenario"])}</strong><div class="muted">{e(ident)}</div>',
                         f'<span class="mono">{e(f.get("failed_step") or "—")}</span><div class="muted mono">{e(first[:160])}</div>',
                         f'<div class="runs">{hist}</div>', thumbnail(cap, f["scenario"], "s")])
        body.append(section("Scenarios with failures", table(["ID", "Likely cause", "Scenario", "Step and error", "Runs", "Screenshot"], rows),
                            "click the ID to see the detail"))

        det = []
        for f in failures:
            a = f["_analysis"]
            caps = [x for x in f.get("evidence") or [] if x["type"] == "screenshot"]
            vids = [x for x in f.get("evidence") or [] if x["type"] == "video"]
            trs = [x for x in f.get("evidence") or [] if x["type"] == "trace"]
            evid = "".join(thumbnail(x["file"], f["scenario"]) for x in caps[:4])
            evid += "".join(f'<video controls preload="metadata" src="{e(x["file"])}#t=0.5"></video>' for x in vids[:1])
            trace = "".join(f'<li><a href="{e(x["file"])}" download style="color:var(--ink)">{e(x["file"].split("/")[-1])}</a> · '
                            f'open it in <a href="https://trace.playwright.dev" target="_blank" rel="noopener" style="color:var(--ink)">trace.playwright.dev</a> '
                            f'to see each action, the network and the console</li>' for x in trs)
            hist = "".join(run_pill(s, f'{c["id"]} · {c["label"]}') for s, c in zip(f.get("history") or [], runs))
            det.append(f'''<div class="finding" id="{e(f["id"])}"><h3>{e(f["id"])} · {e(f["scenario"])} {cat_pill(f["category"])}</h3>
              <p class="muted mono">{e(f.get("uri"))}:{e(f.get("line"))} · {e(" · ".join(x for x in [f.get("story"), f.get("case"), "suite " + f["suite"]] if x))} · {e(f.get("duration_s"))} s</p>
              <div class="lbl">Runs</div><div class="runs">{hist}</div>
              <div class="lbl">Failed step</div><p class="mono" style="color:var(--ink)">{e(f.get("failed_step") or "—")}</p>
              {f'<div class="lbl">Error</div><div class="err">{e(chr(10).join((f.get("error") or "").splitlines()[:30]))}</div>' if f.get("error") else ""}
              <div class="lbl">Likely cause</div><p>{e(a.get("cause") or f.get("suggestion"))}</p>
              {f'<p class="muted">Matched: <span class="mono">{e(f["match"])}</span></p>' if f.get("match") and not a.get("cause") else ""}
              {f'<div class="lbl">What to do</div><p>{e(a["action"])}</p>' if a.get("action") else ""}
              {f'<div class="lbl">Bug</div><p class="mono" style="color:var(--ink)">{e(a["bug"])}</p>' if a.get("bug") else ""}
              {f'<div class="lbl">Evidence</div><div class="evid">{evid}</div>' if evid else ""}
              {f'<div class="lbl">Trace</div><ul>{trace}</ul>' if trace else ""}</div>''')
        body.append(section("Detail of each failure", "".join(det)))

    rows = [[e(c["id"]), e(c["label"]), e((c.get("date") or "").replace("T", " ")), e(", ".join(c.get("suites") or []))] for c in runs]
    body.append(section("Runs analyzed", table(["Run", "Type", "Date", "Suites"], rows),
                        "the original one and the retries of the scenarios that failed"))
    if analysis.get("recommendations"):
        rows = [[f'<strong style="color:var(--ink)">{e(x.get("action"))}</strong>', e(x.get("reason")), level_badge(x.get("priority"))]
                for x in analysis["recommendations"]]
        body.append(section("Recommendations", table(["Action", "Why", "Priority"], rows)))
    if analysis.get("next_steps"):
        body.append(section("Next steps", doc_list(analysis["next_steps"])))

    if hist_html:
        body.append(hist_html)
    meta_html = meta([("Story", data.get("story")), ("Date", (data.get("date") or "")[:16].replace("T", " ")),
                      ("Suites", ", ".join(data.get("suites") or [])), ("Tool", "k0lmena · npm test")])
    return page("Failure analysis", "Failure analysis", meta_html, CSS_EXTRA + CSS_FAILURES + "".join(body) + JS_EXTRA)


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="HTML failure analysis report from failures.json")
    ap.add_argument("failures_json")
    ap.add_argument("output")
    ap.add_argument("--analysis")
    a = ap.parse_args()
    if not a.output.lower().endswith(".html"):
        sys.exit("The output must end in .html")
    with open(a.failures_json, encoding="utf-8") as f:
        data = json.load(f)
    analysis = {}
    if a.analysis:
        with open(a.analysis, encoding="utf-8") as f:
            analysis = json.load(f)
    hist_html = _history.section("failures", Path(a.failures_json).resolve().parent, data)
    with open(a.output, "w", encoding="utf-8") as f:
        f.write(build_html(data, analysis, hist_html=hist_html))
    print(f"OK: {a.output}")


if __name__ == "__main__":
    main()
