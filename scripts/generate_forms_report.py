#!/usr/bin/env python3
"""
Generates the Form validations report in HTML (dashboard, dark mode) from forms.json
(npm run forms) and, optionally, from the form-tester agent's analysis.

Usage:
    python scripts/generate_forms_report.py <forms.json> <output.html> [--analysis analysis.json]

What it shows: verdict, indicators (forms, fields, tests, percentage that passes, invalid values
accepted, valid values rejected, findings), the tests per field, the problems by type, each
form with the screenshot before and with the errors in sight and the field × test matrix (value, what was
expected, what happened and the message), the findings table and the evolution of the runs.

The analysis (optional) provides:
{
  "verdict": "...", "verdict_tone": "bad", "summary": "...",
  "findings": {"V-01": {"severity": "High", "note": "..."}},
  "discarded": [{"id": "V-12", "reason": "..."}],
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
from _report_styles import (missing_info, warn_analysis, e, page, meta, section, kpi_tiles, banner, doc_list, table, bar_chart, stacked_bars, two_col,
                            level_badge, _pill, thumbnail, CRITICAL, WARNING, NEUTRAL, OK, SERIES)
from generate_exploratory_report import CSS_EXTRA

SEV = ["Critical", "High", "Medium", "Low"]
RES = {"rejects": "Rejects", "accepts": "Accepts", "truncates": "Truncates"}

CSS_FORMS = """
<style>
.form{border-top:1px solid var(--border-soft);padding:18px 24px}
.form:first-child{border-top:0}
.form h3{font-size:16px;color:var(--ink);display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
.screenshots{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:8px 0 14px}
.screenshots figure{margin:0}
.screenshots figcaption{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:600;margin-bottom:6px}
.screenshots .thumb{display:grid;width:100%;height:260px}
.field{font-weight:650;color:var(--ink)}
.field small{display:block;font-weight:400;color:var(--muted);font-family:var(--mono);font-size:11.5px}
.discarded{opacity:.55}
</style>
"""


def res_pill(p):
    if p["ok"] is None:
        return _pill(RES.get(p["result"], p["result"]) + " · informational", NEUTRAL, "–")
    return _pill(RES.get(p["result"], p["result"]), OK if p["ok"] else CRITICAL, "✓" if p["ok"] else "✕")


def build_html(data, analysis, hist_html=""):
    adjustments = analysis.get("findings") or {}
    desc = {str(d.get("id")): d.get("reason") for d in analysis.get("discarded") or []}
    findings = []
    for h in data.get("findings") or []:
        h = dict(h)
        a = adjustments.get(h["id"]) or {}
        if a.get("severity") in SEV:
            h["severity"] = a["severity"]
        h["_note"], h["_desc"] = a.get("note"), desc.get(h["id"])
        findings.append(h)
    live = [h for h in findings if not h["_desc"]]
    r = data.get("summary") or {}
    forms = data.get("forms") or []
    serious = [h for h in live if h["severity"] in ("Critical", "High")]
    if not forms:
        tone, text = "warn", "I found no forms in the pages reviewed"
    elif serious:
        tone, text = "bad", f'{len(serious)} serious problem(s): the form accepts invalid data or rejects valid data'
    elif live:
        tone, text = "warn", "The validations work; there are details in messages, labels and field types"
    else:
        tone, text = "ok", "The forms validate well"
    body = [banner(analysis.get("verdict") or text, analysis.get("verdict_tone") or tone)]
    n = r.get("tests", 0)
    with_res = n - sum(1 for f in forms for c in f["fields"] for p in c["tests"] if p["ok"] is None)
    body.append('<div style="margin-top:20px">' + kpi_tiles([
        ("Forms", r.get("forms", 0), "", f'{r.get("fields", 0)} fields in {r.get("pages", 0)} page(s)', "list"),
        ("Tests", n, "", "without submitting anything: fill in, leave the field and look", "target"),
        ("Passing", r.get("tests_ok", 0), "ok" if not r.get("tests_failing") else "", f'{round(r.get("tests_ok", 0) / with_res * 100) if with_res else 0} % of the tests with the expected result', "ok",
         {"pct": r.get("tests_ok", 0) / with_res * 100 if with_res else 0}),
        ("Accepts invalid", r.get("accepts_invalid", 0), "bad" if r.get("accepts_invalid") else "ok", "incorrect data that would reach the database", "bad"),
        ("Rejects valid", r.get("rejects_valid", 0), "bad" if r.get("rejects_valid") else "ok", "people who cannot complete the form", "bug"),
        ("Findings", len(live), "bad" if serious else ("warn" if live else "ok"), f"{len(serious)} serious", "warn"),
    ]) + "</div>")
    if analysis.get("summary"):
        body.append(section("Executive summary", f'<div class="cardbody"><p class="lead">{e(analysis["summary"])}</p></div>'))
    rows = [(f'{c.get("label") or c["name"]}'[:30], [sum(1 for p in c["tests"] if p["ok"] is True), sum(1 for p in c["tests"] if p["ok"] is False)])
            for f in forms for c in f["fields"] if c["tests"]]
    types = Counter(h["type"] for h in live)
    body.append(two_col(section("Tests per field", stacked_bars(rows, [("Pass", OK), ("Fail", CRITICAL)]) if rows else '<p class="muted" style="padding:16px 24px">—</p>'),
                        section("Problems by type", bar_chart([(t, k, SERIES[i % len(SERIES)]) for i, (t, k) in enumerate(types.most_common())], label_width=170)
                                if types else '<p class="muted" style="padding:16px 24px">No problems.</p>')))
    blocks = []
    for f in forms:
        caps = ""
        for lbl, k in (("Before", "screenshot"), ("With the invalid values", "errors_screenshot"), ("When submitted empty", "empty_submit_screenshot")):
            if f.get(k):
                caps += f'<figure><figcaption>{e(lbl)}</figcaption>{thumbnail(f[k], f["id"] + " · " + lbl)}</figure>'
        rows = []
        for c in f["fields"]:
            restr = " · ".join(x for x in [c["type"], "required" if c["required"] else "", f'max {c["maxlength"]}' if c.get("maxlength") else "",
                                           f'min {c["minlength"]}' if c.get("minlength") else "", f'range {c.get("min")}–{c.get("max")}' if c.get("min") is not None or c.get("max") is not None else ""] if x)
            field = f'<div class="field">{e(c.get("label") or c["name"])}<small>{e(restr)}</small></div>'
            if not c["tests"]:
                rows.append([field, '<span class="muted">no tests for this type</span>', "", "", "", ""])
            for i, p in enumerate(c["tests"]):
                rows.append([field if i == 0 else "", e(p["rule"]), f'<span class="mono">{e(p["value"])}</span>', e(p["expected"]), res_pill(p),
                             e(p.get("message") or "—") + (f' <span class="muted">({e(p["source"])})</span>' if p.get("source") else "")])
        extra = f'<p class="muted">After submitting it empty it stayed on <span class="mono">{e(f.get("url_after_submit"))}</span></p>' if f.get("url_after_submit") else ""
        color = CRITICAL if any(h["severity"] in ("High", "Critical") for h in f["findings"]) else WARNING if f["findings"] else OK
        status = _pill("%d finding(s)" % len(f["findings"]), color, "!" if f["findings"] else "✓")
        blocks.append(f'<div class="form" id="{e(f["id"])}"><h3>{e(f["id"])} · {e(f["name"])} <span class="muted mono">{e(f.get("method") or "")} {e(f.get("action") or "")}</span>'
                      f'{status}</h3>'
                      f'<p class="muted mono">{e(f["url"])}</p><div class="screenshots">{caps}</div>{extra}'
                      f'{table(["Field", "Test", "Value", "Expected", "Result", "Message"], rows)}</div>')
    if blocks:
        body.append(section("Each form", "".join(blocks), "field × test: what was tested, what was expected and what the form did"))
    if findings:
        rows = [[e(h["id"]), level_badge(h["severity"]), e(h["type"]),
                 f'<strong style="color:var(--ink)">{e(h["title"])}</strong><div class="muted">{e(h.get("detail"))}</div>'
                 + (f'<div><i>{e(h["_note"])}</i></div>' if h.get("_note") else "") + (f'<div class="muted">Discarded: {e(h["_desc"])}</div>' if h.get("_desc") else ""),
                 f'<a href="#{e(h["form"])}" style="color:var(--ink)">{e(h["form"])}</a>'] for h in findings]
        body.append(section("Findings", table(["ID", "Severity", "Type", "Finding", "Form"], rows)))
    body.append(missing_info(analysis.get("missing_info")))
    if analysis.get("recommendations"):
        rows = [[f'<strong style="color:var(--ink)">{e(x.get("action"))}</strong>', e(x.get("reason")), level_badge(x.get("priority"))]
                for x in analysis["recommendations"]]
        body.append(section("Recommendations", table(["Action", "Why", "Priority"], rows)))
    if analysis.get("next_steps"):
        body.append(section("Next steps", doc_list(analysis["next_steps"])))
    if hist_html:
        body.append(hist_html)
    m = meta([("Story", data.get("story")), ("Site", data.get("host")), ("Date", (data.get("date") or "")[:16].replace("T", " ")),
              ("Empty submit", "yes" if data.get("empty_submit") else "no")])
    return page("Forms", "Form validations", m, CSS_EXTRA + CSS_FORMS + "".join(body))


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="HTML forms report from forms.json")
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
    hist_html = _history.section("forms", Path(a.data_json).resolve().parent, data)
    with open(a.output, "w", encoding="utf-8") as f:
        f.write(build_html(data, analysis, hist_html=hist_html))
    print(f"OK: {a.output}")


if __name__ == "__main__":
    main()
