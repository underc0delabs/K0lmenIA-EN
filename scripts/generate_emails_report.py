#!/usr/bin/env python3
"""
Generates the Emails report in HTML (dashboard, dark mode) from emails.json (npm run emails)
and, optionally, from the email-verifier agent's analysis.

Usage:
    python scripts/generate_emails_report.py <emails.json> <output.html> [--analysis analysis.json]

What it shows: verdict, indicators (emails reviewed, expectations met, not received, findings,
unreplaced variables, links with problems, compatibility), the expectations of each case (what had
to arrive and what was checked), findings by type and severity, compatibility per email, each email
with its desktop and mobile view, headers, links, attachments and problems, the findings table and the
evolution of the runs.

The analysis (optional) provides:
{
  "verdict": "The order email goes out with empty variables", "verdict_tone": "bad",
  "summary": "Summary for a non-technical person...",
  "findings": {"C-02": {"severity": "Critical", "note": "Every customer who buys receives it"}},
  "discarded": [{"id": "C-11", "reason": "Outlook is not a target client"}],
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
from _report_styles import (missing_info, warn_analysis, e, page, meta, section, kpi_tiles, banner, doc_list, table, bar_chart, column_chart, donut_panel, two_col,
                            level_badge, _pill, thumbnail, LEVEL_COLOR, CRITICAL, WARNING, NEUTRAL, OK, SERIES)
from generate_exploratory_report import CSS_EXTRA

SEV = ["Critical", "High", "Medium", "Low"]
EXPECT = {"Met": (OK, "✓"), "Not met": (CRITICAL, "✕"), "Not received": (CRITICAL, "⊘")}

CSS_EML = """
<style>
.email{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,.65fr);gap:18px;padding:18px 24px;border-top:1px solid var(--border-soft)}
.email:first-child{border-top:0}
.email h3{font-size:16px;color:var(--ink);margin-bottom:8px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.hdrs{display:grid;grid-template-columns:110px 1fr;gap:4px 12px;font-size:13px;margin:8px 0 12px}
.hdrs dt{color:var(--muted)}
.hdrs dd{margin:0;color:var(--ink);word-break:break-all}
.views{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr);gap:10px}
.views figure{margin:0}
.views figcaption{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:600;margin-bottom:6px}
.views .thumb{display:grid;width:100%;height:340px}
.ctl{list-style:none;margin:6px 0 0;padding:0}
.ctl li{display:flex;gap:8px;align-items:baseline;font-size:13px;color:var(--body);margin:3px 0}
.ctl b{font-weight:700}
.ctl .yes{color:#7BD36A}.ctl .no{color:#FF7B70}
.linkst td{font-size:12.5px}
.cat{display:inline-flex;align-items:center;gap:7px;font-size:12px;font-weight:650;padding:4px 11px;border-radius:999px;
  background:var(--tile);border:1px solid var(--border);color:var(--ink);white-space:nowrap}
.cat i{width:9px;height:9px;border-radius:3px}
.discarded{opacity:.55}
@media (max-width:980px){.email{grid-template-columns:1fr}}
</style>
"""


def pill(mapping, v):
    color, ic = mapping.get(v, (NEUTRAL, "●"))
    return _pill(v or "—", color, ic)


def checks(x):
    if not x.get("checks"):
        return '<span class="muted">—</span>'
    items = []
    for c in x["checks"]:
        cls, mark = ("yes", "✓") if c["ok"] else ("no", "✕")
        detail = f' <span class="muted">· {e(c.get("detail"))}</span>' if c.get("detail") and not c["ok"] else ""
        items.append(f'<li><b class="{cls}">{mark}</b>{e(c["name"])}{detail}</li>')
    return '<ul class="ctl">' + "".join(items) + "</ul>"


def build_html(data, analysis, hist_html=""):
    adjustments = analysis.get("findings") or {}
    discarded = {str(d.get("id")): d.get("reason", "") for d in analysis.get("discarded") or []}
    findings = []
    for h in data.get("findings") or []:
        h = dict(h)
        a = adjustments.get(h["id"]) or {}
        if a.get("severity") in SEV:
            h["severity"] = a["severity"]
        h["_note"] = a.get("note")
        h["_discarded"] = discarded.get(h["id"])
        findings.append(h)
    live = [h for h in findings if not h["_discarded"]]
    emails = data.get("emails") or []
    exp = data.get("expectations") or []
    r = data.get("summary") or {}
    body = []

    serious = [h for h in live if h["severity"] in ("Critical", "High")]
    if not emails and not exp:
        tone, text = "warn", "There are no emails in the mailbox for that filter"
    elif r.get("not_received"):
        tone, text = "bad", f'{r["not_received"]} expected email(s) did not arrive'
    elif serious:
        tone, text = "bad", f"{len(serious)} important problem(s) in the emails"
    elif live:
        tone, text = "warn", "The emails arrive; there are details to improve"
    else:
        tone, text = "ok", "The emails arrive fine and without problems"
    body.append(banner(analysis.get("verdict") or text, analysis.get("verdict_tone") or tone))
    ne = r.get("expectations", 0)
    body.append('<div style="margin-top:20px">' + kpi_tiles([
        ("Emails reviewed", r.get("emails", 0), "", data.get("filter") or "the whole mailbox", "list"),
        ("Expectations met", f'{r.get("met", 0)}/{ne}' if ne else "—", ("ok" if r.get("met") == ne else "bad") if ne else "",
         "what had to arrive, the way it had to arrive", "target", {"pct": r.get("met", 0) / ne * 100} if ne else None),
        ("Not received", r.get("not_received", 0), "bad" if r.get("not_received") else "ok", "expected emails that are not there", "bad"),
        ("Findings", len(live), "bad" if serious else ("warn" if live else "ok"), f'{len(serious)} of high or critical severity', "warn"),
        ("Unreplaced variables", r.get("unreplaced_variables", 0), "bad" if r.get("unreplaced_variables") else "ok",
         "{{name}}, undefined, null… in plain sight", "code"),
        ("Links with problems", r.get("problem_links", 0), "bad" if r.get("problem_links") else "ok", f'of {r.get("links", 0)} links reviewed', "link"),
        ("Compatibility", f'{r["compatibility_avg"]} %' if r.get("compatibility_avg") is not None else "—",
         "" if r.get("compatibility_avg") is None else ("ok" if r["compatibility_avg"] >= 90 else "warn"), "of the HTML with the email clients", "screen"),
    ]) + "</div>")
    if analysis.get("summary"):
        body.append(section("Executive summary", f'<div class="cardbody"><p class="lead">{e(analysis["summary"])}</p></div>'))

    if exp:
        rows = [[e(x["id"]), e(x.get("case") or "—"), f'<strong style="color:var(--ink)">{e(x.get("subject") or "—")}</strong>'
                 f'<div class="muted">{e(x.get("to") or "")}</div>', pill(EXPECT, x["status"]), checks(x),
                 f'<a href="#{e(x["email"])}" style="color:var(--ink)">{e(x["email"])}</a>' if x.get("email") else '<span class="muted">—</span>']
                for x in exp]
        body.append(section("What had to arrive", table(["ID", "Case", "Expected email", "Result", "Checks", "Email"], rows),
                            "each test case with the email it expects and what was verified"))

    if live:
        types = Counter(h["type"] for h in live)
        sev = Counter(h["severity"] for h in live)
        segs = [(sev[s], LEVEL_COLOR.get(s, NEUTRAL), s) for s in SEV if sev[s]]
        main_seg = max(segs, key=lambda s: s[0])
        body.append(two_col(
            section("Findings by type", bar_chart([(t, n, SERIES[i % len(SERIES)]) for i, (t, n) in enumerate(types.most_common())], label_width=160)),
            section("Findings by severity", donut_panel(segs, round(main_seg[0] / len(live) * 100), main_seg[2].lower()))))
    compat = [(c["id"], c["compatibility"]["pct"]) for c in emails if c.get("compatibility") and c["compatibility"].get("pct") is not None]
    if compat:
        body.append(section("HTML compatibility per email", column_chart([(i, p, OK if p >= 90 else WARNING if p >= 75 else CRITICAL) for i, p in compat],
                                                                        fmt=lambda v: f"{v:g} %"),
                            "percentage of the HTML features supported by the email clients (Outlook, Gmail, Apple Mail, Yahoo…)"))

    blocks = []
    for c in emails:
        hs = [h for h in findings if h.get("email") == c["id"]]
        attachments = ", ".join("%s (%s KB)" % (a["name"], a["kb"]) for a in c.get("attachments") or [])
        hdr = (f'<dl class="hdrs"><dt>From</dt><dd>{e(c["from"])}</dd><dt>To</dt><dd>{e(", ".join(c["to"]))}</dd>'
               + (f'<dt>Cc</dt><dd>{e(", ".join(c["cc"]))}</dd>' if c.get("cc") else "")
               + (f'<dt>Reply to</dt><dd>{e(", ".join(c["reply_to"]))}</dd>' if c.get("reply_to") else "")
               + f'<dt>Received</dt><dd>{e((c.get("date") or "")[:16].replace("T", " "))}</dd>'
               + f'<dt>Size</dt><dd>{e(c["size_kb"])} KB · HTML {e(c["html_kb"])} KB · {"with" if c["has_text"] else "without"} plain text</dd>'
               + (f'<dt>Attachments</dt><dd>{e(attachments)}</dd>' if attachments else "")
               + "</dl>")
        prob = ""
        for h in hs:
            note = f'<div><i>{e(h["_note"])}</i></div>' if h.get("_note") else ""
            prob += (f'<li>{level_badge(h["severity"])} <strong style="color:var(--ink)">{e(h["title"])}</strong>'
                     f'<div class="muted">{e(h.get("detail"))}</div>{note}</li>')
        links = ""
        if c.get("links"):
            rows = [[f'<span class="mono">{e(l["url"][:90])}</span>', e(l.get("text") or "—"), e(l.get("status") if l.get("status") is not None else "—"),
                     _pill(l["problem"]["text"], CRITICAL if l["problem"]["severity"] == "High" else WARNING, "!") if l.get("problem") else _pill("OK", OK, "✓")]
                    for l in c["links"][:30]]
            links = '<div class="lbl">Links</div><div class="linkst">' + table(["URL", "Text", "Status", "Result"], rows) + "</div>"
        compat_html = ""
        if c.get("compatibility") and c["compatibility"].get("problems"):
            compat_html = '<div class="lbl">Not supported in some clients</div><ul class="doclist">' + "".join(
                f'<li><strong style="color:var(--ink)">{e(p["title"])}</strong> <span class="muted">· {e(", ".join(p["clients"]))}</span></li>'
                for p in c["compatibility"]["problems"][:8]) + "</ul>"
        views = (f'<div class="views"><figure><figcaption>Desktop (700 px)</figcaption>{thumbnail(c.get("desktop_screenshot"), c["subject"] + " · desktop")}</figure>'
                 f'<figure><figcaption>Mobile (375 px)</figcaption>{thumbnail(c.get("mobile_screenshot"), c["subject"] + " · mobile")}</figure></div>')
        extra = " · ".join(x for x in [f'<a href="{e(c["eml"])}" download style="color:var(--ink)">download .eml</a>' if c.get("eml") else "",
                                        f'<a href="{e(c["view_in_mailpit"])}" target="_blank" rel="noopener" style="color:var(--ink)">view in Mailpit</a>'] if x)
        blocks.append(f'''<div class="email" id="{e(c["id"])}"><div><h3>{e(c["id"])} · {e(c["subject"] or "(no subject)")}
            {_pill(f"{len(hs)} finding(s)", CRITICAL if any(h["severity"] in ("Critical", "High") for h in hs) else WARNING if hs else OK, "!" if hs else "✓")}</h3>
            {hdr}{f'<div class="lbl">Problems</div><ul class="doclist">{prob}</ul>' if prob else '<p class="muted">No problems detected.</p>'}
            {links}{compat_html}<p class="muted" style="margin-top:10px">{extra}</p></div><div>{views}</div></div>''')
    if blocks:
        body.append(section("Each email", "".join(blocks), "how it looks on desktop and mobile, headers, links, attachments and problems"))

    if findings:
        rows = [[e(h["id"]), level_badge(h["severity"]), f'<span class="cat"><i style="background:{SERIES[0]}"></i>{e(h["type"])}</span>',
                 f'<strong style="color:var(--ink)">{e(h["title"])}</strong>' + (f'<div class="muted">Discarded: {e(h["_discarded"])}</div>' if h["_discarded"] else ""),
                 f'<a href="#{e(h["email"])}" style="color:var(--ink)">{e(h["email"])}</a>' if h.get("email") else '<span class="muted">—</span>']
                for h in findings]
        body.append(section("All findings", table(["ID", "Severity", "Type", "Finding", "Email"], rows)))
    body.append(missing_info(analysis.get("missing_info")))
    if analysis.get("recommendations"):
        rows = [[f'<strong style="color:var(--ink)">{e(x.get("action"))}</strong>', e(x.get("reason")), level_badge(x.get("priority"))]
                for x in analysis["recommendations"]]
        body.append(section("Recommendations", table(["Action", "Why", "Priority"], rows)))
    if analysis.get("next_steps"):
        body.append(section("Next steps", doc_list(analysis["next_steps"])))
    if hist_html:
        body.append(hist_html)
    meta_html = meta([("Story", data.get("story")), ("Mailbox", data.get("mailpit")), ("Mailpit", data.get("mailpit_version")),
                      ("Date", (data.get("date") or "")[:16].replace("T", " "))])
    return page("Email verification", "Emails", meta_html, CSS_EXTRA + CSS_EML + "".join(body))


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="HTML emails report from emails.json")
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
    hist_html = _history.section("emails", Path(a.data_json).resolve().parent, data)
    html = build_html(data, analysis, hist_html=hist_html)
    with open(a.output, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"OK: {a.output}")


if __name__ == "__main__":
    main()
