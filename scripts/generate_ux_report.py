#!/usr/bin/env python3
"""
Generates the usability evaluation HTML report (dashboard, dark mode) from ux.json
(npm run ux) and, optionally, from the analysis of the ux-evaluator agent.

Usage:
    python scripts/generate_ux_report.py <ux.json> <output.html> [--analysis analysis.json]

What it shows: verdict, indicators (heuristic score, findings, severity, pages), the score of each
of the 10 Nielsen heuristics, the findings grouped by heuristic with the crop of the element and
where they appear (the automatic ones and the ones from the agent's manual review), the 404 error page, the
pages on desktop and mobile, recommendations and the evolution of the runs.

The analysis (optional) provides:
{
  "verdict": "...", "verdict_tone": "warn", "summary": "...",
  "findings": {"U-03": {"severity": "High", "note": "..."}},
  "discarded": [{"id": "U-07", "reason": "..."}],
  "manual_findings": [{"heuristic": "H1", "severity": "High", "title": "After paying there is no confirmation",
                       "detail": "...", "fix": "...", "flow": "Checkout", "url": "https://...",
                       "screenshot": "screenshots/manual-1.png"}],
  "missing_info": [{"id": "MI-01", "what_is_missing": "...", "question": "..."}],   // "description" works as an alias of what_is_missing
  "recommendations": [{"action": "...", "reason": "...", "priority": "High"}],
  "next_steps": ["..."]
}
"""
import argparse
import json
import sys
from pathlib import Path

import _history
from _report_styles import (missing_info, warn_analysis, e, page, meta, section, kpi_tiles, banner, doc_list, table, bar_chart, two_col, gauge,
                              level_badge, _pill, thumbnail, CRITICAL, WARNING, NEUTRAL, OK, SERIES)
from generate_exploratory_report import CSS_EXTRA

SEV = ["Critical", "High", "Medium", "Low"]
WEIGHT = {"Critical": 40, "High": 25, "Medium": 10, "Low": 4}

CSS_UX = """
<style>
.heur{border-top:1px solid var(--border-soft);padding:16px 24px}
.heur:first-child{border-top:0}
.heur h3{font-size:15px;color:var(--ink);display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
.heur h3 .cod{font-family:var(--mono);font-size:12px;padding:3px 8px;border-radius:7px;background:var(--tile);border:1px solid var(--border)}
.item{display:grid;grid-template-columns:minmax(0,1fr) 170px;gap:14px;padding:10px 0;border-top:1px dashed var(--border-soft)}
.item:first-of-type{border-top:0}
.item p{margin:2px 0;color:var(--body);font-size:13px}
.manual{display:inline-block;font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px;background:rgba(144,133,233,.15);color:#C9C2FF;margin-left:6px}
.sidebyside{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;padding:16px 24px}
.sidebyside figure{margin:0;background:var(--bg);border:1px solid var(--border);border-radius:12px;overflow:hidden}
.sidebyside .thumb{display:grid;width:100%;height:240px;border:0;border-radius:0;border-bottom:1px solid var(--border)}
.sidebyside figcaption{padding:8px 12px;font-size:12.5px;color:var(--body)}
.discarded{opacity:.55}
@media (max-width:720px){.item{grid-template-columns:1fr}}
</style>
"""


def short(u):
    r = (u or "").split("://", 1)[-1].split("/", 1)
    return ("/" + r[1]) if len(r) > 1 and r[1] else "/"


def build_html(data, analysis, hist_html=""):
    heur = data.get("heuristics") or {}
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
    for i, m in enumerate(analysis.get("manual_findings") or [], 1):
        findings.append({"id": f"M-{i:02d}", "heuristic": m.get("heuristic", "H1"), "severity": m.get("severity", "Medium"), "title": m.get("title", ""),
                         "detail": m.get("detail", ""), "fix": m.get("fix"), "manual": True, "flow": m.get("flow"), "where": [{"screenshot": m.get("screenshot"), "url": m.get("url")}]})
    alive = [h for h in findings if not h.get("_disc")]
    # Score per heuristic (with the manual ones included)
    scores = {k: max(0, 100 - sum(WEIGHT.get(h["severity"], 4) for h in alive if h["heuristic"] == k)) for k in heur}
    total = round(sum(scores.values()) / len(scores)) if scores else 0
    r = data.get("summary") or {}
    serious = [h for h in alive if h["severity"] in ("Critical", "High")]
    tone = "bad" if serious else ("warn" if alive else "ok")
    text = f"Heuristic score {total}/100 · {len(alive)} usability problem(s), {len(serious)} important" if alive else "No usability problems detected"
    body = [banner(analysis.get("verdict") or text, analysis.get("verdict_tone") or tone)]
    body.append('<div style="margin-top:20px">' + kpi_tiles([
        ("Heuristic score", f"{total}/100", "ok" if total >= 85 else "warn" if total >= 65 else "bad", "average of the 10 Nielsen heuristics", "target", {"pct": total}),
        ("Findings", len(alive), "bad" if serious else ("warn" if alive else "ok"), f'{sum(1 for h in alive if h.get("manual"))} from the manual review', "search"),
        ("High or critical", len(serious), "bad" if serious else "ok", "they block or confuse the person", "bad"),
        ("Pages", r.get("pages", 0), "", f'at {", ".join(data.get("resolutions") or [])}', "screen"),
    ]) + "</div>")
    if analysis.get("summary"):
        body.append(section("Executive summary", f'<div class="cardbody"><p class="lead">{e(analysis["summary"])}</p></div>'))
    rows = [(f'{k} · {heur[k][:52]}', scores[k], OK if scores[k] >= 85 else WARNING if scores[k] >= 60 else CRITICAL) for k in heur]
    body.append(two_col(section("Score per heuristic", bar_chart(rows, label_width=380), "100 = no problems in that heuristic"),
                        section("Overall score", f'<div class="cardbody" style="display:grid;place-items:center">{gauge(total, "out of 100")}</div>')))

    blocks = []
    for k, name in heur.items():
        hs = [h for h in findings if h["heuristic"] == k]
        if not hs:
            continue
        items = ""
        for h in hs:
            d = (h.get("where") or [{}])[0]
            ev = d.get("crop") or d.get("screenshot")
            more = f' · and {len(h["where"]) - 1} more' if len(h.get("where") or []) > 1 else ""
            where = f'<p class="muted mono">{e(short(d.get("url")))} · {e(d.get("resolution") or "")}{e(more)}</p>' if d.get("url") else ""
            note = f'<p><i>{e(h["_note"])}</i></p>' if h.get("_note") else ""
            note += f'<p><b>How to fix it:</b> {e(h["fix"])}</p>' if h.get("fix") else ""
            discarded = f'<p class="muted">Discarded: {e(h["_disc"])}</p>' if h.get("_disc") else ""
            manual = '<span class="manual">manual review</span>' if h.get("manual") else ""
            cls = "item discarded" if h.get("_disc") else "item"
            evid = thumbnail(ev, h["title"], "s") if ev else ""
            items += (f'<div class="{cls}"><div><p>{level_badge(h["severity"])} <strong style="color:var(--ink)">{e(h["id"])} · {e(h["title"])}</strong>'
                      f'{manual}</p><p>{e(h.get("detail"))}</p>{where}{note}{discarded}</div><div>{evid}</div></div>')
        blocks.append(f'<div class="heur"><h3><span class="cod">{e(k)}</span>{e(name)} {_pill(f"{scores[k]}/100", OK if scores[k] >= 85 else WARNING if scores[k] >= 60 else CRITICAL, "●")}</h3>{items}</div>')
    if blocks:
        body.append(section("Findings by heuristic", "".join(blocks), "automatic and from the agent's manual review"))

    p404 = data.get("page_404") or {}
    if p404:
        rows = [["Address tested", f'<span class="mono">{e(p404.get("url"))}</span>'], ["Response", e(p404.get("status") or p404.get("error") or "—")],
                ["Has links to go back", "Yes" if p404.get("links") else "No"], ["Technical message", "Yes" if p404.get("technical") else "No"],
                ["What it shows", e((p404.get("text") or "")[:240])]]
        body.append(section("404 error page", table(["Item", "Value"], rows), "what someone who follows a broken link sees"))
    figs = "".join(f'<figure>{thumbnail(p.get("screenshot"), short(p["url"]) + " · " + p["resolution"])}<figcaption>{e(short(p["url"]))} · {e(p["resolution"])} · '
                   f'{e(p.get("findings", 0))} finding(s)</figcaption></figure>' for p in data.get("screens") or [] if p.get("screenshot"))
    if figs:
        body.append(section("Pages reviewed", f'<div class="sidebyside">{figs}</div>'))
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
              ("Duration", f'{data.get("duration_s", 0)} s')])
    return page("Usability", "Heuristic evaluation (Nielsen)", m, CSS_EXTRA + CSS_UX + "".join(body))


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Usability HTML report from ux.json")
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
    hist_html = _history.section("ux", Path(a.data_json).resolve().parent, data)
    with open(a.output, "w", encoding="utf-8") as f:
        f.write(build_html(data, analysis, hist_html=hist_html))
    print(f"OK: {a.output}")


if __name__ == "__main__":
    main()
