#!/usr/bin/env python3
"""
Generates the Accessibility report in HTML (dashboard, dark mode) from the automatic
audit (audit.json, from `npm run accessibility`) and, optionally, from the analysis by the
accessibility-analyst agent. `npm run accessibility` already generates it on its own when it finishes; the agent
generates it again with its analysis.

Usage:
    python scripts/generate_accessibility_report.py <audit.json> <output.html> [--analysis analysis.json]

What it shows: verdict, indicators (automatic compliance, findings by severity, unmet WCAG
criteria, affected elements), charts (rules that pass and fail, findings by principle and by
severity, by page), the unmet WCAG criteria with their name and level, each finding with what
happens, how to fix it, the affected elements with their screenshot (click to enlarge) and the link to the
documentation, the manual review, what axe could not decide, keyboard navigation, the pages,
the video and the screenshots.

The AUTOMATIC findings come from audit.json. The analysis (optional) provides:
{
  "verdict": "Does not meet AA: 3 critical barriers", "verdict_tone": "bad",   // ok | warn | bad
  "summary": "Summary for a non-technical person...",
  "reviewed_areas": ["Screen reader on signup", "Form error messages"],
  "notes": {"A-02": "Decorative images can have an empty alt"},
  "discarded": [{"id": "A-09", "reason": "The tabindex is added by a third-party widget that cannot be changed"}],
  "severities": {"A-07": "Critical"},
  "manual": [{"id": "M-01", "title": "...", "severity": "High", "wcag": ["3.3.1"], "page": "https://...",
              "steps": ["..."], "expected": "...", "actual": "...", "fix": "...", "evidence": "screenshots/manual/m-01.png"}],
  "missing_info": [{"id": "MI-01", "what_is_missing": "...", "question": "..."}],   // "description" works as an alias of what_is_missing
  "recommendations": [{"action": "...", "reason": "...", "priority": "High"}],
  "next_steps": ["..."]
}
"""
import argparse
import datetime
import json
from pathlib import Path
import sys

import _history
from _report_styles import (missing_info, warn_analysis, e, page, meta, section, kpi_tiles, banner, doc_list, table, bar_chart, donut_panel,
                            two_col, level_badge, _pill, CRITICAL, SERIOUS, WARNING, NEUTRAL, OK, SERIES)
from generate_exploratory_report import CSS_EXTRA, JS_EXTRA, thumbnail, short, origin

SEVERITIES = [("Critical", CRITICAL), ("High", SERIOUS), ("Medium", WARNING), ("Low", NEUTRAL)]
ORDER = {s: i for i, (s, _) in enumerate(SEVERITIES)}
PRINCIPLES = {"1": ("Perceivable", SERIES[1]), "2": ("Operable", SERIES[3]), "3": ("Understandable", SERIES[2]), "4": ("Robust", SERIES[7])}

# WCAG 2.2 success criteria (levels A and AA, and the AAA ones axe checks).
WCAG = {
    "1.1.1": ("Non-text Content", "A"), "1.2.1": ("Audio-only and Video-only (Prerecorded)", "A"),
    "1.2.2": ("Captions (Prerecorded)", "A"), "1.2.3": ("Audio Description or Media Alternative (Prerecorded)", "A"),
    "1.2.4": ("Captions (Live)", "AA"), "1.2.5": ("Audio Description (Prerecorded)", "AA"),
    "1.3.1": ("Info and Relationships", "A"), "1.3.2": ("Meaningful Sequence", "A"),
    "1.3.3": ("Sensory Characteristics", "A"), "1.3.4": ("Orientation", "AA"),
    "1.3.5": ("Identify Input Purpose", "AA"), "1.4.1": ("Use of Color", "A"),
    "1.4.2": ("Audio Control", "A"), "1.4.3": ("Contrast (Minimum)", "AA"),
    "1.4.4": ("Resize Text", "AA"), "1.4.5": ("Images of Text", "AA"),
    "1.4.6": ("Contrast (Enhanced)", "AAA"), "1.4.10": ("Reflow", "AA"),
    "1.4.11": ("Non-text Contrast", "AA"), "1.4.12": ("Text Spacing", "AA"),
    "1.4.13": ("Content on Hover or Focus", "AA"), "2.1.1": ("Keyboard", "A"),
    "2.1.2": ("No Keyboard Trap", "A"), "2.1.4": ("Character Key Shortcuts", "A"),
    "2.2.1": ("Timing Adjustable", "A"), "2.2.2": ("Pause, Stop, Hide", "A"),
    "2.2.4": ("Interruptions", "AAA"), "2.3.1": ("Three Flashes or Below Threshold", "A"),
    "2.4.1": ("Bypass Blocks", "A"), "2.4.2": ("Page Titled", "A"), "2.4.3": ("Focus Order", "A"),
    "2.4.4": ("Link Purpose (In Context)", "A"), "2.4.5": ("Multiple Ways", "AA"),
    "2.4.6": ("Headings and Labels", "AA"), "2.4.7": ("Focus Visible", "AA"),
    "2.4.9": ("Link Purpose (Link Only)", "AAA"), "2.4.11": ("Focus Not Obscured (Minimum)", "AA"),
    "2.5.1": ("Pointer Gestures", "A"), "2.5.2": ("Pointer Cancellation", "A"), "2.5.3": ("Label in Name", "A"),
    "2.5.4": ("Motion Actuation", "A"), "2.5.7": ("Dragging Movements", "AA"),
    "2.5.8": ("Target Size (Minimum)", "AA"), "3.1.1": ("Language of Page", "A"),
    "3.1.2": ("Language of Parts", "AA"), "3.2.1": ("On Focus", "A"), "3.2.2": ("On Input", "A"),
    "3.2.3": ("Consistent Navigation", "AA"), "3.2.4": ("Consistent Identification", "AA"), "3.2.6": ("Consistent Help", "A"),
    "3.3.1": ("Error Identification", "A"), "3.3.2": ("Labels or Instructions", "A"),
    "3.3.3": ("Error Suggestion", "AA"), "3.3.4": ("Error Prevention (Legal, Financial, Data)", "AA"),
    "3.3.7": ("Redundant Entry", "A"), "3.3.8": ("Accessible Authentication (Minimum)", "AA"),
    "4.1.2": ("Name, Role, Value", "A"), "4.1.3": ("Status Messages", "AA"),
}

CSS_A11Y = """
<style>
.crit{display:inline-block;font-family:var(--mono);font-size:11.5px;padding:1px 7px;border-radius:6px;
  background:var(--tile);border:1px solid var(--border);color:var(--ink);margin:2px 4px 2px 0;white-space:nowrap}
.code-a11y{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:8px 10px;white-space:pre-wrap;
  word-break:break-all;color:var(--body);font-family:var(--mono);font-size:12px;margin:4px 0}
.elem{display:grid;grid-template-columns:1fr 130px;gap:14px;padding:10px 0;border-top:1px dashed var(--border-soft)}
.elem:first-child{border-top:0}
.focus-order{font-size:12.5px;color:var(--body);columns:2;column-gap:28px}
.focus-order li{margin:2px 0;break-inside:avoid}
@media (max-width:720px){.elem{grid-template-columns:1fr}.focus-order{columns:1}}
</style>
"""


def crit(c):
    name, level = WCAG.get(c, ("", ""))
    return f'<span class="crit" title="{e(name)}">{e(c)}{" · " + e(level) if level else ""}</span>'


def principle(c):
    return PRINCIPLES.get((c or "0")[0], ("Best practices", NEUTRAL))


def auto_tone(findings, level):
    sev = {h["severity"] for h in findings}
    wcag = [h for h in findings if h.get("wcag")]
    if "Critical" in sev:
        return "bad", f"Does not meet WCAG {level}: there are critical barriers that prevent some people from using the site"
    if wcag:
        return "warn", f"Does not meet WCAG {level}: there are unmet criteria worth fixing"
    if findings:
        return "warn", "No unmet WCAG criteria in the automatic part; some best practices are left to improve"
    return "ok", f"No problems detected in the automatic part of WCAG {level} (the manual review is still pending)"


def build_html(data, analysis, hist_html=""):
    discarded = {str(d.get("id")): d.get("reason", "") for d in analysis.get("discarded") or []}
    notes = analysis.get("notes") or {}
    overrides = analysis.get("severities") or {}
    base = origin(data.get("url"))
    cfg = data.get("config") or {}
    r = data.get("summary") or {}
    pgs = data.get("pages") or []
    level = cfg.get("level", "AA")

    findings = []
    for h in data.get("findings") or []:
        if h.get("id") in discarded:
            continue
        h = dict(h)
        if overrides.get(h.get("id")) in ORDER:
            h["severity"] = overrides[h["id"]]
        findings.append(h)
    manual = [dict(m, source="manual", pages=[m.get("page")] if m.get("page") else [], total_nodes=1)
              for m in analysis.get("manual") or []]
    everything = sorted(findings + manual, key=lambda h: ORDER.get(h.get("severity"), 9))
    by_sev = {s: sum(1 for h in everything if h.get("severity") == s) for s, _ in SEVERITIES}
    criteria = sorted({c for h in everything for c in h.get("wcag") or []}, key=lambda c: [int(x) for x in c.split(".")])
    keyboard = [h for h in findings if h.get("source") == "keyboard"]

    body = []
    tone, text = auto_tone(everything, level)
    body.append(banner(analysis.get("verdict") or text, analysis.get("verdict_tone") or tone))

    pct = r.get("compliance_pct")
    body.append('<div style="margin-top:20px">' + kpi_tiles([
        ("Automatic compliance", f"{pct:g} %" if pct is not None else "—", "ok" if (pct or 0) >= 95 else "warn" if (pct or 0) >= 80 else "bad",
         "of the axe rules that apply", "", {"pct": pct or 0}),
        ("Findings", len(everything), "bad" if by_sev["Critical"] else ("warn" if everything else "ok"),
         f'{by_sev["Critical"]} critical · {by_sev["High"]} high · {by_sev["Medium"]} medium · {by_sev["Low"]} low'),
        ("Unmet WCAG criteria", len(criteria), "bad" if criteria else "ok", f"target level {level}"),
        ("Affected elements", sum(h.get("total_nodes", 0) for h in findings), "warn" if findings else "ok"),
        ("Pages audited", r.get("pages", len(pgs)), "", f'{r["uncrawled_pages"]} not crawled' if r.get("uncrawled_pages") else ""),
        ("Keyboard", len(keyboard), "bad" if any(h["severity"] == "Critical" for h in keyboard) else ("warn" if keyboard else "ok"),
         "visible focus, traps and skip to content"),
        ("To review by hand", len(data.get("review") or []), "warn" if data.get("review") else "", "axe could not decide"),
    ] + ([("Manual review", len(manual), "warn" if manual else "ok")] if analysis else [])) + "</div>")

    if analysis.get("summary"):
        body.append(section("Executive summary", f'<div class="cardbody"><p class="lead">{e(analysis["summary"])}</p></div>'))

    # ---- Overview
    ok_rules = sum(len(p.get("passes") or []) for p in pgs)
    bad_rules = sum(len(p.get("violations") or []) for p in pgs)
    seg = [(ok_rules, OK, "Rules that pass"), (bad_rules, CRITICAL, "Rules that fail")]
    g1 = donut_panel(seg, round(pct or 0), "compliance")
    by_principle = {}
    for h in everything:
        name, color = principle((h.get("wcag") or [""])[0])
        by_principle.setdefault(name, [0, color])[0] += 1
    p_order = ["Perceivable", "Operable", "Understandable", "Robust", "Best practices"]
    g2 = bar_chart([(n, by_principle[n][0], SERIES[0]) for n in p_order if n in by_principle], label_width=140)
    body.append(two_col(section("axe rules", g1, "adding up all the pages"),
                        section("Findings by WCAG principle", g2)))
    if everything:
        by_page = sorted(((short(p["url"], base), sum(1 for h in findings if p["url"] in h.get("pages", []))) for p in pgs), key=lambda x: -x[1])
        body.append(two_col(section("Findings by severity", bar_chart([(s, by_sev[s], c) for s, c in SEVERITIES])),
                            section("Findings by page", bar_chart([(u, n, SERIES[0]) for u, n in by_page[:12] if n], label_width=200))))

    # ---- Scope
    areas = ('<p><strong style="color:var(--ink)">Manual review:</strong> ' + e(", ".join(analysis["reviewed_areas"])) + "</p>"
             if analysis.get("reviewed_areas") else "")
    body.append(section("Scope and method", f'''<div class="cardbody">
      <p><strong style="color:var(--ink)">Automatic audit</strong> of {e(r.get("pages", len(pgs)))} page(s) from <span class="mono">{e(data.get("url"))}</span>
      against <strong style="color:var(--ink)">WCAG 2.2 level {e(level)}</strong>{" and best practices" if cfg.get("best_practices") else ""} with {e(data.get("tool", "axe-core"))};
      keyboard navigation (up to {e(cfg.get("tabs"))} Tabs per page) and content reflow at 320px. Duration: {e(data.get("duration_s"))} s.</p>
      <p><strong style="color:var(--ink)">Important:</strong> an automatic audit detects between 30 and 50 % of accessibility problems.
      A criterion not showing up does not mean it is met: the quality of alternative texts, the reading order, the error
      messages, use with a screen reader or with zoom require a manual review.</p>{areas}</div>'''))

    # ---- Unmet criteria
    if criteria:
        rows = []
        for c in criteria:
            name, lvl = WCAG.get(c, ("—", "—"))
            hs = [h for h in everything if c in (h.get("wcag") or [])]
            rows.append([crit(c), e(name), e(lvl), e(principle(c)[0]), ", ".join(e(h["id"]) for h in hs),
                         e(len({p for h in hs for p in h.get("pages") or []}))])
        body.append(section("Unmet WCAG criteria", table(["Criterion", "Name", "Level", "Principle", "Findings", "Pages"], rows)))

    # ---- Findings table
    if everything:
        rows = []
        for h in everything:
            ev = next((x.get("screenshot") for x in h.get("examples") or [] if x.get("screenshot")), None) or h.get("evidence")
            note = f'<div class="muted" style="margin-top:4px">{e(notes[h["id"]])}</div>' if h.get("id") in notes else ""
            source = {"axe": "axe", "keyboard": "Keyboard", "reflow": "Reflow", "manual": "Manual"}.get(h.get("source"), "")
            rows.append([f'<a href="#{e(h["id"])}" style="color:var(--ink);white-space:nowrap">{e(h["id"])}</a>', level_badge(h.get("severity")),
                         "".join(crit(c) for c in h.get("wcag") or []) or '<span class="muted">Best practice</span>',
                         f'<strong style="color:var(--ink)">{e(h.get("title"))}</strong><div class="muted">{e(source)}</div>{note}',
                         e(len(h.get("pages") or [])), e(h.get("total_nodes", "")), thumbnail(ev, f'{h["id"]} · {h.get("title")}', "s")])
        body.append(section("All findings", table(["ID", "Severity", "WCAG", "Finding", "Pages", "Elements", "Evidence"], rows),
                            "click the ID to see the detail and the screenshot to enlarge it"))
    else:
        body.append(section("Findings", '<div class="cardbody"><p>The automatic audit found no problems.</p></div>'))

    # ---- Detail
    detail = []
    for h in [x for x in everything if x.get("source") != "manual"]:
        elems = []
        for x in (h.get("examples") or [])[:8]:
            fix = x.get("summary") or ""
            elems.append(f'''<div class="elem"><div><div class="mono muted">{e(short(x.get("page"), base))}</div>
              <div class="mono" style="color:var(--ink)">{e(x.get("selector"))}</div>
              {f'<div class="code-a11y">{e(x["html"])}</div>' if x.get("html") else ""}
              {f'<div class="code-a11y">{e(fix)}</div>' if fix else ""}</div>
              <div>{thumbnail(x.get("screenshot"), x.get("selector", ""))}</div></div>''')
        more = h.get("total_nodes", 0) - len(elems)
        pages = h.get("pages") or []
        detail.append(f'''<div class="finding" id="{e(h["id"])}"><h3>{e(h["id"])} · {e(h.get("title"))} {level_badge(h.get("severity"))}
            {"".join(crit(c) for c in h.get("wcag") or [])}</h3>
          <div class="lbl">What happens</div><p>{e(h.get("description"))}</p>
          {"".join(f'<p class="muted">{e(c)} · {e(WCAG.get(c, ("",))[0])}</p>' for c in h.get("wcag") or [])}
          {f'<div class="lbl">Analysis</div><p>{e(notes[h["id"]])}</p>' if h.get("id") in notes else ""}
          <div class="lbl">Pages ({len(pages)})</div><p class="mono">{e(", ".join(short(p, base) for p in pages[:10]))}{" …" if len(pages) > 10 else ""}</p>
          <div class="lbl">Affected elements ({e(h.get("total_nodes"))}) and how to fix them</div>{"".join(elems)}
          {f'<p class="muted">… and {more} more element(s).</p>' if more > 0 else ""}
          {f'<div class="lbl">More information</div><p><a href="{e(h["help"])}" target="_blank" rel="noopener" style="color:var(--ink)">Guide for the rule <span class="mono">{e(h.get("rule"))}</span> (Deque)</a></p>' if h.get("help") else ""}
        </div>''')
    if detail:
        body.append(section("Detail of each finding", "".join(detail)))

    if manual:
        det = []
        for x in manual:
            steps = "".join(f"<li>{e(p)}</li>" for p in x.get("steps") or [])
            det.append(f'''<div class="finding" id="{e(x.get("id"))}"><h3>{e(x.get("id"))} · {e(x.get("title"))} {level_badge(x.get("severity"))}
                {"".join(crit(c) for c in x.get("wcag") or [])}</h3><div class="mono muted">{e(x.get("page"))}</div>
              {f'<div class="lbl">Steps</div><ol>{steps}</ol>' if steps else ""}
              {f'<div class="lbl">Expected result</div><p>{e(x["expected"])}</p>' if x.get("expected") else ""}
              {f'<div class="lbl">Actual result</div><p>{e(x["actual"])}</p>' if x.get("actual") else ""}
              {f'<div class="lbl">How to fix it</div><p>{e(x["fix"])}</p>' if x.get("fix") else ""}
              {f'<div class="lbl">Evidence</div>{thumbnail(x["evidence"], x.get("title", ""))}' if x.get("evidence") else ""}</div>''')
        body.append(section("Manual review", "".join(det)))

    review = data.get("review") or []
    if review:
        rows = [[e(x["id"]), f'<strong style="color:var(--ink)">{e(x.get("title"))}</strong><div class="muted">{e(x.get("description"))}</div>',
                 "".join(crit(c) for c in x.get("wcag") or []) or "—", e(len(x.get("pages") or [])), e(x.get("total_nodes")),
                 f'<a href="{e(x["help"])}" target="_blank" rel="noopener" style="color:var(--ink)">guide</a>' if x.get("help") else "—"]
                for x in review]
        body.append(section("To review by hand", table(["ID", "What to review", "WCAG", "Pages", "Elements", "Help"], rows),
                            "axe could not decide whether they pass (for example, contrast over images)"))

    # ---- Keyboard per page
    with_keyboard = [p for p in pgs if p.get("keyboard")]
    if with_keyboard:
        rows, blocks = [], []
        for p in with_keyboard:
            t = p["keyboard"]
            steps = t.get("steps") or []
            without = sum(1 for x in steps if not x.get("visible_indicator"))
            skip = bool(steps) and any(k in (steps[0].get("text") or "").lower() for k in ("skip", "content", "salt", "contenido"))
            rows.append([f'<span class="mono">{e(short(p["url"], base))}</span>', e(len(steps)),
                         _pill("OK", OK, "✓") if not without else _pill(f"{without} without indicator", SERIOUS, "✕"),
                         _pill("Yes", CRITICAL, "✕") if t.get("trap") else _pill("No", OK, "✓"),
                         _pill("Yes", OK, "✓") if skip else _pill("No", WARNING, "!")])
            warning = f' <b style="color:{SERIOUS}">· no visible focus</b>'
            order = "".join(f'<li><span class="mono">{e(x["element"])}</span> {e(x.get("text") or "")}'
                            f'{warning if not x.get("visible_indicator") else ""}</li>' for x in steps)
            blocks.append(f'<details class="pag"><summary><span class="mono">{e(short(p["url"], base))}</span>'
                          f'<span class="muted">{len(steps)} elements with Tab</span></summary>'
                          f'<div style="padding:0 24px 18px"><ol class="focus-order">{order or "<li>No element received focus.</li>"}</ol></div></details>')
        body.append(section("Keyboard navigation", table(["Page", "Elements with Tab", "Visible focus", "Focus trap", "Skip to content"], rows)))
        body.append(section("Focus order per page", "".join(blocks), "in the order they are reached with Tab"))

    # ---- Pages
    if pgs:
        rows = []
        for p in pgs:
            n_h = sum(1 for h in findings if p["url"] in (h.get("pages") or []))
            rf = p.get("reflow") or {}
            rows.append([f'<span class="mono">{e(short(p["url"], base))}</span>' + (f'<div class="muted">{e(p.get("title"))}</div>' if p.get("title") else ""),
                         _pill(str(p.get("status")), OK, "✓") if not p.get("error") and 0 < (p.get("status") or 0) < 400 else _pill(str(p.get("error") and "error" or p.get("status")), CRITICAL, "✕"),
                         e(p.get("language") or "—"), e(len(p.get("violations") or [])), e(len(p.get("passes") or [])),
                         _pill("Overflows", WARNING, "!") if rf.get("overflows") else _pill("OK", OK, "✓"),
                         _pill(str(n_h), CRITICAL if n_h else OK, "✕" if n_h else "✓"), thumbnail(p.get("screenshot"), short(p["url"], base), "s")])
        body.append(section("Pages audited", table(["Page", "Status", "Language (lang)", "Rules that fail", "Rules that pass", "Reflow 320px", "Findings", "Screenshot"], rows)))

    videos = data.get("videos") or []
    if videos:
        figs = "".join(f'<figure><video controls preload="metadata" src="{e(v["file"])}#t=1"></video>'
                       f'<figcaption>{e(v.get("title", v["file"]))} · <a href="{e(v["file"])}" download style="color:var(--ink)">download</a></figcaption></figure>'
                       for v in videos)
        body.append(section("Video", f'<div class="videos">{figs}</div>'))
    shots = [p for p in pgs if p.get("screenshot")]
    if shots:
        figs = "".join(f'<figure>{thumbnail(p["screenshot"], short(p["url"], base)).replace("thumb", "", 1)}'
                       f'<figcaption>{e(short(p["url"], base))}</figcaption></figure>' for p in shots)
        body.append(section("Screenshots of the pages", f'<div class="gallery">{figs}</div>', "the failing elements, marked in red"))

    if discarded:
        originals = {h.get("id"): h for h in data.get("findings") or []}
        rows = [[e(i), e((originals.get(i) or {}).get("title", "")), e(m)] for i, m in discarded.items()]
        body.append(section("Discarded", table(["ID", "Finding", "Reason"], rows)))
    body.append(missing_info(analysis.get("missing_info")))
    if analysis.get("recommendations"):
        rows = [[f'<strong style="color:var(--ink)">{e(x.get("action"))}</strong>', e(x.get("reason")), level_badge(x.get("priority"))]
                for x in analysis["recommendations"]]
        body.append(section("Recommendations", table(["Action", "Why", "Priority"], rows)))
    if analysis.get("next_steps"):
        body.append(section("Next steps", doc_list(analysis["next_steps"])))

    date = (data.get("date") or datetime.datetime.now().isoformat())[:16].replace("T", " ")
    if hist_html:
        body.append(hist_html)
    meta_html = meta([("Story", data.get("story")), ("Site", data.get("host")), ("Date", date),
                      ("Standard", f"WCAG 2.2 {level}"), ("Tool", data.get("tool"))])
    return page("Accessibility report", "Accessibility", meta_html, CSS_EXTRA + CSS_A11Y + "".join(body) + JS_EXTRA)


def main():
    for stream in (sys.stdout, sys.stderr):  # proper accents in the Windows console
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Accessibility HTML report from audit.json")
    ap.add_argument("audit_json")
    ap.add_argument("output")
    ap.add_argument("--analysis", help="JSON with verdict, summary, manual review, discards and recommendations")
    a = ap.parse_args()
    if not a.output.lower().endswith(".html"):
        sys.exit("The output must end in .html")
    with open(a.audit_json, encoding="utf-8") as f:
        data = json.load(f)
    analysis = {}
    if a.analysis:
        with open(a.analysis, encoding="utf-8") as f:
            analysis = json.load(f)
        warn_analysis(analysis, [h.get("id") for h in (data.get("findings") or []) + (data.get("review") or [])] + [x.get("id") for x in analysis.get("manual") or []])
    hist_html = _history.section("accessibility", Path(a.audit_json).resolve().parent, data)
    with open(a.output, "w", encoding="utf-8") as f:
        f.write(build_html(data, analysis, hist_html=hist_html))
    print(f"OK: {a.output}")


if __name__ == "__main__":
    main()
