#!/usr/bin/env python3
"""
Generates the Exploratory testing report in HTML (dashboard, dark mode) from the
result of the automated crawl (exploration.json, from `npm run explore`) and, optionally,
from the web-explorer agent's analysis. `npm run explore` already generates it on its own when it
finishes; the agent generates it again with its analysis.

Usage:
    python scripts/generate_exploratory_report.py <exploration.json> <output.html>
           [--analysis analysis.json]

What it shows: verdict, indicators, charts (pages with and without problems, links, findings by
severity and by type, load times, responsive by resolution), all the findings with their
screenshot (click to enlarge), the manual exploration, the responsive matrix with thumbnails, the
videos of the walkthrough and of each resolution, the screenshot gallery, broken and unverifiable links,
and the detail of each page (metrics, JavaScript and console errors, failing resources and images).

The AUTOMATIC findings come from exploration.json (they are not written by hand). The analysis
(optional) provides:
{
  "verdict": "Usable site with remarks",        // conclusion
  "verdict_tone": "warn",                       // optional: ok | warn | bad
  "summary": "Summary for a non-technical person...",
  "mission": "Explore the navigation and the public forms",   // session charter
  "duration_min": 30,                                   // timebox of the manual exploration
  "notes": {"H-03": "The 502 is intermittent: it answered 200 again after 5 minutes"},
  "discarded": [{"id": "H-05", "reason": "The external site blocks the link for robots"}],
  "severities": {"H-02": "High"},                      // severity adjustment (with the reason in notes)
  "exploratory": [{"id": "EX-01", "title": "...", "severity": "Medium", "page": "https://...",
                   "steps": ["..."], "expected": "...", "actual": "...", "fix": "...", "evidence": "screenshots/manual/ex-01.png"}],
  "explored_areas": ["Main menu", "Contact form (without submitting)"],
  "missing_info": [{"id": "MI-01", "what_is_missing": "...", "question": "..."}],   // "description" works as an alias of what_is_missing
  "recommendations": [{"action": "...", "reason": "...", "priority": "High"}],
  "next_steps": ["..."]
}

Severity: Critical | High | Medium | Low. The evidence and video paths are relative to the HTML
(it is saved in the same folder as exploration.json). The HTML is self-contained (no internet).
"""
import argparse
import datetime
import json
from pathlib import Path
import sys

import _history
from _report_styles import thumbnail  # noqa: F401 (imported by the other reports)
from _report_styles import (missing_info, warn_analysis, e, page, meta, section, kpi_tiles, banner, doc_list, table, bar_chart, stacked_bars,
                            donut_panel, two_col, level_badge, _pill, CRITICAL, SERIOUS, WARNING, NEUTRAL, OK, SERIES)

SEVERITIES = [("Critical", CRITICAL), ("High", SERIOUS), ("Medium", WARNING), ("Low", NEUTRAL)]
ORDER = {s: i for i, (s, _) in enumerate(SEVERITIES)}
CATEGORIES = [("Page error", CRITICAL), ("Broken link", SERIOUS), ("Broken image", SERIOUS), ("JavaScript error", SERIOUS),
              ("Console error", WARNING), ("Failed resource", WARNING), ("Responsive", SERIES[1]), ("Web performance", SERIES[7]),
              ("Accessibility", NEUTRAL), ("Manual exploration", SERIES[5])]

CSS_EXTRA = """
<style>
.mono{font-family:var(--mono);font-size:12.5px;word-break:break-all}
.finding{padding:20px 24px;border-top:1px solid var(--border-soft)}
.finding:first-child{border-top:0}
.finding h3{font-size:16px;color:var(--ink);margin-bottom:6px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.finding .lbl{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:600;margin:12px 0 4px}
.finding p,.finding li{color:var(--body)}
.finding ol,.finding ul{margin-left:18px}
.gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:16px;padding:20px 24px}
.gallery figure{margin:0;background:var(--bg);border:1px solid var(--border);border-radius:10px;overflow:hidden}
.gallery img{display:block;width:100%;height:230px;object-fit:cover;object-position:top}
.gallery figcaption{padding:8px 10px;font-size:12px;color:var(--muted);word-break:break-all}
.videos{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px;padding:20px 24px}
.videos figure{margin:0;background:var(--bg);border:1px solid var(--border);border-radius:10px;overflow:hidden}
.videos video{display:block;width:100%;max-height:420px;background:#000}
.videos figcaption{padding:8px 10px;font-size:12.5px;color:var(--body)}
.matrix td{text-align:center;vertical-align:top}
.matrix td:first-child{text-align:left}
.matrix .thumb{margin-top:6px}
details.pag{border-top:1px solid var(--border-soft)}
details.pag:first-child{border-top:0}
details.pag summary{cursor:pointer;padding:14px 24px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;color:var(--ink);list-style:none}
details.pag summary::-webkit-details-marker{display:none}
details.pag summary:before{content:"▸";color:var(--muted)}
details.pag[open] summary:before{content:"▾"}
details.pag .pbody{padding:0 24px 20px 24px;display:grid;grid-template-columns:240px 1fr;gap:20px}
details.pag .pbody .thumb{width:240px;height:180px}
details.pag .pbody ul{margin-left:18px;color:var(--body)}
details.pag .pbody li{word-break:break-all;margin:2px 0}
.metr{display:flex;gap:18px;flex-wrap:wrap;margin-bottom:10px;color:var(--body);font-size:13px}
.metr b{color:var(--ink)}
@media (max-width:720px){details.pag .pbody{grid-template-columns:1fr}}
</style>
"""

# Lightbox: the thumbnails (a.lb) are enlarged on the same page; Esc or a click closes them.
JS_EXTRA = ""  # the evidence viewer is now shared (scripts/_report_styles.py)


def pill(ok, ok_text, bad_text, bad_tone=CRITICAL):
    return _pill(ok_text, OK, "✓") if ok else _pill(bad_text, bad_tone, "✕")


def short(url, base):
    """The URL without the site's origin, so the tables don't overflow."""
    if base and url and url.startswith(base):
        return url[len(base):] or "/"
    return url or ""


def origin(url):
    parts = (url or "").split("/")
    return "/".join(parts[:3]) if len(parts) >= 3 else ""


def sec(ms):
    return f"{(ms or 0) / 1000:.1f} s"


def auto_tone(findings):
    sev = {h["severity"] for h in findings}
    if "Critical" in sev:
        return "bad", "There are critical issues: pages that don't open or serious errors"
    if "High" in sev:
        return "warn", "There are important problems that should be fixed before release"
    if findings:
        return "warn", "No serious problems; minor remarks remain"
    return "ok", "No problems were found in the walkthrough"


def page_issues(p):
    return (len(p.get("js_errors") or []) + len(p.get("console_errors") or []) + len(p.get("failed_resources") or [])
            + len(p.get("broken_images") or []) + (1 if p.get("error") or (p.get("status") or 0) >= 400 else 0))


def build_html(data, analysis, hist_html=""):
    discarded = {str(d.get("id")): d.get("reason", "") for d in analysis.get("discarded") or []}
    notes = analysis.get("notes") or {}
    adjustments = analysis.get("severities") or {}
    base = origin(data.get("url"))
    cfg = data.get("config") or {}
    r = data.get("summary") or {}
    pags = data.get("pages") or []
    links = data.get("links") or []
    resp = data.get("responsive") or []
    videos = data.get("videos") or []

    automatic = []
    for h in data.get("findings") or []:
        if h.get("id") in discarded:
            continue
        h = dict(h)
        if adjustments.get(h.get("id")) in ORDER:
            h["severity"] = adjustments[h["id"]]
        automatic.append(h)
    exploratory = [dict(x, category="Manual exploration") for x in analysis.get("exploratory") or []]
    everything = sorted(automatic + exploratory, key=lambda h: ORDER.get(h.get("severity"), 9))
    count = lambda cat: sum(1 for h in everything if h.get("category") == cat)
    by_sev = {s: sum(1 for h in everything if h.get("severity") == s) for s, _ in SEVERITIES}

    body = []
    tone, text = auto_tone(everything)
    body.append(banner(analysis.get("verdict") or text, analysis.get("verdict_tone") or tone))

    # ---- Indicators
    errors = count("JavaScript error") + count("Console error")
    body.append('<div style="margin-top:20px">' + kpi_tiles([
        ("Findings", len(everything), "bad" if by_sev["Critical"] or by_sev["High"] else ("warn" if everything else "ok"),
         f'{by_sev["Critical"]} critical · {by_sev["High"]} high · {by_sev["Medium"]} medium · {by_sev["Low"]} low'),
        ("Pages crawled", r.get("pages", len(pags)), "",
         f'{r["uncrawled_pages"]} not crawled' if r.get("uncrawled_pages") else "all the ones found"),
        ("Broken links", count("Broken link"), "bad" if count("Broken link") else "ok",
         f'of {r.get("links", len(links))} · {r.get("unverifiable_links", 0)} unverifiable'),
        ("Broken images", count("Broken image"), "bad" if count("Broken image") else "ok", f'of {r.get("images", 0)} images'),
        ("JS and console errors", errors, "bad" if count("JavaScript error") else ("warn" if errors else "ok")),
        ("Failed resources", count("Failed resource"), "warn" if count("Failed resource") else "ok"),
        ("Responsive", count("Responsive"), "warn" if count("Responsive") else "ok", f'{len(cfg.get("resolutions") or [])} resolutions'),
        ("Average load", sec(r.get("load_avg_ms")), "warn" if count("Web performance") else "",
         f'max {sec(r.get("load_max_ms"))} · p90 {sec(r.get("load_p90_ms"))}'),
    ] + ([("Manual exploration", len(exploratory), "warn" if exploratory else "")] if exploratory or analysis else [])) + "</div>")

    if analysis.get("summary"):
        body.append(section("Executive summary", f'<div class="cardbody"><p class="lead">{e(analysis["summary"])}</p></div>'))

    # ---- Overview: pages and links
    healthy = sum(1 for p in pags if not page_issues(p))
    pct_pages = round(healthy / len(pags) * 100) if pags else 0
    seg_pages = [(healthy, OK, "No errors"), (len(pags) - healthy, CRITICAL, "With errors")]
    ok_l = sum(1 for l in links if l.get("result") == "ok")
    broken_l = sum(1 for l in links if l.get("result") == "broken")
    nov_l = sum(1 for l in links if l.get("result") == "unverifiable")
    pct_l = round(ok_l / len(links) * 100) if links else 0
    seg_l = [(ok_l, OK, "OK"), (broken_l, CRITICAL, "Broken"), (nov_l, NEUTRAL, "Unverifiable")]
    body.append(two_col(section("Pages", donut_panel(seg_pages, pct_pages, "healthy pages"), "without JS, console, resource or image errors"),
                        section("Links", donut_panel(seg_l, pct_l, "links ok"), "internal and external")))

    if everything:
        cats = sorted([(c, count(c), SERIES[0]) for c, _ in CATEGORIES if count(c)], key=lambda x: -x[1])
        body.append(two_col(section("Findings by severity", bar_chart([(s, by_sev[s], col) for s, col in SEVERITIES])),
                            section("Findings by type", bar_chart(cats, label_width=150))))

    # ---- Scope
    mission = f'<p><strong style="color:var(--ink)">Mission:</strong> {e(analysis["mission"])}</p>' if analysis.get("mission") else ""
    timebox = f' · manual exploration of {e(analysis["duration_min"])} min' if analysis.get("duration_min") else ""
    unvisited = (f'<p class="muted">{r["uncrawled_pages"]} page(s) of the site were left uncrawled because of the configured '
                 f'limit (raise --max-pages or --depth).</p>') if r.get("uncrawled_pages") else ""
    areas = ('<p><strong style="color:var(--ink)">Areas explored by hand:</strong> ' + e(", ".join(analysis["explored_areas"])) + "</p>"
             if analysis.get("explored_areas") else "")
    body.append(section("Scope and method", f'''<div class="cardbody">{mission}
      <p><strong style="color:var(--ink)">Automated crawl</strong> with Playwright from <span class="mono">{e(data.get("url"))}</span>:
      up to {e(cfg.get("max_pages"))} pages of the same site, {e(cfg.get("depth"))} levels deep,
      {"internal and external" if cfg.get("external", True) else "internal"} links; responsive at {e(", ".join(cfg.get("resolutions") or []))}
      ({e(cfg.get("responsive"))} page(s)); slow page from {sec(cfg.get("slow_ms", 3000))}{timebox}. Crawl duration: {e(data.get("duration_s"))} s.</p>
      <p>Only GET navigation was used: no forms were filled in or submitted in the automated crawl and no logout links were followed.
      In the screenshots, the elements with problems (broken images, elements that go off the screen, small touch targets) are marked in red.</p>
      {areas}{unvisited}</div>'''))

    # ---- Findings
    if everything:
        rows = []
        for h in everything:
            res = h.get("resolutions") or ([h["resolution"]] if h.get("resolution") else [])
            note = f'<div class="muted" style="margin-top:4px">{e(notes[h["id"]])}</div>' if h.get("id") in notes else ""
            rows.append([f'<span class="id">{e(h.get("id"))}</span>', level_badge(h.get("severity")), e(h.get("category")),
                         f'<strong style="color:var(--ink)">{e(h.get("title"))}</strong>'
                         f'<div class="mono muted">{e(h.get("detail") or h.get("actual") or "")}</div>{note}',
                         f'<span class="mono">{e(short(h.get("page"), base))}</span>'
                         + (f'<div class="muted" title="{e(chr(10).join(short(x, base) for x in h["pages"]))}">and {len(h["pages"]) - 1} more page(s)</div>'
                            if len(h.get("pages") or []) > 1 else "")
                         + (f'<div class="muted">{e(", ".join(res))}</div>' if res else ""),
                         thumbnail(h.get("evidence"), f'{h.get("id")} · {h.get("title")}')])
        body.append(section("All findings", table(["ID", "Severity", "Type", "Finding", "Page", "Evidence"], rows),
                            "click the screenshot to enlarge it"))
    else:
        body.append(section("Findings", '<div class="cardbody"><p>No problems were found in the crawled pages.</p></div>'))

    if exploratory:
        det = []
        for x in exploratory:
            steps = "".join(f"<li>{e(p)}</li>" for p in x.get("steps") or [])
            det.append(f'''<div class="finding"><h3>{e(x.get("id"))} · {e(x.get("title"))} {level_badge(x.get("severity"))}</h3>
              <div class="mono muted">{e(x.get("page"))}</div>
              {f'<div class="lbl">Steps</div><ol>{steps}</ol>' if steps else ""}
              {f'<div class="lbl">Expected result</div><p>{e(x["expected"])}</p>' if x.get("expected") else ""}
              {f'<div class="lbl">Actual result</div><p>{e(x["actual"])}</p>' if x.get("actual") else ""}
              {f'<div class="lbl">How to fix it</div><p>{e(x["fix"])}</p>' if x.get("fix") else ""}
              {f'<div class="lbl">Evidence</div>{thumbnail(x["evidence"], x.get("title", ""))}' if x.get("evidence") else ""}</div>''')
        body.append(section("Findings from the manual exploration", "".join(det)))

    # ---- Web performance
    with_time = sorted([p for p in pags if not p.get("error") and p.get("time_ms")], key=lambda p: -p["time_ms"])
    if with_time:
        slow = cfg.get("slow_ms") or 3000
        color = lambda ms: SERIOUS if ms >= slow * 2 else WARNING if ms >= slow else OK
        rows = [(short(p["url"], base), round(p["time_ms"] / 1000, 2), color(p["time_ms"])) for p in with_time[:20]]
        body.append(section("Load time per page", bar_chart(rows, label_width=240),
                            f"seconds · green < {sec(slow)} · yellow slow · orange very slow"))

    # ---- Responsive
    if resp:
        resolutions = list(dict.fromkeys(f["resolution"] for f in resp))
        names = {f["resolution"]: f.get("name", "") for f in resp}
        rows_sb = [(f'{names[x]} {x}', [sum(1 for f in resp if f["resolution"] == x and f.get(k)) for k in
                                         ("horizontal_overflow", "small_text", "small_touch_targets")]) for x in resolutions]
        series = [("Horizontal scroll", CRITICAL), ("Text < 12px", WARNING), ("Touch targets < 24px", SERIES[1])]
        if any(sum(v) for _, v in rows_sb):
            body.append(section("Responsive problems by resolution", stacked_bars(rows_sb, series), "affected pages"))
        pages_r = list(dict.fromkeys(f["url"] for f in resp))
        idx = {(f["url"], f["resolution"]): f for f in resp}
        rows = []
        for p in pages_r:
            cells = [f'<span class="mono">{e(short(p, base))}</span>']
            for res in resolutions:
                f = idx.get((p, res)) or {}
                if f.get("error"):
                    cells.append(_pill("Could not check", NEUTRAL, "⊘") + f'<div class="muted" style="font-size:11px">{e(f["error"][:80])}</div>')
                    continue
                warnings = [t for k, t in (("small_text", "small text"), ("small_touch_targets", "small touch targets")) if f.get(k)]
                status = (_pill("Overflows", CRITICAL, "✕") if f.get("horizontal_overflow")
                          else _pill("With warnings", WARNING, "!") if warnings else _pill("OK", OK, "✓"))
                det = f'<div class="muted" style="font-size:11px">{e(", ".join(warnings))}</div>' if warnings else ""
                cells.append(status + det + "<div>" + thumbnail(f.get("screenshot"), f'{short(p, base)} · {res}', "s") + "</div>")
            rows.append(cells)
        tbl = table(["Page"] + [f"{names[x]} {x}" for x in resolutions], rows).replace("<table>", '<table class="matrix">', 1)
        body.append(section("Responsive: page by resolution", tbl,
                            "horizontal scroll, text < 12px and touch targets < 24px (WCAG 2.5.8)"))

    # ---- Videos
    if videos:
        figs = "".join(f'<figure><video controls preload="metadata" src="{e(v["file"])}#t=1"></video>'
                       f'<figcaption>{e(v.get("title", v["file"]))} · <a href="{e(v["file"])}" download style="color:var(--ink)">download</a></figcaption></figure>'
                       for v in videos)
        body.append(section("Videos", f'<div class="videos">{figs}</div>', "the full walkthrough and each resolution"))

    # ---- Galleries
    caps = [p for p in pags if p.get("screenshot")]
    if caps:
        figs = "".join(f'<figure>{thumbnail(p["screenshot"], short(p["url"], base)).replace("thumb", "", 1)}'
                       f'<figcaption>{e(short(p["url"], base))}{" · " + str(page_issues(p)) + " error(s)" if page_issues(p) else ""}</figcaption></figure>'
                       for p in caps)
        body.append(section("Page screenshots", f'<div class="gallery">{figs}</div>', "desktop · full page"))
    caps_r = [f for f in resp if f.get("screenshot")]
    if caps_r:
        figs = "".join(f'<figure>{thumbnail(f["screenshot"], short(f["url"], base) + " · " + f["resolution"]).replace("thumb", "", 1)}'
                       f'<figcaption>{e(short(f["url"], base))} · {e(f.get("name", ""))} {e(f["resolution"])}'
                       f'{" · overflows" if f.get("horizontal_overflow") else ""}</figcaption></figure>' for f in caps_r)
        body.append(section("Responsive screenshots", f'<div class="gallery">{figs}</div>', "each page at each resolution"))

    # ---- Links
    broken = [l for l in links if l.get("result") == "broken"]
    doubtful = [l for l in links if l.get("result") == "unverifiable"]
    if broken:
        rows = [[f'<span class="mono">{e(l["url"])}</span>' + (f'<div class="muted">"{e(l["text"])}"</div>' if l.get("text") else ""),
                 e("Internal" if l.get("internal") else "External"), e(l.get("status") or l.get("error") or "—"),
                 "<br>".join(f'<span class="mono">{e(short(o, base))}</span>' for o in l.get("sources", [])[:5])
                 + (f'<div class="muted">… and {len(l["sources"]) - 5} more</div>' if len(l.get("sources", [])) > 5 else "")]
                for l in broken]
        body.append(section("Broken links", table(["Link", "Type", "Response", "Appears on"], rows)))
    if doubtful:
        rows = [[f'<span class="mono">{e(l["url"])}</span>', e(l.get("status") or "—"), e(l.get("error") or "Requires login or blocks robots")]
                for l in doubtful]
        body.append(section("Links that could not be verified", table(["Link", "Response", "Reason"], rows),
                            "they are not necessarily errors: review them by hand"))

    # ---- Detail per page
    if pags:
        rows = []
        for p in pags:
            m = p.get("metrics") or {}
            rows.append([f'<span class="mono">{e(short(p["url"], base))}</span>' + (f'<div class="muted">{e(p.get("title"))}</div>' if p.get("title") else ""),
                         pill(not p.get("error") and 0 < (p.get("status") or 0) < 400, str(p.get("status")), str(p.get("error") and "error" or p.get("status"))),
                         e(sec(p.get("time_ms"))), e(f'{m["ttfb_ms"]} ms' if m.get("ttfb_ms") is not None else "—"),
                         e(m.get("requests", "—")), e(f'{m["size_kb"]} KB' if m.get("size_kb") is not None else "—"),
                         e(p.get("links", 0)), e(p.get("images", 0)),
                         pill(not page_issues(p), "0", str(page_issues(p)))])
        body.append(section("Pages crawled", table(["Page", "Status", "Load", "First byte", "Requests", "Approx. size",
                                                    "Links", "Images", "Errors"], rows)))
        blocks = []
        for p in pags:
            m = p.get("metrics") or {}
            lists = []
            for title, items in (("JavaScript errors", p.get("js_errors")), ("Console errors", p.get("console_errors")),
                                 ("Failed resources", [f'{x.get("type") or "resource"} {x.get("status") or x.get("error") or ""} · {x.get("url")}' for x in p.get("failed_resources") or []]),
                                 ("Broken images", [f'{x.get("src")}' + (f' (HTTP {x["status"]})' if x.get("status") else "") for x in p.get("broken_images") or []]),
                                 ("Images without alt", p.get("examples_without_alt"))):
                if items:
                    lists.append(f'<div class="lbl" style="font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:600;margin:10px 0 4px">{e(title)} ({len(items)})</div>'
                                 "<ul>" + "".join(f'<li class="mono">{e(i)}</li>' for i in items[:15]) + "</ul>")
            metr = (f'<div class="metr"><span>Status <b>{e(p.get("status") or p.get("error"))}</b></span><span>Load <b>{sec(p.get("time_ms"))}</b></span>'
                    + (f'<span>First byte <b>{m["ttfb_ms"]} ms</b></span><span>DOM ready <b>{m.get("dom_ms")} ms</b></span>'
                       f'<span>Requests <b>{m.get("requests")}</b></span><span>Approx. size <b>{m.get("size_kb")} KB</b></span>' if m.get("ttfb_ms") is not None else "")
                    + (f'<span>Redirects to <b class="mono">{e(p["redirects_to"])}</b></span>' if p.get("redirects_to") else "") + "</div>")
            n = page_issues(p)
            blocks.append(f'''<details class="pag"{" open" if n else ""}><summary><span class="mono">{e(short(p["url"], base))}</span>
                {pill(not n, "No errors", f"{n} error(s)")}<span class="muted">{e(p.get("title") or "")}</span></summary>
                <div class="pbody"><div>{thumbnail(p.get("screenshot"), short(p["url"], base))}</div>
                <div>{metr}{"".join(lists) or '<p class="muted">No JavaScript, console, resource or image errors.</p>'}</div></div></details>''')
        body.append(section("Detail per page", "".join(blocks), "the pages with errors are open"))

    # ---- Closing
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
                      ("Tool", "Playwright · crawl + exploration")])
    return page("Exploratory testing report", "Exploratory testing", meta_html, CSS_EXTRA + "".join(body) + JS_EXTRA)


def main():
    for stream in (sys.stdout, sys.stderr):  # accents shown properly in the Windows console
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="HTML exploratory testing report from exploration.json")
    ap.add_argument("exploration_json")
    ap.add_argument("output")
    ap.add_argument("--analysis", help="JSON with verdict, summary, manual findings, discarded and recommendations")
    a = ap.parse_args()
    if not a.output.lower().endswith(".html"):
        sys.exit("The output must end in .html")
    with open(a.exploration_json, encoding="utf-8") as f:
        data = json.load(f)
    analysis = {}
    if a.analysis:
        with open(a.analysis, encoding="utf-8") as f:
            analysis = json.load(f)
        warn_analysis(analysis, [h.get("id") for h in data.get("findings") or []] + [x.get("id") for x in analysis.get("exploratory") or []])
    hist_html = _history.section("exploratory", Path(a.exploration_json).resolve().parent, data)
    with open(a.output, "w", encoding="utf-8") as f:
        f.write(build_html(data, analysis, hist_html=hist_html))
    print(f"OK: {a.output}")


if __name__ == "__main__":
    main()
