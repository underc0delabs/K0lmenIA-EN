#!/usr/bin/env python3
"""
Generates the Cross-browser report in HTML (dashboard, dark mode) from cross-browser.json
(npm run cross-browser) and, optionally, from the analysis by the cross-browser agent.

Usage:
    python scripts/generate_cross_browser_report.py <cross-browser.json> <output.html> [--analysis analysis.json]

What it shows:
  - suite mode: scenarios that pass in all browsers, that fail only in some (what the test
    looks for) and that fail in all; the scenario × browser matrix with the screenshot of each
    one, passed and failed per browser, and the detail of each difference with the error.
  - pages mode: each screen (page × resolution) in each browser, side by side and with the
    slider comparator against the base browser, the percentage that looks different and the findings
    exclusive to one browser (JavaScript and console errors, failing resources, overflow,
    missing or shifted elements, different styles).
  - in both: the browsers and their versions (or how to install them), recommendations and next steps.

The analysis (optional) provides:
{
  "verdict": "Checkout does not work in Safari", "verdict_tone": "bad",
  "summary": "Summary for a non-technical person...",
  "findings": {"X-01": {"severity": "Critical", "cause": "Safari does not support ...", "action": "Add a polyfill",
                        "discarded": false}},
  "recommendations": [{"action": "...", "reason": "...", "priority": "High"}],
  "next_steps": ["..."]
}
"""
import argparse
import json
from pathlib import Path
import sys
from collections import Counter

import _history
from _report_styles import (e, page, meta, section, kpi_tiles, banner, doc_list, table, bar_chart, donut_panel, grouped_columns,
                            two_col, level_badge, status_pill, _pill, thumbnail, LEVEL_COLOR, CRITICAL, WARNING, NEUTRAL, OK, SERIOUS, SERIES)
from generate_exploratory_report import CSS_EXTRA
from generate_pixel_perfect_report import CSS_PP, JS_PP, deltas, before_after

BROWSER_COLOR = {"chromium": SERIES[2], "firefox": SERIES[3], "webkit": SERIES[4]}
SHORT = {"chromium": "Chromium", "firefox": "Firefox", "webkit": "WebKit"}
CLASS = {"Passes in all": (OK, "✓"), "Browser difference": (CRITICAL, "✕"), "Difference between browsers": (CRITICAL, "✕"),
         "Fails in all": (SERIOUS, "!"), "Flaky": (WARNING, "~"), "Incomplete result": (NEUTRAL, "–")}
PAGE_STATUS = {"OK": (OK, "✓"), "With issues": (CRITICAL, "✕"), "Minor differences": (WARNING, "!"), "Error": (NEUTRAL, "⊘")}
SEV = ["Critical", "High", "Medium", "Low"]

CSS_CB = """
<style>
.nav-pill{display:inline-flex;align-items:center;gap:7px;font-size:12px;font-weight:650;padding:4px 11px;border-radius:999px;
  background:var(--tile);border:1px solid var(--border);color:var(--ink);white-space:nowrap}
.nav-pill i{width:9px;height:9px;border-radius:50%}
.side-by-side{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;padding:16px 24px}
.side-by-side figure{margin:0;background:var(--bg);border:1px solid var(--border);border-radius:12px;overflow:hidden}
.side-by-side .thumb{display:grid;width:100%;height:260px;border:0;border-radius:0;border-bottom:1px solid var(--border)}
.side-by-side figcaption{padding:9px 12px;font-size:12.5px;color:var(--body);display:flex;justify-content:space-between;gap:8px;align-items:center}
.err{background:#120F0B;border:1px solid var(--border);border-radius:10px;padding:12px 14px;white-space:pre-wrap;word-break:break-word;
  font-family:var(--mono);font-size:12px;color:#FFB8B0;max-height:260px;overflow:auto}
.cell{display:flex;flex-direction:column;align-items:center;gap:6px}
.cell .pct{font-family:var(--mono);font-size:12px;color:var(--muted)}
.install{font-family:var(--mono);font-size:12px;color:var(--ink);background:var(--tile);border:1px solid var(--border);
  border-radius:8px;padding:4px 8px;display:inline-block}
.discarded{opacity:.55}
</style>
"""


def _state(x):
    """Status of a page result: cross-browser.js writes it as "state" ("status" is the HTTP status)."""
    return x.get("state") or x.get("status")


def _diff(x):
    return x.get("diff") or x.get("difference")


def nav_pill(n, text=None):
    nav = n.split("-")[0]
    return f'<span class="nav-pill"><i style="background:{BROWSER_COLOR.get(nav, NEUTRAL)}"></i>{e(text or SHORT.get(nav, n))}</span>'


def combo_txt(c):
    nav, _, res = c.partition("-")
    return f'{SHORT.get(nav, nav)} {res}'


def pill_for(mapping, status):
    color, ic = mapping.get(status, (NEUTRAL, "●"))
    return _pill(status or "—", color, ic)


def short_url(u):
    path = (u or "").split("://", 1)[-1].split("/", 1)
    return ("/" + path[1]) if len(path) > 1 and path[1] else "/"


def comparator(base, other, diff, base_lbl, other_lbl, width):
    maxw = f"max-width:{width}px" if width < 1024 else ""
    return f'''<div class="comp-wrap">
  <div class="comp-bar"><span class="side"><i style="background:{SERIES[2]}"></i>{e(base_lbl)}</span>
    <input type="range" min="0" max="100" value="50" aria-label="Slide between {e(base_lbl)} and {e(other_lbl)}">
    <span class="side"><i style="background:{SERIES[3]}"></i>{e(other_lbl)}</span>
    <button type="button" data-mode="slide" class="on">Slide</button><button type="button" data-mode="diff">View differences</button></div>
  <div class="comp" style="{maxw}"><div class="canvas">
    <img class="base" src="{e(other)}" data-act="{e(other)}" data-diff="{e(diff)}" alt="{e(other_lbl)}">
    <img class="over" src="{e(base)}" alt="{e(base_lbl)}"><div class="line"></div></div></div></div>'''


def browsers_table(data):
    r = data.get("summary") or {}
    rows = []
    for n in data.get("browsers") or []:
        if n.get("ok"):
            status = _pill("Available", OK, "✓")
            extra = ""
            if data.get("mode") == "suite":
                cs = [c for c in data.get("runs") or [] if c["browser"] == n["name"]]
                extra = " · ".join(f'{c["resolution"]}: {c["passed"]}/{c["total"]} passed' for c in cs)
            else:
                extra = f'{(r.get("by_browser") or {}).get(n["name"], 0)} exclusive finding(s)'
        else:
            status = _pill(n.get("error") or "Not available", NEUTRAL, "⊘")
            extra = f'<span class="install">{e(n.get("install"))}</span>' if n.get("install") else e(n.get("error"))
        base = " · comparison base" if data.get("base") == n["name"] and data.get("mode") == "pages" else ""
        rows.append([nav_pill(n["name"], n.get("title")), e(n.get("version") or "—"), status, extra + e(base)])
    return table(["Browser", "Version", "Status", "Result"], rows)


def finding_detail(h, a):
    evid = ""
    if h.get("evidence"):
        evid = '<div class="side-by-side" style="padding:8px 0">' + "".join(
            f'<figure>{thumbnail(x["screenshot"], combo_txt(x["combo"]))}<figcaption>{nav_pill(x["combo"], combo_txt(x["combo"]))}'
            f'{status_pill(x["status"])}</figcaption></figure>' for x in h["evidence"]) + "</div>"
    screens = h.get("screens") or []
    items = ""
    if len(screens) > 1:
        items = '<div class="lbl">Where it appears</div><ul>' + "".join(
            f'<li><span class="mono">{e(short_url(p["url"]))}</span> · {e(p["resolution"])}</li>' for p in screens[:12]) + "</ul>"
    ba = before_after({"id": h["id"], "before": h.get("base_screenshot"), "after": h.get("nav_screenshot")}) if (h.get("base_screenshot") or h.get("nav_screenshot")) else ""
    ba = ba.replace(">Reference<", ">Base browser<").replace(">Actual<", f'>{e(SHORT.get(h.get("browser"), "This browser"))}<')
    if not ba and not evid and h.get("screenshot"):
        evid = f'<div style="margin-top:8px">{thumbnail(h["screenshot"], h["title"])}</div>'
    err = h.get("error") or (h["detail"] if h["type"] in ("JavaScript error", "Console error") else "")
    return f'''<div class="finding{' discarded' if a.get("discarded") else ''}" id="{e(h["id"])}"><h3>{e(h["id"])} · {e(h["title"])} {level_badge(h["severity"])}
      {nav_pill(h["browser"]) if h.get("browser") else "".join(nav_pill(f) for f in h.get("failing") or [])}{' <span class="pill">Discarded</span>' if a.get("discarded") else ''}</h3>
      <p>{e(h["detail"]) if not err or err != h["detail"] else ""}</p>{deltas(h)}
      {f'<div class="lbl">Error</div><div class="err">{e(chr(10).join(err.splitlines()[:20]))}</div>' if err else ''}
      {f'<div class="lbl">Cause</div><p>{e(a["cause"])}</p>' if a.get("cause") else ''}
      {f'<div class="lbl">What to do</div><p>{e(a["action"])}</p>' if a.get("action") else ''}
      {items}{ba}{evid}</div>'''


def build_html(data, analysis, hist_html=""):
    overrides = analysis.get("findings") or {}
    findings = []
    for h in data.get("findings") or []:
        h = dict(h)
        a = overrides.get(h["id"]) or {}
        if a.get("severity") in SEV:
            h["severity"] = a["severity"]
        h["_a"] = a
        findings.append(h)
    live = [h for h in findings if not h["_a"].get("discarded")]
    r = data.get("summary") or {}
    mode = data.get("mode")
    navs = [n for n in data.get("browsers") or [] if n.get("ok")]
    lacking = r.get("not_installed") or []
    body = []

    if mode == "suite":
        dif, all_, n = r.get("differences", 0), r.get("fail_in_all", 0), r.get("scenarios", 0)
        if not n:
            tone, text = "warn", "There were no results: check the error of each run"
        elif dif:
            tone, text = "bad", f"{dif} scenario(s) fail only in some browsers"
        elif all_:
            tone, text = "warn", f"No differences between browsers; {all_} scenario(s) fail in all of them (not a browser issue)"
        else:
            tone, text = "ok", "All scenarios pass in all browsers"
    else:
        wi = r.get("with_issues", 0)
        if wi:
            tone, text = "bad", f"{wi} screen(s) with issues that appear only in some browser"
        elif live:
            tone, text = "warn", "Minor differences between browsers"
        else:
            tone, text = "ok", "The pages look and work the same in all browsers"
    if lacking and tone == "ok":
        tone = "warn"
    body.append(banner(analysis.get("verdict") or text, analysis.get("verdict_tone") or tone))

    if mode == "suite":
        n = r.get("scenarios", 0)
        body.append('<div style="margin-top:20px">' + kpi_tiles([
            ("Browsers", len(navs), "ok" if not lacking else "warn", f'{len(lacking)} not installed' if lacking else "all available", "browser"),
            ("Scenarios", n, "", f'{len(data.get("runs") or [])} run(s) · {", ".join(data.get("resolutions") or [])}', "list"),
            ("Pass in all", r.get("pass_in_all", 0), "ok" if n and r.get("pass_in_all") == n else "",
             f'{round(r.get("pass_in_all", 0) / n * 100) if n else 0} % of the scenarios', "ok", {"pct": r.get("pass_in_all", 0) / n * 100 if n else 0}),
            ("Differences", r.get("differences", 0), "bad" if r.get("differences") else "ok", "fail only in some browsers", "bad"),
            ("Fail in all", r.get("fail_in_all", 0), "warn" if r.get("fail_in_all") else "ok", "bug or broken test (failure-analyst)", "warn"),
            ("Flaky", r.get("flaky", 0), "warn" if r.get("flaky") else "ok", "failed and passed when repeated: not a browser issue", "warn"),
            ("No result", r.get("incomplete", 0), "warn" if r.get("incomplete") else "", "did not run in some browser", "blk"),
        ]) + "</div>")
    else:
        scr = r.get("screens", 0)
        body.append('<div style="margin-top:20px">' + kpi_tiles([
            ("Browsers", len(navs), "ok" if not lacking else "warn", f'{len(lacking)} not installed' if lacking else f'base: {SHORT.get(data.get("base"), "")}', "browser"),
            ("Screens", scr, "", f'{r.get("pages", 0)} page(s) × {len(data.get("resolutions") or [])} resolution(s)', "screen"),
            ("No differences", r.get("no_differences", 0), "ok" if scr and r.get("no_differences") == scr else "",
             f'{round(r.get("no_differences", 0) / scr * 100) if scr else 0} % of the screens', "ok", {"pct": r.get("no_differences", 0) / scr * 100 if scr else 0}),
            ("With issues", r.get("with_issues", 0), "bad" if r.get("with_issues") else "ok", "something fails or is missing in a browser", "bad"),
            ("Exclusive JS errors", r.get("exclusive_js_errors", 0), "bad" if r.get("exclusive_js_errors") else "ok",
             f'only in one browser · {r.get("confirmed", 0)} confirmed on reload, {r.get("discarded_on_confirm", 0)} discarded', "code"),
            ("Looks different", f'{r.get("pct_avg", 0)} %', "warn" if r.get("pct_max", 0) > 15 else "ok", f'average · max {r.get("pct_max", 0)} %', "image"),
        ]) + "</div>")
    if analysis.get("summary"):
        body.append(section("Executive summary", f'<div class="cardbody"><p class="lead">{e(analysis["summary"])}</p></div>'))

    body.append(section("Browsers", browsers_table(data),
                        "WebKit is Safari's engine: a very good approximation, but it does not replace a real Safari on a Mac or iPhone"))

    if mode == "suite":
        runs = data.get("runs") or []
        if runs:
            groups = [combo_txt(c["id"]) for c in runs]
            body.append(two_col(
                section("Result per browser", grouped_columns(groups, [("Passed", OK, [c["passed"] for c in runs]),
                                                                       ("Failed", CRITICAL, [c["failed"] for c in runs])], width=660)),
                section("Scenarios by result", donut_panel([(r.get(k, 0), CLASS[c][0], c) for k, c in
                                                            (("pass_in_all", "Passes in all"), ("differences", "Browser difference"),
                                                             ("fail_in_all", "Fails in all"), ("flaky", "Flaky"),
                                                             ("incomplete", "Incomplete result")) if r.get(k)],
                                                           round(r.get("pass_in_all", 0) / r["scenarios"] * 100) if r.get("scenarios") else 0,
                                                           "pass in all"))))
        rows = []
        for f in data.get("scenarios") or []:
            ident = " · ".join(x for x in (f.get("story"), f.get("case")) if x)
            row = [f'<strong style="color:var(--ink)">{e(f["scenario"])}</strong><div class="muted">{e(ident)} · <span class="mono">{e(f["uri"])}:{e(f["line"])}</span></div>',
                   pill_for(CLASS, f["class"])]
            for c in runs:
                x = f["results"].get(c["id"]) or {}
                img = thumbnail(x.get("screenshot"), f'{f["scenario"]} · {combo_txt(c["id"])}', "s") if x.get("screenshot") else ""
                row.append(f'<div class="cell">{status_pill(x.get("status") if x.get("status") in ("Passed", "Failed") else ("Flaky" if x.get("status") == "Flaky" else "N/A"))}{img}</div>')
            rows.append(row)
        if rows:
            body.append(section("Scenario matrix", f'<div class="matrix">{table(["Scenario", "Result"] + [combo_txt(c["id"]) for c in runs], rows)}</div>',
                                "each scenario in each browser, with the final screenshot (or the one from the moment it failed)"))
        errors = [c for c in runs if c.get("error")]
        if errors:
            body.append(section("Runs without results", "".join(
                f'<div class="finding"><h3>{nav_pill(c["id"], combo_txt(c["id"]))}</h3><div class="err">{e(c["error"])}</div></div>' for c in errors)))
    else:
        if live:
            count_n = Counter(h.get("browser") for h in live)
            count_t = Counter(h["type"] for h in live)
            body.append(two_col(
                section("Findings per browser", bar_chart([(SHORT.get(n, n), count_n[n], BROWSER_COLOR.get(n, NEUTRAL)) for n in BROWSER_COLOR if count_n.get(n)], label_width=110)),
                section("Findings by type", bar_chart([(t, c, SERIES[i % len(SERIES)]) for i, (t, c) in enumerate(count_t.most_common())], label_width=160))))
        page_rows = data.get("pages") or []
        combos = list(dict.fromkeys(k for f in page_rows for k in f["results"]))
        navs_order = list(dict.fromkeys(k.split("-")[0] for k in combos))
        rows = []
        for f in page_rows:
            row = [f'<span class="mono" style="color:var(--ink)">{e(short_url(f["url"]))}</span><div class="muted">{e(f["resolution"])}</div>']
            for n in navs_order:
                x = f["results"].get(f'{n}-{f["resolution"]}') or {}
                pct = f'<span class="pct">{x["pct"]} % different</span>' if x.get("pct") is not None else (
                    '<span class="pct">base</span>' if f'{n}-{f["resolution"]}' == f["base"] else "")
                img = thumbnail(x.get("screenshot"), f'{short_url(f["url"])} · {SHORT.get(n)} {f["resolution"]}', "s") if x.get("screenshot") else ""
                row.append(f'<div class="cell"><a href="#p-{e(f["page"])}-{e(f["resolution"])}" style="text-decoration:none">{pill_for(PAGE_STATUS, _state(x))}</a>{pct}{img}</div>')
            rows.append(row)
        if rows:
            body.append(section("Screen matrix", f'<div class="matrix">{table(["Screen"] + [SHORT.get(n, n) for n in navs_order], rows)}</div>',
                                "status of each page in each browser · click the status to compare them"))
        blocks = []
        opened = False
        for f in page_rows:
            base = f["results"].get(f["base"]) or {}
            width = int(f["resolution"].split("x")[0])
            figs = ""
            for k, x in f["results"].items():
                title = short_url(f["url"]) + " · " + combo_txt(k)
                img = thumbnail(x.get("screenshot"), title) if x.get("screenshot") else ""
                figs += f'<figure>{img}<figcaption>{nav_pill(k)}{pill_for(PAGE_STATUS, _state(x))}</figcaption></figure>'
            comps = "".join(comparator(base["screenshot"], x["screenshot"], _diff(x), SHORT.get(f["base"].split("-")[0]), SHORT.get(k.split("-")[0]), width)
                            for k, x in f["results"].items() if k != f["base"] and _diff(x) and base.get("screenshot"))
            problems = any(_state(x) != "OK" for x in f["results"].values())
            open_attr = "open" if problems and not opened else ""
            opened = opened or problems
            worst = "With issues" if any(_state(x) == "With issues" for x in f["results"].values()) else "Minor differences"
            status_html = pill_for(PAGE_STATUS, worst) if problems else '<span class="muted">no differences</span>'
            blocks.append(f'''<details class="pag" id="p-{e(f["page"])}-{e(f["resolution"])}" {open_attr}>
              <summary><strong>{e(short_url(f["url"]))}</strong><span class="muted">{e(f["resolution"])}</span>{status_html}</summary>
              <div class="side-by-side">{figs}</div>{comps}</details>''')
        if blocks:
            body.append(section("Each screen in each browser", "".join(blocks),
                                "side by side and with the slider comparator against the base browser"))

    if findings:
        rows = []
        for h in findings:
            more = len(h.get("screens") or []) - 1
            more_txt = f" · and {more} more" if more > 0 else ""
            where = (f'<span class="mono">{e(short_url(h["url"]))}</span><div class="muted">{e(h.get("resolution"))}{more_txt}</div>'
                     if h.get("url") else f'<span class="mono">{e(h.get("scenario", ""))}</span>')
            navcol = nav_pill(h["browser"]) if h.get("browser") else "".join(nav_pill(x, combo_txt(x)) for x in h.get("failing") or [])
            rows.append([f'<a class="id" href="#{e(h["id"])}" style="color:var(--ink)">{e(h["id"])}</a>', level_badge(h["severity"]), e(h["type"]),
                         f'<strong style="color:var(--ink)">{e(h["title"])}</strong>', navcol, where])
        body.append(section("Findings", table(["ID", "Severity", "Type", "Finding", "Browser", "Where"], rows), "click the ID to see the detail"))
        body.append(section("Detail of each finding", "".join(finding_detail(h, h["_a"]) for h in findings)))

    if analysis.get("recommendations"):
        rows = [[f'<strong style="color:var(--ink)">{e(x.get("action"))}</strong>', e(x.get("reason")), level_badge(x.get("priority"))]
                for x in analysis["recommendations"]]
        body.append(section("Recommendations", table(["Action", "Why", "Priority"], rows)))
    if analysis.get("next_steps"):
        body.append(section("Next steps", doc_list(analysis["next_steps"])))

    cfg = data.get("config") or {}
    rows = [["Mode", e("k0lmena suite (npm test per browser)" if mode == "suite" else "Page walkthrough (GET only)")],
            ["Resolutions", e(", ".join(data.get("resolutions") or []))]]
    if mode == "suite":
        rows.append(["Scenario filter", f'<span class="mono">{e(data.get("tags") or "all")}</span>'])
        for c in data.get("runs") or []:
            if c.get("report"):
                rows.append([f"Cucumber report · {e(combo_txt(c['id']))}", f'<a href="{e(c["report"])}" style="color:var(--ink)">{e(c["report"])}</a>'])
    else:
        rows += [["Base browser", e(SHORT.get(data.get("base")))], ["Position tolerance", f'{e(cfg.get("tolerance_px"))} px'],
                 ["Hidden areas", e(", ".join(cfg.get("hide") or []) or "none")]]
    body.append(section("Run configuration", table(["Item", "Value"], rows)))

    if hist_html:
        body.append(hist_html)
    meta_html = meta([("Story", data.get("story")), ("Site", data.get("host")), ("Date", (data.get("date") or "")[:16].replace("T", " ")),
                      ("Mode", "suite" if mode == "suite" else "pages"), ("Duration", f'{data.get("duration_s", 0)} s')])
    return page("Cross-browser", "Browser compatibility", meta_html, CSS_EXTRA + CSS_PP + CSS_CB + "".join(body) + JS_PP)


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Cross-browser HTML report from cross-browser.json")
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
    hist_html = _history.section("cross-browser", Path(a.data_json).resolve().parent, data)
    with open(a.output, "w", encoding="utf-8") as f:
        f.write(build_html(data, analysis, hist_html=hist_html))
    print(f"OK: {a.output}")


if __name__ == "__main__":
    main()
