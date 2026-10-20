#!/usr/bin/env python3
"""
Generates the automation repair HTML report (dashboard, dark mode) from
repairs.json (npm run repair) and, optionally, from the analysis of the automation-repairer agent.

Usage:
    python scripts/generate_repair_report.py <repairs.json> <output.html> [--analysis analysis.json]

What it shows: verdict, indicators (failures analyzed, with proposal, applied, verified, still
failing, possible bugs and waits), the repair funnel (analyzed → with proposal →
applied → verified), the diagnoses, the repairs table and the detail of each one: the
step and the error, where the locator is (file and line), the proposed or applied change as a diff,
the candidates with their score, the DOM screenshot with the original element (red) and the proposed one
(green), the risk (if it may be a bug) and the verification result; at the end, the full diff.

The analysis (optional) provides:
{
  "verdict": "2 locators repaired and verified; 1 possible bug", "verdict_tone": "warn",
  "summary": "Summary for a non-technical person...",
  "repairs": {"R-01": {"decision": "Possible bug", "note": "The story asks for the coupons section"}},
  "recommendations": [{"action": "...", "reason": "...", "priority": "High"}],
  "next_steps": ["..."]
}
Decisions: Apply · Possible bug · Manual fix · Discard
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import _history
from _report_styles import (e, page, meta, section, kpi_tiles, banner, doc_list, table, bar_chart, donut_panel, two_col,
                              level_badge, _pill, thumbnail, CRITICAL, WARNING, NEUTRAL, OK, SERIOUS, SERIES)
from generate_exploratory_report import CSS_EXTRA

STATUS = {"Verified": (OK, "✓"), "Applied": (SERIES[2], "●"), "Proposed": (WARNING, "◷"), "Still failing": (CRITICAL, "✕"),
          "No proposal": (NEUTRAL, "–"), "No result": (NEUTRAL, "?")}
CONFIDENCE = {"High": (OK, "▲"), "Medium": (WARNING, "●"), "Low": (SERIOUS, "▼")}
DIAGNOSES = ["No longer exists", "Matches several", "Exists but not visible", "Exists and visible", "No saved DOM", "No locator in the error"]
DIAG_COLOR = {d: SERIES[i] for i, d in enumerate(DIAGNOSES)}
WHAT_IT_IS = {
    "No longer exists": "the locator finds nothing: the text, the role or the attribute changed",
    "Matches several": "it finds more than one element: it has to be made more specific",
    "Exists but not visible": "it is hidden: a previous step is missing or the app does not show it",
    "Exists and visible": "the locator is fine: the wait or the verification failed",
    "No saved DOM": "there is no DOM of the failure to analyze",
    "No locator in the error": "it is not a locator failure",
}

CSS_RPR = """
<style>
.diff{margin:6px 0 4px;border:1px solid var(--border);border-radius:10px;overflow:auto;background:#120F0B;
  font-family:var(--mono);font-size:12.5px;line-height:1.65}
.diff div{padding:1px 14px;white-space:pre}
.diff .h{color:var(--muted);background:rgba(244,239,230,.03)}
.diff .del{background:rgba(255,90,78,.16);color:#FFB8B0}
.diff .add{background:rgba(92,191,74,.16);color:#C6EDB9}
.diff .ctx{color:var(--body)}
.err{background:#120F0B;border:1px solid var(--border);border-radius:10px;padding:12px 14px;white-space:pre-wrap;word-break:break-word;
  font-family:var(--mono);font-size:12px;color:#FFB8B0;max-height:220px;overflow:auto}
.code{font-family:var(--mono);font-size:12px;color:var(--ink);background:var(--tile);border:1px solid var(--border);
  border-radius:7px;padding:3px 8px;display:inline-block;word-break:break-all}
.code.old{color:#FFB8B0;text-decoration:line-through;text-decoration-color:rgba(255,184,176,.5)}
.code.new{color:#C6EDB9}
.arrow{color:var(--muted);margin:0 6px}
.score{display:flex;align-items:center;gap:8px;min-width:120px}
.score .t{flex:1;height:6px;border-radius:99px;background:rgba(244,239,230,.06);overflow:hidden}
.score .t span{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,rgba(249,176,6,.5),#F9B006)}
.score b{font-family:var(--mono);font-size:12px;color:var(--ink);min-width:26px;text-align:right}
.warning{border:1px solid rgba(255,214,10,.35);background:rgba(255,214,10,.07);border-radius:10px;padding:10px 14px;color:#FFE58A;margin-top:10px}
.screenshots{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:8px}
.screenshots figure{margin:0}
.screenshots figcaption{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:600;margin-bottom:6px}
.screenshots img{display:block;width:100%;max-height:320px;object-fit:contain;object-position:left top;border-radius:8px;border:1px solid var(--border);background:#fff}
.cmd{font-family:var(--mono);font-size:12.5px;color:var(--ink)}
@media (max-width:720px){.screenshots{grid-template-columns:1fr}}
</style>
"""


ANSI = re.compile(r"\x1b\[[0-9;]*m")  # terminal colors in the Playwright errors


def pill(mapping, value):
    color, ic = mapping.get(value, (NEUTRAL, "●"))
    return _pill(value or "—", color, ic)


def score(p):
    return f'<div class="score"><div class="t"><span style="width:{max(0, min(100, p or 0))}%"></span></div><b>{e(p)}</b></div>'


def preview(r):
    """Line before and after (the applied one or the one it would become if applied)."""
    if r.get("applied"):
        return r["applied"]["before"], r["applied"]["after"]
    u, prop = r.get("location") or {}, r.get("proposal") or {}
    if not u or not prop:
        return None, None
    before = u.get("text") or ""
    if u.get("type") == "feature":
        inp = prop.get("input") or {}
        new = next((inp[k] for k in ("name", "text", "label", "placeholder", "testId") if k in inp), None)
        return before, before.replace(f'"{u.get("value")}"', f'"{new}"') if new else None
    objs = re.findall(r"\{[^{}]*\}", before)
    vals = [v for v in ((r.get("locator") or {}).get("input") or {}).values() if isinstance(v, str)]
    obj = next((o for o in objs if all(v in o for v in vals)), None)
    return before, before.replace(obj, prop["code"]) if obj else None


def diff_html(before, after, title=""):
    rows = [f'<div class="h">{e(title)}</div>'] if title else []
    rows += [f'<div class="del">- {e(before)}</div>', f'<div class="add">+ {e(after)}</div>']
    return f'<div class="diff">{"".join(rows)}</div>'


def full_diff(text):
    rows = []
    for l in text.splitlines():
        cls = "h" if l.startswith(("---", "+++", "@@")) else "del" if l.startswith("-") else "add" if l.startswith("+") else "ctx"
        rows.append(f'<div class="{cls}">{e(l) or "&nbsp;"}</div>')
    return f'<div class="cardbody"><div class="diff">{"".join(rows)}</div></div>'


def detail(r, a):
    u = r.get("location") or {}
    loc = r.get("locator") or {}
    prop = r.get("proposal") or {}
    status = (r.get("verification") or {}).get("status") or r.get("status") or ("Proposed" if prop else "No proposal")
    parts = [f'<div class="finding" id="{e(r["id"])}"><h3>{e(r["id"])} · {e(r["scenario"])} {pill(STATUS, status)}'
             f'{" " + pill(CONFIDENCE, prop.get("confidence")) if prop else ""}</h3>',
             f'<p class="muted mono">{e(" · ".join(x for x in [r.get("story"), r.get("case"), r.get("uri")] if x))}:{e(r.get("line"))}</p>',
             f'<div class="lbl">Step that failed ({e(r.get("action"))})</div><p class="mono" style="color:var(--ink)">{e(r.get("step") or "—")}</p>']
    if r.get("error"):
        parts.append(f'<div class="lbl">Error</div><div class="err">{e(chr(10).join(ANSI.sub("", r["error"]).splitlines()[:8]))}</div>')
    parts.append(f'<div class="lbl">Diagnosis · {e(r.get("diagnosis"))}</div><p>{e(r.get("detail"))}</p>')
    if loc:
        parts.append(f'<div class="lbl">Locator</div><p><span class="code old">{e(loc.get("code"))}</span>'
                     + (f'<span class="arrow">→</span><span class="code new">{e(prop.get("code"))}</span>' if prop else "") + "</p>")
    if prop.get("reasons"):
        parts.append(f'<p class="muted">Why: {e("; ".join(prop["reasons"]))}</p>')
    if u:
        where = f'{u.get("file")}:{u.get("line")}' + (f' · key {u["key"]}' if u.get("key") else "")
        kind = {"locator": "locators file", "feature": ".feature data", "step": "written in a step"}.get(u.get("type"), u.get("type"))
        parts.append(f'<div class="lbl">Where it is ({e(kind)})</div><p class="mono">{e(where)}</p>')
        before, after = preview(r)
        if before and after:
            parts.append(diff_html(before, after, "applied change" if r.get("applied") else "proposed change (not applied yet)"))
    elif loc:
        parts.append('<div class="warning">I could not find where the locator is (it may be built at runtime): change it by hand.</div>')
    if r.get("risk"):
        parts.append(f'<div class="warning">⚠ {e(r["risk"])}</div>')
    if r.get("wait_suggestion"):
        parts.append(f'<div class="lbl">What to do</div><p>{e(r["wait_suggestion"])}</p>')
    if a.get("decision") or a.get("note"):
        parts.append(f'<div class="lbl">Analysis decision</div><p><strong style="color:var(--ink)">{e(a.get("decision") or "")}</strong> {e(a.get("note") or "")}</p>')
    caps = ""
    if r.get("original_screenshot"):
        caps += f'<figure><figcaption>What the original locator finds</figcaption><a class="lb" href="{e(r["original_screenshot"])}" title="{e(r["id"])} · original"><img src="{e(r["original_screenshot"])}" loading="lazy" alt="Original"></a></figure>'
    if r.get("screenshot"):
        caps += f'<figure><figcaption>Proposed element</figcaption><a class="lb" href="{e(r["screenshot"])}" title="{e(r["id"])} · proposal"><img src="{e(r["screenshot"])}" loading="lazy" alt="Proposal"></a></figure>'
    if caps:
        parts.append(f'<div class="lbl">On the page saved at the failure</div><div class="screenshots">{caps}</div>')
    if r.get("candidates"):
        rows = []
        for c in r["candidates"][:6]:
            best = c.get("best") or {}
            rows.append([score(c.get("score")), e(c.get("role") or c.get("tag")), f'<span style="color:var(--ink)">{e((c.get("name") or c.get("text") or "")[:60])}</span>',
                         f'<span class="code">{e(best.get("code") or "—")}</span>', "Yes" if best else "No", e(", ".join(c.get("reasons") or []))])
        parts.append('<div class="lbl">Candidates on the page</div>' + table(["Score", "Role", "Name", "Locator", "Unique", "Why"], rows))
    if r.get("alternatives") and len(r["alternatives"]) > 1:
        parts.append('<div class="lbl">Alternatives (one per element)</div><ul>' + "".join(
            f'<li><span class="code">{e(x["code"])}</span> <span class="muted">· {e(x.get("reference"))}</span></li>' for x in r["alternatives"][:8]) + "</ul>")
    v = r.get("verification")
    if v:
        parts.append(f'<div class="lbl">Verification</div><p>{pill(STATUS, v.get("status"))} <span class="muted">{e((v.get("date") or "")[:16].replace("T", " "))}</span></p>')
        if v.get("error"):
            parts.append(f'<div class="err">{e(chr(10).join(ANSI.sub("", v["error"]).splitlines()[:8]))}</div>')
    parts.append("</div>")
    return "".join(parts)


def build_html(data, analysis, folder=None, hist_html=""):
    rs = data.get("repairs") or []
    r = data.get("summary") or {}
    adjustments = analysis.get("repairs") or {}
    body = []
    n = r.get("failures", len(rs))
    ver, still, appl, prop = r.get("verified", 0), r.get("still_failing", 0), r.get("applied", 0), r.get("with_proposal", 0)
    if not n:
        tone, text = "ok", "There are no web failures to repair"
    elif still:
        tone, text = "bad", f"{still} applied repair(s) still failing"
    elif ver and ver == appl:
        tone, text = "ok", f"{ver} repair(s) applied and verified" + (f"; {n - ver} failure(s) left to review" if n > ver else "")
    elif appl:
        tone, text = "warn", f"{appl} repair(s) applied, still to be verified (npm run repair -- --verify)"
    elif prop:
        tone, text = "warn", f"{prop} of {n} failure(s) have a proposed repair, not applied yet"
    else:
        tone, text = "warn", "No automatic repairs are possible: review the detail of each failure"
    body.append(banner(analysis.get("verdict") or text, analysis.get("verdict_tone") or tone))
    body.append('<div style="margin-top:20px">' + kpi_tiles([
        ("Failures analyzed", n, "", f'{r.get("locator_failures", 0)} locator · source: {data.get("source_type", "")}', "search"),
        ("With proposal", prop, "ok" if prop and prop == r.get("locator_failures") else ("warn" if prop else ""),
         f'{r.get("high_confidence", 0)} with high confidence', "key", {"pct": prop / n * 100 if n else 0}),
        ("Applied", appl, "" if not appl else "ok", "changes written to the code", "code"),
        ("Verified", ver, "ok" if ver and ver == appl else ("warn" if appl else ""), "pass after being repaired", "ok", {"pct": ver / appl * 100 if appl else 0}),
        ("Still failing", still, "bad" if still else "ok", "applied ones that were not enough", "bad"),
        ("Possible bugs", r.get("possible_bugs", 0), "warn" if r.get("possible_bugs") else "ok", "verifications that do not find the element", "bug"),
        ("Waits", r.get("wait", 0), "warn" if r.get("wait") else "", "the locator is fine: the timing failed", "clock"),
        ("No proposal", r.get("no_proposal", 0), "warn" if r.get("no_proposal") else "ok", "review by hand", "list"),
    ]) + "</div>")
    if analysis.get("summary"):
        body.append(section("Executive summary", f'<div class="cardbody"><p class="lead">{e(analysis["summary"])}</p></div>'))

    if rs:
        count = Counter(x.get("diagnosis") for x in rs)
        segs = [(count[d], DIAG_COLOR[d], d) for d in DIAGNOSES if count[d]]
        main_seg = max(segs, key=lambda s: s[0])
        funnel = bar_chart([("Analyzed", n, SERIES[2]), ("With proposal", prop, SERIES[1]), ("Applied", appl, SERIES[4]), ("Verified", ver, OK)],
                           label_width=130)
        body.append(two_col(section("Repair funnel", funnel, "from the failure to the test that passes again"),
                            section("Diagnoses", donut_panel(segs, round(main_seg[0] / len(rs) * 100), main_seg[2][:16].lower()))))
        rows = []
        for x in rs:
            loc = (x.get("locator") or {}).get("code")
            p = (x.get("proposal") or {}).get("code")
            change = (f'<span class="code old">{e(loc)}</span>' if loc else '<span class="muted">—</span>') + \
                (f'<div style="margin-top:6px"><span class="code new">{e(p)}</span></div>' if p else "")
            status = (x.get("verification") or {}).get("status") or x.get("status") or "No proposal"
            rows.append([f'<a class="id" href="#{e(x["id"])}" style="color:var(--ink)">{e(x["id"])}</a>',
                         f'<strong style="color:var(--ink)">{e(x["scenario"])}</strong><div class="muted">{e(" · ".join(y for y in [x.get("story"), x.get("case")] if y))}</div>',
                         f'<span class="cat"><i style="background:{DIAG_COLOR.get(x.get("diagnosis"), NEUTRAL)}"></i>{e(x.get("diagnosis"))}</span>'
                         f'<div class="muted" style="margin-top:4px">{e(WHAT_IT_IS.get(x.get("diagnosis"), ""))}</div>',
                         change, pill(CONFIDENCE, (x.get("proposal") or {}).get("confidence")) if x.get("proposal") else '<span class="muted">—</span>',
                         pill(STATUS, status)])
        body.append(section("Repairs", table(["ID", "Scenario", "Diagnosis", "Locator → proposal", "Confidence", "Status"], rows),
                            "click the ID to see the detail, the screenshots and the change"))
        body.append(section("Detail of each repair", "".join(detail(x, adjustments.get(x["id"]) or {}) for x in rs)))

    if folder and (Path(folder) / "changes.diff").exists():
        text = (Path(folder) / "changes.diff").read_text(encoding="utf-8").strip()
        if text:
            body.append(section("Applied changes (diff)", full_diff(text), "copy of the original files in backup/"))

    if analysis.get("recommendations"):
        rows = [[f'<strong style="color:var(--ink)">{e(x.get("action"))}</strong>', e(x.get("reason")), level_badge(x.get("priority"))]
                for x in analysis["recommendations"]]
        body.append(section("Recommendations", table(["Action", "Why", "Priority"], rows)))
    if analysis.get("next_steps"):
        body.append(section("Next steps", doc_list(analysis["next_steps"])))
    us = f' --story {data["story"]}' if data.get("story") else ""
    rows = [["Apply the high-confidence ones in action steps", f'<span class="cmd">npm run repair -- --apply safe{e(us)}</span>'],
            ["Apply some in particular", f'<span class="cmd">npm run repair -- --apply R-01,R-03{e(us)}</span>'],
            ["Verify them (runs the repaired scenarios)", f'<span class="cmd">npm run repair -- --verify{e(us)}</span>'],
            ["Roll back", "restore the file from backup/ (or git checkout of the file)"]]
    if (data.get("verification") or {}).get("report"):
        rows.append(["Cucumber report of the verification", f'<a href="{e(data["verification"]["report"])}" style="color:var(--ink)">{e(data["verification"]["report"])}</a>'])
    body.append(section("How to continue", table(["To", "Command"], rows)))

    if hist_html:
        body.append(hist_html)
    meta_html = meta([("Story", data.get("story")), ("Date", (data.get("date") or "")[:16].replace("T", " ")),
                      ("Source", data.get("source")), ("Tool", data.get("tool"))])
    css_cat = ('<style>.cat{display:inline-flex;align-items:center;gap:7px;font-size:12px;font-weight:650;padding:4px 11px;border-radius:999px;'
               'background:var(--tile);border:1px solid var(--border);color:var(--ink);white-space:nowrap}.cat i{width:9px;height:9px;border-radius:3px}</style>')
    return page("Automation repair", "Automation repairer", meta_html, CSS_EXTRA + CSS_RPR + css_cat + "".join(body))


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Automation repair HTML report from repairs.json")
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
    hist_html = _history.section("repair", Path(a.data_json).resolve().parent, data)
    with open(a.output, "w", encoding="utf-8") as f:
        f.write(build_html(data, analysis, Path(a.data_json).parent, hist_html=hist_html))
    print(f"OK: {a.output}")


if __name__ == "__main__":
    main()
