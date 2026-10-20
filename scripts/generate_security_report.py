#!/usr/bin/env python3
"""
Generates the web security HTML report (dashboard, dark mode) from the OWASP ZAP result
(zap.json, traditional JSON format) and, optionally, from the agent's analysis.

Usage:
    python scripts/generate_security_report.py <zap.json> <output.html>
           [--url URL] [--story US-001] [--analysis analysis.json]

The FINDINGS come from zap.json (they are not written by hand). The analysis (optional) provides:
{
  "verdict": "Medium risk: fix before release",   // conclusion
  "verdict_tone": "warn",                          // optional: ok | warn | bad
  "summary": "Executive summary...",
  "false_positives": [{"pluginid": "10021", "reason": "The header is added by the production proxy"}],
  "notes": {"10038": "Affects every page: it is solved in the server configuration"},
  "missing_info": [{"id": "MI-01", "what_is_missing": "...", "question": "..."}],   // "description" works as an alias of what_is_missing
  "recommendations": [{"action": "...", "reason": "...", "priority": "High"}],
  "next_steps": ["..."]
}

ZAP risk: High | Medium | Low | Informational. The evidence is shown with long strings masked
(possible tokens or keys). The HTML is self-contained (no internet).
"""
import argparse
import datetime
import html as htmllib
import json
import re
import sys

from _report_styles import (missing_info, e, page, meta, section, kpi_tiles, banner, doc_list, table, bar_chart, level_badge,
                              CRITICAL, SERIOUS, WARNING, NEUTRAL)

RISKS = [(3, "High", CRITICAL), (2, "Medium", SERIOUS), (1, "Low", WARNING), (0, "Informational", NEUTRAL)]
RISK_NAME = {c: n for c, n, _ in RISKS}
COLOR_RISK = {c: col for c, _, col in RISKS}
CONFIDENCE = {"0": "False positive", "1": "Low", "2": "Medium", "3": "High", "4": "Confirmed"}

CSS_EXTRA = """
<style>
.finding{padding:20px 24px;border-top:1px solid var(--border-soft)}
.finding:first-child{border-top:0}
.finding h3{font-size:16px;color:var(--ink);margin-bottom:6px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.finding .lbl{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:600;margin:12px 0 4px}
.finding p{color:var(--body)}
.finding code,.mono{font-family:var(--mono);font-size:12.5px}
.finding ul{margin-left:18px;color:var(--body)}
.finding li{word-break:break-all}
.ev{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:8px 10px;white-space:pre-wrap;word-break:break-all;color:var(--body)}
.fp{opacity:.6}
</style>
"""


def mask(t):
    """ZAP evidence may carry an exposed token or key: of each secret-looking string (16 or more
    token characters, with letters and digits) only the first 4 are shown."""
    def cover(m):
        s = m.group(0)
        return s[:4] + "…" if re.search(r"\d", s) and re.search(r"[A-Za-z]", s) else s
    return re.sub(r"[A-Za-z0-9_\-+/=.]{16,}", cover, t or "")


def text(html_zap):
    """ZAP sends the description, solution and references with <p> and line breaks: they become plain text."""
    t = re.sub(r"</p>\s*<p>|<br\s*/?>", "\n", html_zap or "")
    t = re.sub(r"<[^>]+>", "", t)
    return htmllib.unescape(t).strip()


def paragraphs(html_zap):
    return "".join(f"<p>{e(p)}</p>" for p in text(html_zap).split("\n") if p.strip())


def risk_badge(code):
    name = RISK_NAME.get(code, "—")
    sev = {"High": "Critical", "Medium": "High", "Low": "Medium", "Informational": "Low"}.get(name)
    return level_badge(sev).replace(f">{sev}<", f">{name}<") if sev else name


def load_alerts(zap):
    alerts = []
    for site in zap.get("site") or []:
        for a in site.get("alerts") or []:
            a = dict(a)
            a["_site"] = site.get("@name", "")
            a["_risk"] = int(a.get("riskcode", 0) or 0)
            alerts.append(a)
    return sorted(alerts, key=lambda a: (-a["_risk"], -int(a.get("count", 0) or 0)))


def tone(verdict, alerts):
    if verdict:
        low = verdict.lower()
        if "high" in low or "critical" in low or "not fit" in low or "no-go" in low:
            return "bad"
        if "medium" in low or "observ" in low or "fix" in low:
            return "warn"
        return "ok"
    if any(a["_risk"] == 3 for a in alerts):
        return "bad"
    return "warn" if any(a["_risk"] == 2 for a in alerts) else "ok"


def build_html(zap, analysis, url, story, mode="passive"):
    active = str(mode).lower() == "active"
    alerts = load_alerts(zap)
    false_pos = {str(f.get("pluginid")): f.get("reason", "") for f in analysis.get("false_positives") or []}
    notes = {str(k): v for k, v in (analysis.get("notes") or {}).items()}
    valid = [a for a in alerts if str(a.get("pluginid")) not in false_pos]

    body = []
    verdict = analysis.get("verdict")
    if not verdict:
        high = sum(1 for a in valid if a["_risk"] == 3)
        medium = sum(1 for a in valid if a["_risk"] == 2)
        verdict = (f"{high} high-risk finding(s)" if high else f"{medium} medium-risk finding(s)" if medium
                   else f"No high- or medium-risk findings in the {'active' if active else 'passive'} scan")
    body.append(banner(verdict, analysis.get("verdict_tone") or tone(analysis.get("verdict"), valid)))

    count = {c: sum(1 for a in valid if a["_risk"] == c) for c, _, _ in RISKS}
    kpis = kpi_tiles([
        ("High risk", count[3], "bad" if count[3] else "ok"),
        ("Medium risk", count[2], "warn" if count[2] else "ok"),
        ("Low risk", count[1], ""),
        ("Informational", count[0], "blk"),
    ])
    body.append(f'<div style="margin-top:20px">{kpis}</div>')

    method = (f'''
      <p><strong style="color:var(--ink)">Active scan</strong> with OWASP ZAP (full scan) on an authorized URL: besides crawling the site,
      attack payloads (injection, XSS, etc.) were sent and the responses were analyzed. It is intrusive and may have created or modified data
      in the test environment. It does not cover business logic or role-based access control beyond what ZAP tests.</p>'''
              if active else '''
      <p><strong style="color:var(--ink)">Passive scan</strong> with OWASP ZAP (baseline): the site was crawled with the spider and the responses
      were analyzed without sending attacks or modifying data. It detects configurations and exposures visible from the client
      (security headers, cookies, exposed information, mixed content…); it <strong style="color:var(--ink)">does not replace</strong>
      an authorized active scan or a penetration test.</p>''')
    body.append(section("Scope and method", f'''<div class="cardbody">{method}
      <p>Site: <span class="mono">{e(url or ", ".join(sorted({a["_site"] for a in alerts})) or "—")}</span> ·
      ZAP version: {e(zap.get("@version", "—"))} · Generated by ZAP: {e(zap.get("@generated", "—"))}</p></div>'''))

    if analysis.get("summary"):
        body.append(section("Executive summary", f'<div class="cardbody"><p class="lead">{e(analysis["summary"])}</p></div>'))

    body.append(section("Findings by risk", bar_chart([(n, count[c], col) for c, n, col in RISKS])))

    if valid:
        rows = [[f'<a href="#a{e(a.get("pluginid"))}" style="color:var(--ink)">{e(a.get("name") or a.get("alert"))}</a>',
                 risk_badge(a["_risk"]), e(CONFIDENCE.get(str(a.get("confidence")), "—")),
                 e(a.get("count") or len(a.get("instances") or [])), e(f'CWE-{a["cweid"]}' if a.get("cweid") not in (None, "", "-1", "0") else "—")]
                for a in valid]
        body.append(section("Findings summary", table(["Finding", "Risk", "Confidence", "Instances", "CWE"], rows)))

        detail = []
        for a in valid:
            inst = a.get("instances") or []
            urls = "".join(f'<li><span class="mono">{e(i.get("method", ""))} {e(i.get("uri", ""))}</span>'
                           + (f' · parameter <code>{e(i["param"])}</code>' if i.get("param") else "") + "</li>" for i in inst[:5])
            more = f'<li class="muted">… and {len(inst) - 5} more</li>' if len(inst) > 5 else ""
            evid = next((i.get("evidence") for i in inst if i.get("evidence")), "")
            refs = [r for r in text(a.get("reference")).split("\n") if r.strip()][:4]
            cwe = f'CWE-{a["cweid"]}' if a.get("cweid") not in (None, "", "-1", "0") else ""
            detail.append(f'''<div class="finding" id="a{e(a.get("pluginid"))}">
              <h3>{e(a.get("name") or a.get("alert"))} {risk_badge(a["_risk"])}
                <span class="muted" style="font-size:12px;font-weight:400">Confidence {e(CONFIDENCE.get(str(a.get("confidence")), "—"))}{" · " + e(cwe) if cwe else ""} · rule {e(a.get("pluginid"))}</span></h3>
              <div class="lbl">What it is</div>{paragraphs(a.get("desc"))}
              {f'<div class="lbl">Analysis</div><p>{e(notes[str(a.get("pluginid"))])}</p>' if str(a.get("pluginid")) in notes else ""}
              <div class="lbl">Where ({len(inst)})</div><ul>{urls}{more}</ul>
              {f'<div class="lbl">Evidence</div><div class="ev">{e(mask(evid)[:400])}</div>' if evid else ""}
              <div class="lbl">How to fix it</div>{paragraphs(a.get("solution"))}
              {"<div class='lbl'>References</div><ul>" + "".join(f"<li>{e(r)}</li>" for r in refs) + "</ul>" if refs else ""}
            </div>''')
        body.append(section("Detail of each finding", "".join(detail)))

    if false_pos:
        rows = [[e(next((a.get("name") for a in alerts if str(a.get("pluginid")) == pid), pid)), e(reason)] for pid, reason in false_pos.items()]
        body.append(section("Discarded as false positives", table(["Finding", "Reason"], rows)))

    body.append(missing_info(analysis.get("missing_info")))
    if analysis.get("recommendations"):
        rows = [[f'<strong style="color:var(--ink)">{e(r.get("action"))}</strong>', e(r.get("reason")), level_badge(r.get("priority"))]
                for r in analysis["recommendations"]]
        body.append(section("Recommendations", table(["Action", "Why", "Priority"], rows)))
    if analysis.get("next_steps"):
        body.append(section("Next steps", doc_list(analysis["next_steps"])))

    meta_html = meta([("Story", story), ("Date", datetime.date.today().isoformat()),
                      ("Tool", "OWASP ZAP · active full scan" if active else "OWASP ZAP · passive baseline")])
    return page("Web security report", "Security report", meta_html, CSS_EXTRA + "".join(body))


def main():
    ap = argparse.ArgumentParser(description="Security HTML report from zap.json")
    ap.add_argument("zap_json")
    ap.add_argument("output")
    ap.add_argument("--url")
    ap.add_argument("--story")
    ap.add_argument("--analysis", help="JSON with verdict, summary, false positives, notes and recommendations")
    ap.add_argument("--mode", choices=["passive", "active"], default="passive", help="type of scan that generated the zap.json")
    a = ap.parse_args()
    if not a.output.lower().endswith(".html"):
        sys.exit("The output must end in .html")
    with open(a.zap_json, encoding="utf-8") as f:
        zap = json.load(f)
    analysis = {}
    if a.analysis:
        with open(a.analysis, encoding="utf-8") as f:
            analysis = json.load(f)
    with open(a.output, "w", encoding="utf-8") as f:
        f.write(build_html(zap, analysis, a.url, a.story, a.mode))
    print(f"OK: {a.output}")


if __name__ == "__main__":
    main()
