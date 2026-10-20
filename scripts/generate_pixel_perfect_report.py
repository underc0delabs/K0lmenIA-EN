#!/usr/bin/env python3
"""
Generates the Visual regression (pixel perfect) report in HTML (dashboard, dark mode) from
pixel-perfect.json (npm run pixel-perfect) and, optionally, from the pixel-perfect agent's analysis.

Usage:
    python scripts/generate_pixel_perfect_report.py <pixel-perfect.json> <output.html> [--analysis analysis.json]

What it shows: verdict, indicators (screens compared, no changes, with changes, shifted,
missing and new elements, largest difference), difference per screen, findings by type and
severity, the page × resolution matrix, each screen with the slider comparator (reference
against actual, or against the diff map), the regions with changes up close and the before and
after of each finding, the findings table and the reference data.

The analysis (optional) provides:
{
  "verdict": "The buy button shifted on mobile", "verdict_tone": "bad",
  "summary": "Summary for a non-technical person...",
  "findings": {"V-01": {"intentional": true, "note": "Change requested in US-014"},
               "V-02": {"severity": "High", "note": "It covers the price at 390px"}},
  "missing_info": [{"id": "MI-01", "what_is_missing": "...", "question": "..."}],   // "description" works as an alias of what_is_missing
  "recommendations": [{"action": "...", "reason": "...", "priority": "High"}],
  "next_steps": ["..."]
}
The findings marked as intentional do not count as defects: they are listed separately and accepted
as the new reference (npm run pixel-perfect -- --accept <screen>).
"""
import argparse
import json
from pathlib import Path
import sys
from collections import Counter

import _history
from _report_styles import (missing_info, warn_analysis, e, page, meta, section, kpi_tiles, banner, doc_list, table, bar_chart, column_chart, donut_panel,
                            two_col, level_badge, _pill, thumbnail, LEVEL_COLOR, CRITICAL, WARNING, NEUTRAL, OK, SERIOUS, SERIES)
from generate_exploratory_report import CSS_EXTRA

TYPES = ["Shifted block", "Shifted element", "Missing element", "Changed text", "Style change",
         "Size change", "New element", "Visual change", "Page height"]
COLOR_TYPE = {t: SERIES[i % len(SERIES)] for i, t in enumerate(TYPES)}
STATE = {"No changes": (OK, "✓"), "Minor changes": (WARNING, "!"), "With changes": (CRITICAL, "✕"), "New": (NEUTRAL, "+"),
         "Reference": (SERIES[2], "◎"), "Error": (NEUTRAL, "⊘")}
SEV = ["Critical", "High", "Medium", "Low"]

CSS_PP = """
<style>
.comp-wrap{padding:18px 24px 6px}
.comp-bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:10px;font-size:12.5px;color:var(--muted)}
.comp-bar .side{display:inline-flex;align-items:center;gap:6px;color:var(--ink);font-weight:600}
.comp-bar .side i{width:9px;height:9px;border-radius:3px;display:inline-block}
.comp-bar input[type=range]{flex:1;min-width:160px;accent-color:var(--accent)}
.comp-bar button{background:var(--tile);border:1px solid var(--border);color:var(--ink);border-radius:999px;padding:5px 12px;
  font:inherit;font-size:12px;cursor:pointer}
.comp-bar button.on{background:var(--accent);color:#0E0C09;border-color:transparent}
.comp{position:relative;max-height:640px;overflow:auto;border:1px solid var(--border);border-radius:12px;background:#120F0B;margin:0 auto}
.comp .canvas{position:relative}
.comp img{display:block;width:100%;height:auto;user-select:none;-webkit-user-drag:none}
.comp .over{position:absolute;left:0;top:0;width:100%;clip-path:inset(0 calc(100% - var(--x,50%)) 0 0)}
.comp .line{position:absolute;top:0;bottom:0;left:var(--x,50%);width:2px;margin-left:-1px;background:#fff;
  box-shadow:0 0 0 1px rgba(0,0,0,.45),0 0 14px rgba(0,0,0,.5);pointer-events:none}
.comp .line:after{content:"◂ ▸";position:sticky;top:45%;display:block;margin-left:-17px;width:36px;text-align:center;font-size:11px;
  background:#fff;color:#111;border-radius:999px;padding:3px 0}
.comp.diff .over,.comp.diff .line{display:none}
.regs{display:grid;gap:14px;padding:6px 24px 18px}
.reg{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;align-items:start;background:var(--bg);border:1px solid var(--border);
  border-radius:12px;padding:12px}
.reg figure{margin:0}
.reg figcaption{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:600;margin-bottom:6px}
.reg img{display:block;width:100%;height:auto;border-radius:8px;border:1px solid var(--border);background:#fff}
.ba{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:8px}
.ba figure{margin:0}
.ba figcaption{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:600;margin-bottom:6px}
.ba img{display:block;width:100%;max-height:300px;object-fit:contain;object-position:left top;border-radius:8px;border:1px solid var(--border);background:#120F0B}
.delta{display:inline-flex;gap:6px;flex-wrap:wrap}
.delta span{font-family:var(--mono);font-size:12px;padding:3px 8px;border-radius:6px;background:var(--tile);border:1px solid var(--border);color:var(--ink)}
.sw{display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:-2px;border:1px solid rgba(244,239,230,.25);margin:0 3px}
.cell{display:flex;flex-direction:column;align-items:center;gap:6px}
.cell .pct{font-family:var(--mono);font-size:12px;color:var(--muted)}
.intentional{opacity:.62}
.cat{display:inline-flex;align-items:center;gap:7px;font-size:12px;font-weight:650;padding:4px 11px;border-radius:999px;
  background:var(--tile);border:1px solid var(--border);color:var(--ink);white-space:nowrap}
.cat i{width:9px;height:9px;border-radius:3px}
@media (max-width:720px){.reg{grid-template-columns:1fr}.ba{grid-template-columns:1fr}}
</style>
"""

JS_PP = """
<script>
document.querySelectorAll('.comp-wrap').forEach(function(w){
  var c=w.querySelector('.comp'),r=w.querySelector('input[type=range]'),base=c.querySelector('.base');
  r.addEventListener('input',function(){c.style.setProperty('--x',r.value+'%')});
  w.querySelectorAll('button[data-mode]').forEach(function(b){b.addEventListener('click',function(){
    w.querySelectorAll('button[data-mode]').forEach(function(x){x.classList.toggle('on',x===b)});
    var diff=b.dataset.mode==='diff';c.classList.toggle('diff',diff);base.src=diff?base.dataset.diff:base.dataset.act;
    r.disabled=diff;});});
});
</script>
"""


def status_pill(state):
    color, ic = STATE.get(state, (NEUTRAL, "●"))
    return _pill(state or "—", color, ic)


def type_pill(t):
    return f'<span class="cat"><i style="background:{COLOR_TYPE.get(t, NEUTRAL)}"></i>{e(t)}</span>'


def short(p):
    path = p["url"].split("://", 1)[-1].split("/", 1)
    return ("/" + path[1]) if len(path) > 1 and path[1] else "/"


def comparator(p):
    width = p.get("vp_width") or 1366
    maxw = f"max-width:{min(width, 1366)}px" if width < 1024 else ""
    return f'''<div class="comp-wrap">
  <div class="comp-bar"><span class="side"><i style="background:{SERIES[2]}"></i>Reference</span>
    <input type="range" min="0" max="100" value="50" aria-label="Slide between reference and actual">
    <span class="side"><i style="background:{SERIES[1]}"></i>Actual</span>
    <button type="button" data-mode="slide" class="on">Slide</button><button type="button" data-mode="diff">View differences</button>
    <a class="lb" href="{e(p["diff"])}" title="Differences · {e(p["id"])}" style="color:var(--ink);font-size:12px">Enlarge differences</a></div>
  <div class="comp" style="{maxw}"><div class="canvas">
    <img class="base" src="{e(p["actual"])}" data-act="{e(p["actual"])}" data-diff="{e(p["diff"])}" alt="Actual · {e(p["id"])}">
    <img class="over" src="{e(p["reference"])}" alt="Reference · {e(p["id"])}"><div class="line"></div></div></div></div>'''


def before_after(h):
    figs = ""
    if h.get("before"):
        figs += f'<figure><figcaption>Reference</figcaption><a class="lb" href="{e(h["before"])}" title="{e(h["id"])} · reference"><img src="{e(h["before"])}" loading="lazy" alt="Reference"></a></figure>'
    if h.get("after"):
        figs += f'<figure><figcaption>Actual</figcaption><a class="lb" href="{e(h["after"])}" title="{e(h["id"])} · actual"><img src="{e(h["after"])}" loading="lazy" alt="Actual"></a></figure>'
    return f'<div class="ba">{figs}</div>' if figs else ""


def deltas(h):
    d = h.get("delta") or {}
    parts = [f"{k} {v:+d} px" for k, v in (("X", d.get("dx")), ("Y", d.get("dy")), ("width", d.get("dw")), ("height", d.get("dh"))) if v]
    s = h.get("style")
    if s:
        sw = lambda c: f'<i class="sw" style="background:{e(c)}"></i>' if str(c).startswith("#") else ""
        return f'<div class="delta"><span>{sw(s["from"])}{e(s["from"])} → {sw(s["to"])}{e(s["to"])}</span></div>'
    return f'<div class="delta">{"".join(f"<span>{e(x)}</span>" for x in parts)}</div>' if parts else ""


def build_html(data, analysis, hist_html=""):
    adjustments = analysis.get("findings") or {}
    findings = []
    for h in data.get("findings") or []:
        h = dict(h)
        a = adjustments.get(h["id"]) or {}
        if a.get("severity") in SEV:
            h["severity"] = a["severity"]
        h["_note"] = a.get("note")
        h["_intentional"] = bool(a.get("intentional"))
        findings.append(h)
    real = [h for h in findings if not h["_intentional"]]
    intentional = [h for h in findings if h["_intentional"]]
    screens = data.get("screens") or []
    r = data.get("summary") or {}
    mode = data.get("mode")
    body = []

    if mode == "reference":
        ok = [p for p in screens if not p.get("error")]
        body.append(banner(f"Reference created: {len(ok)} screen(s). The next run compares against these screenshots.", "ok"))
        body.append('<div style="margin-top:20px">' + kpi_tiles([
            ("Pages", r.get("pages", 0), "", "in the reference", "screen"),
            ("Screens", len(ok), "ok", f'{len(data.get("config", {}).get("resolutions") or [])} resolution(s)', "image"),
            ("With errors", r.get("errors", 0), "bad" if r.get("errors") else "ok", "could not be captured", "bad"),
            ("Browser", data.get("browser"), "", data.get("tool", "")[:40], "code"),
        ]) + "</div>")
        gallery = "".join(f'<figure>{thumbnail(p["reference"], p["id"])}<figcaption>{e(short(p))} · {e(p["resolution"])}</figcaption></figure>'
                          for p in ok)
        body.append(section("Reference screenshots", f'<div class="gallery">{gallery}</div>', "what will be compared in the next runs"))
    else:
        high = [h for h in real if h["severity"] in ("Critical", "High")]
        with_ch = r.get("with_changes", 0)
        if not real:
            tone, text = "ok", ("Everything matches the reference" if not intentional else "Only intentional changes: they can be accepted as the new reference")
        elif high:
            tone, text = "bad", f"{len(high)} visible high-severity change(s) in {with_ch} screen(s)"
        else:
            tone, text = "warn", f"Minor changes in {r.get('minor_changes', 0) + with_ch} screen(s)"
        body.append(banner(analysis.get("verdict") or text, analysis.get("verdict_tone") or tone))
        comp = r.get("compared", 0)
        without = r.get("no_changes", 0)
        body.append('<div style="margin-top:20px">' + kpi_tiles([
            ("Screens compared", comp, "", f'{r.get("pages", 0)} page(s) × {len(data.get("config", {}).get("resolutions") or [])} resolution(s)', "screen"),
            ("No changes", without, "ok" if without == comp else "", f"{round(without / comp * 100) if comp else 0} % of the screens", "ok", {"pct": without / comp * 100 if comp else 0}),
            ("With changes", with_ch + r.get("minor_changes", 0), "bad" if with_ch else ("warn" if r.get("minor_changes") else "ok"),
             f'{with_ch} important · {r.get("minor_changes", 0)} minor', "warn"),
            ("Shifted elements", r.get("shifted_elements", 0) + r.get("shifted_blocks", 0),
             "bad" if r.get("shifted_elements") else ("warn" if r.get("shifted_blocks") else "ok"),
             f'{r.get("shifted_blocks", 0)} shifted block(s)', "move"),
            ("Missing", r.get("missing", 0), "bad" if r.get("missing") else "ok", "they were there and no longer appear", "bad"),
            ("New", r.get("new_elements", 0), "warn" if r.get("new_elements") else "ok", "they were not in the reference", "search"),
            ("Largest difference", f'{r.get("pct_max", 0)} %', "bad" if r.get("pct_max", 0) > 5 else ("warn" if r.get("pct_max", 0) > 0.5 else "ok"),
             "of the pixels of a screen", "image"),
            ("Intentional", len(intentional), "" if not intentional else "blk", "expected changes (not defects)", "ok"),
        ]) + "</div>")
        if analysis.get("summary"):
            body.append(section("Executive summary", f'<div class="cardbody"><p class="lead">{e(analysis["summary"])}</p></div>'))

        compared = [p for p in screens if p.get("pct") is not None]
        if compared:
            col = lambda p: CRITICAL if p.get("state") == "With changes" else WARNING if p.get("state") == "Minor changes" else OK
            body.append(section("Difference per screen", column_chart([(f'{short(p)} {p["resolution"]}', p["pct"], col(p)) for p in compared],
                                                                      fmt=lambda v: f"{v:g} %"),
                                "percentage of pixels different from the reference"))
        if real:
            count_t = Counter(h["type"] for h in real)
            count_s = Counter(h["severity"] for h in real)
            segs = [(count_s[s], LEVEL_COLOR.get(s, NEUTRAL), s) for s in SEV if count_s[s]]
            main_seg = max(segs, key=lambda s: s[0])
            body.append(two_col(
                section("Findings by type", bar_chart([(t, count_t[t], COLOR_TYPE[t]) for t in TYPES if count_t[t]], label_width=150)),
                section("Findings by severity", donut_panel(segs, round(main_seg[0] / len(real) * 100), main_seg[2].lower()))))

        # Page × resolution matrix
        resol = data.get("config", {}).get("resolutions") or sorted({p["resolution"] for p in screens})
        urls = list(dict.fromkeys(p["url"] for p in screens))
        by = {(p["url"], p["resolution"]): p for p in screens}
        rows = []
        for u in urls:
            row = [f'<span class="mono" style="color:var(--ink)">{e(short({"url": u}))}</span>']
            for res in resol:
                p = by.get((u, res))
                if not p:
                    row.append('<span class="muted">—</span>')
                    continue
                st = "Error" if p.get("error") else p.get("state")
                pct = f'<span class="pct">{p["pct"]} %</span>' if p.get("pct") is not None else ""
                img = thumbnail(p.get("diff") or p.get("actual"), f'{p["id"]} · differences', "s") if (p.get("diff") or p.get("actual")) else ""
                row.append(f'<div class="cell"><a href="#{e(p["id"])}" style="text-decoration:none">{status_pill(st)}</a>{pct}{img}</div>')
            rows.append(row)
        body.append(section("Screens matrix", f'<div class="matrix">{table(["Page"] + list(resol), rows)}</div>',
                            "state of each page at each resolution · click the state to see the comparison"))

        # Each screen with changes: comparator, regions and findings
        blocks = []
        for p in screens:
            if p.get("pct") is None or p.get("state") == "No changes":
                continue
            hs = [h for h in findings if h["screen"] == p["id"]]
            regs = "".join(f'''<div class="reg"><figure><figcaption>Reference</figcaption><a class="lb" href="{e(x["reference"])}" title="Region {i + 1} · reference"><img src="{e(x["reference"])}" loading="lazy" alt="Reference"></a></figure>
              <figure><figcaption>Actual</figcaption><a class="lb" href="{e(x["actual"])}" title="Region {i + 1} · actual"><img src="{e(x["actual"])}" loading="lazy" alt="Actual"></a></figure>
              <figure><figcaption>Differences</figcaption><a class="lb" href="{e(x["diff"])}" title="Region {i + 1} · differences"><img src="{e(x["diff"])}" loading="lazy" alt="Differences"></a></figure></div>'''
                           for i, x in enumerate((p.get("crops") or [])[:4]))
            items = "".join(f'''<div class="finding{' intentional' if h["_intentional"] else ''}" id="{e(h["id"])}"><h3>{e(h["id"])} · {e(h["title"])} {level_badge(h["severity"])} {type_pill(h["type"])}
              {'<span class="pill">Intentional</span>' if h["_intentional"] else ''}</h3>
              <p>{e(h["detail"])}</p>{deltas(h)}{f'<div class="lbl">Analysis note</div><p>{e(h["_note"])}</p>' if h.get("_note") else ''}{before_after(h)}</div>'''
                            for h in hs)
            info = (f'{p["pct"]} % of different pixels · {len(p.get("regions") or [])} region(s) · height {p.get("height_ref")} → {p.get("height")} px'
                    + (" · design reference: pixels only" if p.get("pixels_only") else ""))
            blocks.append(f'''<details class="pag" id="{e(p["id"])}" {'open' if not blocks else ''}><summary><strong>{e(short(p))}</strong>
              <span class="muted">{e(p["resolution"])} · {e(p.get("device", ""))}</span>{status_pill(p["state"])}<span class="muted">{e(info)}</span></summary>
              {comparator(p)}{f'<div class="lbl" style="padding:6px 24px 0">Regions with the most changes</div><div class="regs">{regs}</div>' if regs else ''}
              {items}</details>''')
        if blocks:
            body.append(section("Comparison of each screen", "".join(blocks),
                                "slide to go from the reference to the actual one · View differences marks in red every pixel that changed"))

        if findings:
            rows = []
            for h in findings:
                rows.append([f'<a class="id" href="#{e(h["id"])}" style="color:var(--ink)">{e(h["id"])}</a>', level_badge(h["severity"]),
                             type_pill(h["type"]) + (' <span class="pill">Intentional</span>' if h["_intentional"] else ""),
                             f'<strong style="color:var(--ink)">{e(h["title"])}</strong><div class="muted">{e(h["detail"][:180])}</div>',
                             f'<span class="mono">{e(short(h))}</span><div class="muted">{e(h["resolution"])}</div>',
                             thumbnail(h.get("before"), f'{h["id"]} · reference', "s") if h.get("before") else '<span class="muted">—</span>',
                             thumbnail(h.get("after"), f'{h["id"]} · actual', "s") if h.get("after") else '<span class="muted">—</span>'])
            body.append(section("All findings", table(["ID", "Severity", "Type", "Finding", "Screen", "Reference", "Actual"], rows),
                                "click the ID to see the full screen"))

        errors = [p for p in screens if p.get("error")]
        new = [p for p in screens if p.get("state") == "New"]
        if errors or new:
            rows = [[e(short(p)), e(p["resolution"]), status_pill("Error" if p.get("error") else "New"),
                     e(p.get("error") or "There is no reference for this screen: accept it with --accept if it is correct.")] for p in errors + new]
            body.append(section("Screens not compared", table(["Page", "Resolution", "State", "Detail"], rows)))

    body.append(missing_info(analysis.get("missing_info")))
    if analysis.get("recommendations"):
        rows = [[f'<strong style="color:var(--ink)">{e(x.get("action"))}</strong>', e(x.get("reason")), level_badge(x.get("priority"))]
                for x in analysis["recommendations"]]
        body.append(section("Recommendations", table(["Action", "Why", "Priority"], rows)))
    if analysis.get("next_steps"):
        body.append(section("Next steps", doc_list(analysis["next_steps"])))

    cfg = data.get("config") or {}
    ref = data.get("reference") or {}
    rows = [["Reference taken", e((ref.get("date") or "")[:16].replace("T", " "))],
            ["Last update", e((ref.get("updated") or "—")[:16].replace("T", " "))],
            ["Browser", e(ref.get("browser") or data.get("browser"))],
            ["Resolutions", e(", ".join(cfg.get("resolutions") or []))],
            ["Hidden areas", e(", ".join(cfg.get("hide") or []) or "none")],
            ["Sensitivity per pixel", e(cfg.get("threshold"))],
            ["Position tolerance", f'{e(cfg.get("tolerance_px"))} px'],
            ["Difference accepted as no changes", f'{e(cfg.get("pct_max"))} %'],
            ["Accept the changes as the new reference", '<span class="mono">npm run pixel-perfect -- --accept all</span> (or the screen IDs separated by commas)']]
    body.append(section("Reference and configuration", table(["Item", "Value"], rows),
                        "the reference is the version accepted as correct; it is kept between runs"))

    if hist_html:
        body.append(hist_html)
    meta_html = meta([("Story", data.get("story")), ("Site", data.get("host")),
                      ("Date", (data.get("date") or "")[:16].replace("T", " ")), ("Browser", data.get("browser")),
                      ("Duration", f'{data.get("duration_s", 0)} s')])
    title = "Visual reference" if mode == "reference" else "Visual regression"
    return page(title, "Pixel perfect", meta_html, CSS_EXTRA + CSS_PP + "".join(body) + JS_PP)


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="HTML visual regression report from pixel-perfect.json")
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
    hist_html = _history.section("pixel-perfect", Path(a.data_json).resolve().parent, data)
    with open(a.output, "w", encoding="utf-8") as f:
        f.write(build_html(data, analysis, hist_html=hist_html))
    print(f"OK: {a.output}")


if __name__ == "__main__":
    main()
