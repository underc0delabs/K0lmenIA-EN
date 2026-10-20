#!/usr/bin/env python3
"""
Generates the translations HTML report (dashboard, dark mode) from translator.json
(npm run translator) and, optionally, from the analysis of the translation-analyst agent.

Usage:
    python scripts/generate_translation_report.py <translator.json> <output.html> [--analysis analysis.json]

What it shows: verdict, indicators (languages, pages, translated percentage, untranslated texts,
visible keys, encoding, truncated and formats), translated percentage and findings per language,
findings by type, the page × language matrix, each page in every language side by side, the
findings with the crop of the marked text and where it appears, and the evolution of the runs.

The analysis (optional) provides:
{
  "verdict": "The English version has Spanish texts in the checkout", "verdict_tone": "bad",
  "summary": "Summary for a non-technical person...",
  "findings": {"T-01": {"severity": "High", "note": "...", "suggestion": "Add to cart"}},
  "discarded": [{"id": "T-09", "reason": "It is the brand name"}],
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
from _report_styles import (missing_info, warn_analysis, e, page, meta, section, kpi_tiles, banner, doc_list, table, bar_chart, column_chart, two_col,
                              level_badge, _pill, thumbnail, CRITICAL, WARNING, NEUTRAL, OK, SERIES)
from generate_exploratory_report import CSS_EXTRA

SEV = ["Critical", "High", "Medium", "Low"]
TYPES = ["Untranslated", "Same as reference", "Translation key", "Encoding", "Truncated text", "Overflowing text", "Overflow",
         "Number format", "Date in another language", "Lang attribute"]
COLOR_TYPE = {t: SERIES[i % len(SERIES)] for i, t in enumerate(TYPES)}

CSS_TR = """
<style>
.sidebyside{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;padding:16px 24px}
.sidebyside figure{margin:0;background:var(--bg);border:1px solid var(--border);border-radius:12px;overflow:hidden}
.sidebyside .thumb{display:grid;width:100%;height:280px;border:0;border-radius:0;border-bottom:1px solid var(--border)}
.sidebyside figcaption{padding:9px 12px;font-size:12.5px;color:var(--body);display:flex;justify-content:space-between;gap:8px;align-items:center}
.language{display:inline-flex;align-items:center;gap:6px;font-family:var(--mono);font-size:12px;font-weight:600;padding:3px 9px;
  border-radius:999px;background:var(--tile);border:1px solid var(--border);color:var(--ink)}
.cat{display:inline-flex;align-items:center;gap:7px;font-size:12px;font-weight:650;padding:4px 11px;border-radius:999px;
  background:var(--tile);border:1px solid var(--border);color:var(--ink);white-space:nowrap}
.cat i{width:9px;height:9px;border-radius:3px}
.cell{display:flex;flex-direction:column;align-items:center;gap:6px}
.discarded{opacity:.55}
.sug{color:#C6EDB9}
</style>
"""


def language(x, ref=None):
    star = " ★" if ref and x == ref else ""
    return f'<span class="language">{e(x)}{star}</span>'


def short_url(u):
    r = (u or "").split("://", 1)[-1].split("/", 1)
    return ("/" + r[1]) if len(r) > 1 and r[1] else "/"


def build_html(data, analysis, hist_html=""):
    adjustments = analysis.get("findings") or {}
    discarded = {str(d.get("id")): d.get("reason", "") for d in analysis.get("discarded") or []}
    findings = []
    for h in data.get("findings") or []:
        h = dict(h)
        a = adjustments.get(h["id"]) or {}
        if a.get("severity") in SEV:
            h["severity"] = a["severity"]
        h["_a"] = a
        h["_discarded"] = discarded.get(h["id"])
        findings.append(h)
    alive = [h for h in findings if not h["_discarded"]]
    r = data.get("summary") or {}
    ref = data.get("reference")
    languages = data.get("languages") or []
    by_language = r.get("by_language") or {}
    others = [i for i in languages if i != ref]
    avg = [by_language[i]["translated_pct"] for i in others if by_language.get(i, {}).get("translated_pct") is not None]
    avg = round(sum(avg) / len(avg), 1) if avg else None
    body = []
    serious = [h for h in alive if h["severity"] in ("Critical", "High")]
    if serious:
        tone, text = "bad", f"{len(serious)} important problem(s): untranslated texts, visible keys or broken characters"
    elif alive:
        tone, text = "warn", "The translations are there; format and space details remain"
    else:
        tone, text = "ok", f"The site is complete in {', '.join(languages)}"
    body.append(banner(analysis.get("verdict") or text, analysis.get("verdict_tone") or tone))
    body.append('<div style="margin-top:20px">' + kpi_tiles([
        ("Languages", len(languages), "", f"reference: {ref}", "person"),
        ("Pages", r.get("pages", 0), "", f'{r.get("screens", 0)} screens (page × language × resolution)', "screen"),
        ("Translated", f"{avg} %" if avg is not None else "—", "" if avg is None else ("ok" if avg >= 98 else "warn" if avg >= 90 else "bad"),
         "of the texts, average across languages", "ok", {"pct": avg} if avg is not None else None),
        ("Untranslated", r.get("untranslated", 0), "bad" if r.get("untranslated") else "ok", "in another language or equal to the reference", "warn"),
        ("Visible keys", r.get("keys", 0), "bad" if r.get("keys") else "ok", "internal names instead of the text", "code"),
        ("Encoding", r.get("encoding", 0), "bad" if r.get("encoding") else "ok", "broken characters (Ã©, â€™)", "bad"),
        ("Truncated", r.get("truncated", 0), "warn" if r.get("truncated") else "ok", "texts that do not fit or overflow", "move"),
        ("Formats", r.get("formats", 0), "warn" if r.get("formats") else "ok", "numbers or dates from another region", "clock"),
    ]) + "</div>")
    if analysis.get("summary"):
        body.append(section("Executive summary", f'<div class="cardbody"><p class="lead">{e(analysis["summary"])}</p></div>'))

    pct_rows = [(i, by_language[i]["translated_pct"], OK if by_language[i]["translated_pct"] >= 98 else WARNING if by_language[i]["translated_pct"] >= 90 else CRITICAL)
                for i in others if by_language.get(i, {}).get("translated_pct") is not None]
    kinds = Counter(h["type"] for h in alive)
    body.append(two_col(
        section("Translated by language", column_chart(pct_rows, fmt=lambda v: f"{v:g} %", width=660) if pct_rows else '<p class="muted" style="padding:16px 24px">—</p>',
                "percentage of the texts of each language that are translated"),
        section("Findings by type", bar_chart([(t, kinds[t], COLOR_TYPE.get(t, NEUTRAL)) for t in TYPES if kinds[t]], label_width=170) if kinds
                else '<p class="muted" style="padding:16px 24px">No findings.</p>')))

    rows = [[language(i, ref), e(by_language.get(i, {}).get("method") or "—"),
             e(f'{by_language[i]["translated_pct"]} %' if by_language.get(i, {}).get("translated_pct") is not None else "—"),
             e(by_language.get(i, {}).get("findings", 0))] for i in languages]
    body.append(section("Languages", table(["Language", "How it was switched", "Translated", "Findings"], rows),
                        "★ reference · hreflang: links on the site · template: URL built · browser: the site chooses by the browser language"))

    screens = data.get("screens") or []
    keys = list(dict.fromkeys((p["page"], p["url"], p["resolution"]) for p in screens))
    rows = []
    for pag, url, res in keys:
        row = [f'<span class="mono" style="color:var(--ink)">{e(short_url(url))}</span><div class="muted">{e(res)}</div>']
        for i in languages:
            p = next((x for x in screens if x["page"] == pag and x["resolution"] == res and x["language"] == i), None)
            if not p:
                row.append('<span class="muted">—</span>')
                continue
            n = p.get("findings", 0)
            st = _pill("Error", NEUTRAL, "⊘") if p.get("error") else _pill(f"{n} finding(s)" if n else "OK", WARNING if n else OK, "!" if n else "✓")
            row.append(f'<div class="cell"><a href="#p-{e(pag)}-{e(res)}" style="text-decoration:none">{st}</a>'
                       f'{thumbnail(p.get("screenshot"), f"{short_url(url)} · {i} · {res}", "s") if p.get("screenshot") else ""}</div>')
        rows.append(row)
    if rows:
        body.append(section("Pages and languages matrix", f'<div class="matrix">{table(["Page"] + languages, rows)}</div>',
                            "click the status to see the page in every language"))
    blocks = []
    for pag, url, res in keys:
        figs = ""
        for i in languages:
            p = next((x for x in screens if x["page"] == pag and x["resolution"] == res and x["language"] == i), None)
            if p and p.get("screenshot"):
                title = f"{short_url(url)} · {i} · {res}"
                figs += (f'<figure>{thumbnail(p["screenshot"], title)}<figcaption>{language(i, ref)}'
                         f'<span class="muted">{e(p.get("lang") or "no lang")} · {e(p.get("findings", 0))} finding(s)</span></figcaption></figure>')
        blocks.append(f'<details class="pag" id="p-{e(pag)}-{e(res)}"><summary><strong>{e(short_url(url))}</strong><span class="muted">{e(res)}</span></summary>'
                      f'<div class="sidebyside">{figs}</div></details>')
    if blocks:
        body.append(section("Each page in every language", "".join(blocks), "side by side, to compare text length and layout"))

    if findings:
        rows = []
        for h in findings:
            where = h.get("where") or []
            more = f" and {len(where) - 1} more" if len(where) > 1 else ""
            sug = f'<div class="sug">Suggestion: {e(h["_a"]["suggestion"])}</div>' if h["_a"].get("suggestion") else ""
            note = f'<div class="muted">{e(h["_a"]["note"])}</div>' if h["_a"].get("note") else ""
            disc = f'<div class="muted">Discarded: {e(h["_discarded"])}</div>' if h["_discarded"] else ""
            first = where[0] if where else {}
            rows.append([f'<span style="white-space:nowrap">{e(h["id"])}</span>', level_badge(h["severity"]), f'<span class="cat"><i style="background:{COLOR_TYPE.get(h["type"], NEUTRAL)}"></i>{e(h["type"])}</span>',
                         language(h["language"], ref), f'<strong style="color:var(--ink)">{e(h["title"])}</strong><div class="muted">{e(h.get("detail"))}</div>{sug}{note}{disc}',
                         f'<span class="mono">{e(short_url(first.get("url")))}</span><div class="muted">{e(first.get("resolution"))}{e(more)}</div>',
                         thumbnail(first.get("crop") or first.get("screenshot"), h["title"], "s") if (first.get("crop") or first.get("screenshot")) else '<span class="muted">—</span>'])
        body.append(section("Findings", table(["ID", "Severity", "Type", "Language", "Finding", "Where", "Evidence"], rows),
                            "the same text on several pages is a single finding"))
    body.append(missing_info(analysis.get("missing_info")))
    if analysis.get("recommendations"):
        rows = [[f'<strong style="color:var(--ink)">{e(x.get("action"))}</strong>', e(x.get("reason")), level_badge(x.get("priority"))]
                for x in analysis["recommendations"]]
        body.append(section("Recommendations", table(["Action", "Why", "Priority"], rows)))
    if analysis.get("next_steps"):
        body.append(section("Next steps", doc_list(analysis["next_steps"])))
    if hist_html:
        body.append(hist_html)
    meta_html = meta([("Story", data.get("story")), ("Site", data.get("host")), ("Languages", ", ".join(languages)),
                      ("Date", (data.get("date") or "")[:16].replace("T", " ")), ("Duration", f'{data.get("duration_s", 0)} s')])
    return page("Translations", "Translation and languages", meta_html, CSS_EXTRA + CSS_TR + "".join(body))


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Translations HTML report from translator.json")
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
    hist_html = _history.section("translator", Path(a.data_json).resolve().parent, data)
    with open(a.output, "w", encoding="utf-8") as f:
        f.write(build_html(data, analysis, hist_html=hist_html))
    print(f"OK: {a.output}")


if __name__ == "__main__":
    main()
