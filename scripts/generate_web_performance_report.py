#!/usr/bin/env python3
"""
Generates the web performance HTML report (dashboard, dark mode) from the Lighthouse
audit (web-performance.json, from `npm run web-performance`) and, optionally, from the analysis of the
web-performance-auditor agent. `npm run web-performance` already generates it on its own when it finishes; the agent
generates it again with its analysis.

Usage:
    python scripts/generate_web_performance_report.py <web-performance.json> <output.html> [--analysis analysis.json]

What it shows: verdict, indicators (mobile and desktop score, Core Web Vitals in green, worst
metrics, weight and requests), scores per page, Core Web Vitals per page with their rating
(good / needs improvement / poor), LCP per page, the improvement opportunities with their estimated savings and the
resources that cause them, the weight per resource type, the LCP element, the third parties, the loading
sequence and the final screenshot, and the link to the native Lighthouse report of each page.

The data comes from web-performance.json. The analysis (optional) provides:
{
  "verdict": "Acceptable performance on desktop; mobile needs improvement", "verdict_tone": "warn",
  "summary": "Summary for a non-technical person...",
  "notes": {"R-02": "Caching is configured by the CDN: the infrastructure team confirms it"},
  "discarded": [{"id": "R-05", "reason": "The third-party script is the support chat, it is accepted"}],
  "severities": {"R-03": "High"},
  "missing_info": [{"id": "MI-01", "what_is_missing": "...", "question": "..."}],   // "description" works as an alias of what_is_missing
  "recommendations": [{"action": "...", "reason": "...", "priority": "High"}],
  "next_steps": ["..."]
}
"""
import argparse
import datetime
import json
from pathlib import Path
import math
import sys

import _history
from _report_styles import (missing_info, warn_analysis, e, page, meta, section, kpi_tiles, banner, doc_list, table, bar_chart, stacked_bars,
                              grouped_columns, two_col, level_badge, _pill, CRITICAL, WARNING, NEUTRAL, OK, SERIES, SERIOUS,
                              SURFACE)
from generate_exploratory_report import CSS_EXTRA, JS_EXTRA, thumbnail, short, origin

SEVERITIES = [("Critical", CRITICAL), ("High", SERIOUS), ("Medium", WARNING), ("Low", NEUTRAL)]
ORDER = {s: i for i, (s, _) in enumerate(SEVERITIES)}
STATUS = {"good": ("Good", OK, "✓"), "needs-improvement": ("Needs improvement", WARNING, "!"), "poor": ("Poor", CRITICAL, "✕")}
TYPES = ["Document", "JavaScript", "CSS", "Images", "Fonts", "Video and audio", "Data (fetch/XHR)", "Other"]
DEV = {"mobile": "Mobile", "desktop": "Desktop"}

CSS_WPERF = """
<style>
.gauges{display:grid;grid-template-columns:repeat(auto-fill,minmax(400px,1fr));gap:16px;padding:12px 24px 24px}
.gcard{background:var(--tile);border:1px solid var(--border);border-radius:16px;padding:16px 18px}
.gcard .u{font-size:12.5px;color:var(--ink);font-weight:650;margin-bottom:12px;word-break:break-all}
.grow{display:flex;gap:10px;justify-content:space-around;flex-wrap:wrap}
.g{display:flex;flex-direction:column;align-items:center;gap:6px;width:80px;text-align:center;font-size:10.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.1em;font-weight:650}
.gnum{font-size:22px;font-weight:760;fill:var(--ink)}
.film{display:flex;gap:10px;overflow-x:auto;padding:4px 0 10px}
.film figure{margin:0;flex:none;width:96px;text-align:center}
.film .thumb{width:96px;height:170px}
.film .thumb img{object-fit:contain;background:#000}
.film .thumb::before{display:none}
.film.desktop figure{width:150px}.film.desktop .thumb{width:150px;height:100px}
.film figcaption{font-size:11px;color:var(--muted);margin-top:4px;font-variant-numeric:tabular-nums}
.filmrow{padding:14px 24px;border-top:1px solid var(--border-soft)}
.filmrow:first-of-type{border-top:0}
.filmrow .t{font-size:12.5px;color:var(--body);margin-bottom:8px}
</style>
"""


def ring(value, label, size=74):
    """0-100 score ring (like Lighthouse): green from 90, yellow from 50, red below."""
    if value is None:
        return f'<div class="g"><svg width="{size}" height="{size}"></svg>{e(label)}</div>'
    color = OK if value >= 90 else WARNING if value >= 50 else CRITICAL
    r = size / 2 - 7
    c = 2 * math.pi * r
    length = c * value / 100
    status = "good" if value >= 90 else "needs improvement" if value >= 50 else "poor"
    return (f'<div class="g" data-tip="{e(label)}: {value}/100 ({status})" tabindex="0"><svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
            f'<circle cx="{size / 2}" cy="{size / 2}" r="{r}" fill="none" stroke="#2E281F" stroke-width="7"/>'
            f'<circle cx="{size / 2}" cy="{size / 2}" r="{r}" fill="none" stroke="{color}" stroke-width="7" stroke-linecap="round" '
            f'stroke-dasharray="{length:.1f} {c - length:.1f}" transform="rotate(-90 {size / 2} {size / 2})"/>'
            f'<text x="{size / 2}" y="{size / 2 + 7}" text-anchor="middle" class="gnum">{value}</text></svg>{e(label)}</div>')


def metric_pill(m):
    if not m:
        return '<span class="muted">—</span>'
    name, color, icon = STATUS.get(m.get("status"), ("—", NEUTRAL, "●"))
    return _pill(f'{m.get("text", "")} · {name}', color, icon)


def kb(bytes_):
    return f"{(bytes_ or 0) / 1024:,.0f} KB" if (bytes_ or 0) < 1024 * 1024 else f"{bytes_ / 1048576:.1f} MB"


def auto_tone(res):
    ok = [r for r in res if not r.get("error")]
    statuses = [m.get("status") for r in ok for k, m in (r.get("metrics") or {}).items() if k in ("lcp", "cls", "tbt")]
    if any(r.get("error") for r in res) or "poor" in statuses:
        return "bad", "There are Core Web Vitals in red: loading is slow or unstable for people"
    scores = [r["scores"].get("performance") for r in ok if r["scores"].get("performance") is not None]
    if "needs-improvement" in statuses or any(p < 90 for p in scores):
        return "warn", "Performance needs improvement: there are metrics outside Google's recommendations"
    return "ok", "Good performance in what was measured (lab data)"


def build_html(data, analysis, hist_html=""):
    discarded = {str(d.get("id")): d.get("reason", "") for d in analysis.get("discarded") or []}
    notes = analysis.get("notes") or {}
    adjustments = analysis.get("severities") or {}
    base = origin(data.get("url"))
    res = data.get("results") or []
    ok = [r for r in res if not r.get("error")]
    r = data.get("summary") or {}
    cfg = data.get("config") or {}
    devices = cfg.get("devices") or ["mobile", "desktop"]
    pages = list(dict.fromkeys(x["url"] for x in res))

    findings = []
    for h in data.get("findings") or []:
        if h.get("id") in discarded:
            continue
        h = dict(h)
        if adjustments.get(h.get("id")) in ORDER:
            h["severity"] = adjustments[h["id"]]
        findings.append(h)
    findings.sort(key=lambda h: ORDER.get(h.get("severity"), 9))

    body = []
    tone, text = auto_tone(res)
    body.append(banner(analysis.get("verdict") or text, analysis.get("verdict_tone") or tone))

    def worst(key, dev):
        xs = [x["metrics"][key] for x in ok if x["device"] == dev and key in (x.get("metrics") or {})]
        return max(xs, key=lambda m: m["value"]) if xs else None

    main_device = "mobile" if "mobile" in devices else devices[0]
    tiles = []
    for d in devices:
        p = r.get(f"web_performance_{d}")
        tiles.append((f"Performance {DEV[d].lower()}", "—" if p is None else p, "" if p is None else "ok" if p >= 90 else "warn" if p >= 50 else "bad",
                      "average Lighthouse score (0-100)", "bolt", {"pct": p or 0}))
    v = r.get(f"vitals_ok_{main_device}")
    tiles.append((f"Core Web Vitals in green ({DEV[main_device].lower()})", "—" if v is None else f"{v}/{len(pages)}",
                  "" if v is None else "ok" if v == len(pages) else "warn", "pages with good LCP, CLS and TBT", "target"))
    for key, ic in (("lcp", "clock"), ("tbt", "code"), ("cls", "screen")):
        m = worst(key, main_device)
        tone_m = {"good": "ok", "needs-improvement": "warn", "poor": "bad"}.get(m["status"]) if m else ""
        tiles.append((f"Worst {key.upper()} ({DEV[main_device].lower()})", m["text"] if m else "—", tone_m, "", ic))
    weights = [x["total_size"] for x in ok if x["device"] == main_device]
    reqs = [x["requests"] for x in ok if x["device"] == main_device]
    tiles.append(("Average weight per page", kb(sum(weights) / len(weights)) if weights else "—", "",
                  f"{round(sum(reqs) / len(reqs))} requests on average" if reqs else "", "load"))
    tiles.append(("Improvement opportunities", r.get("opportunities", 0), "warn" if r.get("opportunities") else "ok", "audits with estimated savings", "search"))
    body.append('<div style="margin-top:20px">' + kpi_tiles(tiles) + "</div>")

    if analysis.get("summary"):
        body.append(section("Executive summary", f'<div class="cardbody"><p class="lead">{e(analysis["summary"])}</p></div>'))

    # ---- Scores per page
    cards = []
    for u in pages:
        rings = []
        for d in devices:
            x = next((y for y in ok if y["url"] == u and y["device"] == d), None)
            rings.append(ring(x["scores"].get("performance") if x else None, f"Performance {DEV[d]}"))
        x = next((y for y in ok if y["url"] == u), None)
        if x:
            rings.append(ring(x["scores"].get("best-practices"), "Best practices"))
            rings.append(ring(x["scores"].get("seo"), "SEO"))
        cards.append(f'<div class="gcard"><div class="u mono">{e(short(u, base))}</div><div class="grow">{"".join(rings)}</div></div>')
    body.append(section("Scores per page", f'<div class="gauges">{"".join(cards)}</div>',
                        "green 90-100 · yellow 50-89 · red 0-49"))

    if len(devices) > 1 and len(pages) > 1:
        series = [(DEV[d], SERIES[1] if d == "mobile" else SERIES[2],
                   [next((y["scores"].get("performance") for y in ok if y["url"] == u and y["device"] == d), None) for u in pages])
                  for d in devices]
        body.append(section("Performance per page and device", grouped_columns([short(u, base) for u in pages], series, height=280),
                            "Lighthouse score (0-100)"))

    # ---- Core Web Vitals
    rows = []
    for x in res:
        cells = [f'<span class="mono">{e(short(x["url"], base))}</span>', e(DEV.get(x["device"], x["device"]))]
        if x.get("error"):
            cells += [_pill("Could not be measured", CRITICAL, "✕")] + ["—"] * 4
        else:
            cells += [metric_pill((x.get("metrics") or {}).get(k)) for k in ("lcp", "cls", "tbt", "fcp", "si")]
        cells.append(f'<a href="{e(x["lighthouse"])}" target="_blank" style="color:var(--ink)">open</a>' if x.get("lighthouse") else "—")
        rows.append(cells)
    body.append(section("Core Web Vitals and metrics", table(["Page", "Device", "LCP", "CLS", "TBT", "FCP", "Speed Index", "Lighthouse"], rows),
                        "LCP, CLS and TBT are the Core Web Vitals (TBT is the lab equivalent of INP)"))

    lcps = sorted([(f'{short(x["url"], base)} · {DEV[x["device"]]}', round(x["metrics"]["lcp"]["value"] / 1000, 2),
                    {"good": OK, "needs-improvement": WARNING, "poor": CRITICAL}[x["metrics"]["lcp"]["status"]])
                   for x in ok if "lcp" in (x.get("metrics") or {})], key=lambda t: -t[1])
    if lcps:
        body.append(section("LCP per page", bar_chart(lcps[:16], label_width=260),
                            "seconds until the main content is visible · green ≤ 2.5 s · yellow ≤ 4 s · red more than 4 s"))

    # ---- Findings
    if findings:
        rows = []
        for h in findings:
            note = f'<div class="muted" style="margin-top:4px">{e(notes[h["id"]])}</div>' if h.get("id") in notes else ""
            pgs = h.get("pages") or [h.get("page")]
            rows.append([f'<span class="id">{e(h["id"])}</span>', level_badge(h.get("severity")), e(h.get("category")),
                         f'<strong style="color:var(--ink)">{e(h.get("title"))}</strong><div class="muted">{e(h.get("detail"))}</div>{note}',
                         f'<span class="mono">{e(short(pgs[0], base))}</span>' + (f'<div class="muted">and {len(pgs) - 1} more</div>' if len(pgs) > 1 else ""),
                         e(h.get("device", ""))])
        body.append(section("All findings", table(["ID", "Severity", "Type", "Finding", "Page", "Device"], rows)))

    # ---- Opportunities
    ops = data.get("opportunities") or []
    if ops:
        rows_g = [(o["title"], round(o["savings_ms_max"] / 1000, 2), SERIES[0]) for o in ops if o.get("savings_ms_max")][:10]
        if rows_g:
            body.append(section("Opportunities by time savings", bar_chart(rows_g, label_width=320), "seconds that could be saved, on the most affected page"))
        det = []
        for o in ops:
            items = "".join(f'<li class="mono">{e(it["url"][:140])}'
                            + (f' <span class="muted">· {kb(it["savings_bytes"])} of savings</span>' if it.get("savings_bytes") else "")
                            + (f' <span class="muted">· {it["savings_ms"] / 1000:.1f} s</span>' if it.get("savings_ms") else "") + "</li>"
                            for it in o.get("items") or [])
            savings = " · ".join(x for x in [f'up to {o["savings_ms_max"] / 1000:.1f} s' if o.get("savings_ms_max") else "",
                                             f'up to {kb(o["savings_bytes_max"])}' if o.get("savings_bytes_max") else ""] if x)
            det.append(f'''<div class="finding"><h3>{e(o["title"])} {_pill(savings or "improvement", SERIES[0], "↓")}</h3>
              <p class="muted">{e(len(o.get("pages") or []))} page(s) · {e(", ".join(DEV.get(d, d) for d in o.get("devices") or []))}
                {(" · affects " + e(", ".join(o["metrics"]))) if o.get("metrics") else ""}</p>
              <div class="lbl">What it is and how to fix it</div><p>{e(o.get("description"))}</p>
              {f'<div class="lbl">Resources that cause it</div><ul>{items}</ul>' if items else ""}
              {f'<p><a href="{e(o["more_info"])}" target="_blank" rel="noopener" style="color:var(--ink)">More information</a></p>' if o.get("more_info") else ""}</div>''')
        body.append(section("Improvement opportunities", "".join(det), "Lighthouse audits that fail and estimate a savings"))

    # ---- Weight per resource type
    rows_p = []
    for x in ok:
        if x["device"] != main_device:
            continue
        rsc = x.get("resources") or {}
        rows_p.append((short(x["url"], base), [round((rsc.get(t) or {}).get("bytes", 0) / 1024) for t in TYPES]))
    if rows_p:
        body.append(section("Weight per resource type", stacked_bars(rows_p, [(t, SERIES[i]) for i, t in enumerate(TYPES)]),
                            f"KB transferred per page ({DEV[main_device].lower()})"))

    # ---- LCP and third parties
    rows_l = [[f'<span class="mono">{e(short(x["url"], base))}</span>', e(DEV[x["device"]]),
               f'<span class="mono" style="color:var(--ink)">{e(x["lcp"].get("selector"))}</span><div class="muted">{e(x["lcp"].get("label"))}</div>']
              for x in ok if x.get("lcp")]
    if rows_l:
        body.append(section("LCP element", table(["Page", "Device", "Element that defines the LCP"], rows_l),
                            "the largest content painted: optimizing it lowers the LCP"))
    third = {}
    for x in ok:
        for t in x.get("third_parties") or []:
            a = third.setdefault(t["entity"], {"bytes": 0, "blocking_ms": 0, "pages": 0})
            a["bytes"] = max(a["bytes"], t["bytes"])
            a["blocking_ms"] = max(a["blocking_ms"], t["blocking_ms"])
            a["pages"] += 1
    if third:
        rows_t = [[e(n), kb(v["bytes"]), f'{v["blocking_ms"]} ms', e(v["pages"])] for n, v in sorted(third.items(), key=lambda kv: -kv[1]["blocking_ms"])]
        body.append(section("Third-party code", table(["Provider", "Weight", "Main thread blocking", "Measurements"], rows_t)))

    # ---- Loading sequence
    rows_f = []
    for x in ok:
        if not x.get("sequence"):
            continue
        name = short(x["url"], base)
        figs = "".join(f'<figure>{thumbnail(f["screenshot"], name + " at " + format(f["ms"] / 1000, ".1f") + " s")}'
                       f'<figcaption>{f["ms"] / 1000:.1f} s</figcaption></figure>' for f in x["sequence"])
        rows_f.append(f'<div class="filmrow"><div class="t"><span class="mono">{e(short(x["url"], base))}</span> · {e(DEV[x["device"]])}</div>'
                      f'<div class="film {e(x["device"])}">{figs}</div></div>')
    if rows_f:
        body.append(section("Loading sequence", "".join(rows_f), "how the page looks while it loads (click to enlarge)"))

    # ---- Scope
    th = cfg.get("thresholds") or {}
    rows_u = [[e(v.get("name")), e(v.get("title")), e(f'≤ {v["good"] / 1000:g} s' if v.get("unit") == "ms" else f'≤ {v["good"]}'),
               e(f'> {v["poor"] / 1000:g} s' if v.get("unit") == "ms" else f'> {v["poor"]}')] for v in th.values()]
    body.append(section("Scope and method", f'''<div class="cardbody">
      <p><strong style="color:var(--ink)">{e(data.get("tool", "Lighthouse"))}</strong> on {len(pages)} page(s) from
      <span class="mono">{e(data.get("url"))}</span>, on {e(" and ".join(DEV[d].lower() for d in devices))}
      (mobile: Moto G on slow 4G, Google's standard), {e(cfg.get("repetitions", 1))} repetition(s) per page (the median is taken).
      Duration: {e(data.get("duration_s"))} s.</p>
      <p><strong style="color:var(--ink)">Lab data:</strong> a simulated load under fixed conditions, useful for finding
      and comparing problems. It does not replace real-user data (Chrome UX Report): real performance depends on each person's device and network.</p></div>'''
                        + (table(["Metric", "Name", "Good", "Poor"], rows_u) if rows_u else "")))

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

    errors = [x for x in res if x.get("error")]
    if errors:
        body.append(section("Measurements that failed", table(["Page", "Device", "Error"],
                                                              [[e(x["url"]), e(x["device"]), e(x["error"])] for x in errors])))

    date = (data.get("date") or datetime.datetime.now().isoformat())[:16].replace("T", " ")
    if hist_html:
        body.append(hist_html)
    meta_html = meta([("Story", data.get("story")), ("Site", data.get("host")), ("Date", date),
                      ("Tool", data.get("tool"))])
    return page("Web performance report", "Web performance", meta_html, CSS_EXTRA + CSS_WPERF + "".join(body) + JS_EXTRA)


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Web performance HTML report from web-performance.json")
    ap.add_argument("web_performance_json")
    ap.add_argument("output")
    ap.add_argument("--analysis", help="JSON with verdict, summary, notes, discards and recommendations")
    a = ap.parse_args()
    if not a.output.lower().endswith(".html"):
        sys.exit("The output must end in .html")
    with open(a.web_performance_json, encoding="utf-8") as f:
        data = json.load(f)
    analysis = {}
    if a.analysis:
        with open(a.analysis, encoding="utf-8") as f:
            analysis = json.load(f)
        warn_analysis(analysis, [h.get("id") for h in data.get("findings") or []])
    hist_html = _history.section("web-performance", Path(a.web_performance_json).resolve().parent, data)
    with open(a.output, "w", encoding="utf-8") as f:
        f.write(build_html(data, analysis, hist_html=hist_html))
    print(f"OK: {a.output}")


if __name__ == "__main__":
    main()
