#!/usr/bin/env python3
"""
Reports portal: output/index.html with the latest report of each tool.

Usage (from the repo root):
    python scripts/reports_portal.py [--open]

Walks output/ (each folder is a tool: runs, exploratory, accessibility, ...; the ones added later
show up on their own) and the k0lmena reports (tools/k0lmena/reports/), and builds a page with one
card per tool: the latest HTML report of each story, site or suite, its date, the verdict or result
if the JSON has it, and the link to the previous run saved in history/.
At the top it has a search box and filters by tool, story, status and date, and two views: by tool
or by story (all the reports of a US together, from any tool).

Links are relative: output/index.html opens with a double click, without a server.

It regenerates itself: every HTML report built by the scripts (with _report_styles.page) updates it
when it finishes. To turn it off, set K0LMENIA_PORTAL=0 in the environment.
"""
import argparse
import atexit
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Readable names of the known folders (the others are shown with their name capitalized).
NAMES = {
    "runs": "Runs (E2E and API)", "exploratory": "Exploratory testing", "accessibility": "Accessibility",
    "web-performance": "Web performance", "failures": "Failure analysis", "coverage": "Coverage and traceability",
    "pixel-perfect": "Visual regression", "cross-browser": "Cross-browser", "repairs": "Automation repair",
    "case-selection": "Case selection", "emails": "Emails", "translator": "Translations", "case-review": "Case review",
    "charters": "Exploratory charters", "ux": "Usability", "forms": "Forms", "logs": "Logs",
    "security": "Web security", "performance": "Performance", "closure-reports": "Closure reports",
    "test-plans": "Test plans", "permissions": "Permissions by role", "resilience": "Resilience",
    "triage": "Bug triage", "dashboard": "Quality dashboard", "monitoring": "Synthetic monitoring",
    "evals": "Agent evals", "k0lmena": "npm test (k0lmena)", "token-metrics": "Token usage",
    "onboarding": "Onboarding",
    "shopify": "Shopify", "wordpress": "WordPress / WooCommerce", "salesforce": "Salesforce", "wallets": "Wallets and payments",
    "prestashop": "PrestaShop", "vtex": "VTEX", "sap": "SAP (GUI and Fiori)", "desktop": "Desktop apps",
    "mobile": "Mobile apps", "ai": "AI / LLM", "messaging": "Messaging and events", "soap": "SOAP",
    "dependencies": "Dependencies (SCA)", "sast": "Secure code (SAST)", "contracts": "Contract testing",
    "seo": "SEO and GEO", "data": "Data and pipelines", "dynamics": "Dynamics / CRM-ERP", "blockchain": "Blockchain / Web3",
    "ivr": "Voice / IVR", "games": "Video games", "pos": "Point of sale (POS)", "streaming": "Streaming and cameras",
    "observability": "Observability", "search": "Search and relevance", "documents": "Generated documents",
    "content": "Content and typos", "mutation": "Mutation testing",
}
# Card order: what is looked at most comes first.
ORDER = ["dashboard", "closure-reports", "runs", "k0lmena", "failures", "coverage", "monitoring", "test-plans",
         "case-selection", "exploratory", "accessibility", "web-performance", "performance", "security", "permissions",
         "resilience", "pixel-perfect", "cross-browser", "forms", "ux", "emails", "translator", "logs",
         "repairs", "case-review", "charters", "triage", "evals",
         "mobile", "shopify", "wordpress", "prestashop", "vtex", "dynamics", "salesforce", "sap",
         "desktop", "ai", "messaging", "soap", "contracts", "data", "seo", "dependencies", "sast",
         "blockchain", "wallets", "pos", "ivr", "games", "streaming",
         "observability", "search", "documents", "content", "mutation"]
IGNORE = {"history", "evidence", "screenshots", "videos", "crops", "diffs", "lighthouse", "reference",
          "actual", "backup", "suite", "eml", "sessions", "node_modules"}
_STAMP = re.compile(r"[-_]?\d{4}-?\d{2}-?\d{2}([-_T]?\d{2}-?\d{2}(-?\d{2})?)?$")
_REPORT_PREFIXES = ("report-", "closure-", "plan-")


def _date(p):
    return datetime.fromtimestamp(p.stat().st_mtime)


def _htmls(folder):
    """The .html files of the folder, without going into history/ or the evidence folders."""
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in IGNORE and not d.startswith((".", "_"))]
        for a in files:
            if a.lower().endswith(".html"):
                yield Path(root) / a


def _k0_report(p):
    """The full k0lmena report (index.html from npm run report:<suite>, next to cucumber-report.json)."""
    return p.name.lower() == "index.html" and (p.parent / "cucumber-report.json").exists()


def _main_report(files):
    """Out of several .html files of the same unit, the most recent main report."""
    def weight(p):
        n = p.name.lower()
        return (_k0_report(p), n.endswith("-report.html") or n.startswith(_REPORT_PREFIXES + ("cucumber",)), p.stat().st_mtime)
    return max(files, key=weight)


def _read_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def status_of(html):
    """Verdict or result of a report, from the JSON files next to it (or "")."""
    folder = html.parent
    candidates = [folder / "analysis.json"]
    stem = html.stem
    for pref in _REPORT_PREFIXES:
        if stem.startswith(pref):
            candidates.append(folder / f"_results-{stem[len(pref):]}.json")
            candidates.append(folder / f"{stem}.json")
    candidates += sorted(p for p in folder.glob("*.json") if p not in candidates)
    for c in candidates:
        d = _read_json(c) if c.exists() else None
        if not isinstance(d, dict):
            continue
        if d.get("verdict"):
            return str(d["verdict"])
        cases = d.get("cases")
        if isinstance(cases, list) and cases and isinstance(cases[0], dict) and "status" in cases[0]:
            ok = sum(1 for x in cases if str(x.get("status", "")).lower() == "passed")
            return f"{ok}/{len(cases)} passed"
    if html.name.startswith("cucumber") or (folder / "cucumber-report.json").exists():
        d = _read_json(folder / "cucumber-report.json")
        if isinstance(d, list):
            total = ok = 0
            for f in d:
                for sc in f.get("elements") or []:
                    if sc.get("type") == "background":
                        continue
                    total += 1
                    statuses = [(p.get("result") or {}).get("status") for p in sc.get("steps") or []]
                    ok += bool(statuses) and all(s in ("passed", "skipped") for s in statuses) and "passed" in statuses
            if total:
                return f"{ok}/{total} scenarios passed"
    return ""


def _previous(unit_folder):
    """(number of saved runs, the report of the most recent one) from history/."""
    h = unit_folder / "history"
    if not h.is_dir():
        return 0, None
    runs = sorted((d for d in h.iterdir() if d.is_dir()), key=lambda d: d.name)
    if not runs:
        return 0, None
    last = runs[-1]
    reports = sorted(last.rglob("*.html"))
    return len(runs), (_main_report(reports) if reports else None)


def units(folder):
    """Reports of a tool: [{"unit", "html", "date", "status", "history", "previous", "others"}]."""
    groups = {}
    for html in _htmls(folder):
        rel = html.relative_to(folder)
        if len(rel.parts) > 1:
            key, base = rel.parts[0], folder / rel.parts[0]
        else:
            key = _STAMP.sub("", html.stem) or html.stem
            m = re.search(r"(US-\d+|API|TC-API)", html.stem, re.I)
            key = m.group(1).upper() if m and html.stem.startswith(_REPORT_PREFIXES) else key
            base = folder
        groups.setdefault(key, {"base": base, "htmls": []})["htmls"].append(html)
    output = []
    for key, g in groups.items():
        html = _main_report(g["htmls"])
        n, previous = _previous(g["base"]) if g["base"] != folder else (0, None)
        others = sorted({h for h in g["htmls"] if h != html and h.parent == html.parent}, key=lambda p: p.name)
        output.append({"unit": key, "html": html, "date": _date(html), "status": status_of(html),
                       "history": n, "previous": previous, "others": others})
    return sorted(output, key=lambda u: u["date"], reverse=True)


def discover(output, reports_k0=None):
    """{tool: [units]} for every folder of output/ (and npm test), with or without reports."""
    tools = {}
    if output.is_dir():
        for d in sorted(p for p in output.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))):
            tools[d.name] = units(d)
    if reports_k0 and Path(reports_k0).is_dir():
        k0 = []
        for suite in sorted(p for p in Path(reports_k0).iterdir() if p.is_dir()):
            us = units(suite)
            # The full report (index.html + features/) and the basic Cucumber one are the same run:
            # a single entry, the full one, with the basic one as an "other" and without the features/ pages.
            full = next((u for u in us if _k0_report(u["html"]) and u["html"].parent == suite), None)
            if full:
                basics = [u["html"] for u in us if u is not full and u["html"].parent == suite]
                full["others"] = sorted(set(full["others"]) | set(basics), key=lambda p: p.name)
                us = [u for u in us if u is full or (u["html"].parent != suite and u["unit"] != "features")]
            for u in us:
                u["unit"] = suite.name if u["unit"] in (Path(u["html"]).stem, "cucumber-report", "index") else f'{suite.name} · {u["unit"]}'
                if u["html"].parent == suite:
                    u["history"], u["previous"] = _previous(suite)
                k0.append(u)
        tools["k0lmena"] = sorted(k0, key=lambda u: u["date"], reverse=True)
    order = {n: i for i, n in enumerate(ORDER)}
    return dict(sorted(tools.items(), key=lambda kv: (order.get(kv[0], len(ORDER)), kv[0])))


def _tone(status):
    t = (status or "").lower()
    m = re.match(r"(\d+)/(\d+)", t)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return "ok" if a == b else "bad" if a < b * 0.8 else "warn"
    if re.search(r"not ready|no-go|no go|critical|block|fail|reject|high risk|risk high", t):
        return "bad"
    if re.search(r"observation|review|risk|partial|condition|attention|medium|caveat", t):
        return "warn"
    if re.search(r"ready|\bgo\b|in order|passed|\bok\b|no findings|meets|compliant", t):
        return "ok"
    return ""


_STORY = re.compile(r"\b([A-Z][A-Z0-9]{0,9}-\d+)\b")


def story_of(u):
    """The story of a report (US-001, PROJ-12...) taken from the unit or the path; if there is none, the unit."""
    for text in [u.get("unit", "")] + list(Path(u["html"]).parts[::-1]):
        m = _STORY.search(str(text))
        if m and not m.group(1).startswith(("TC-API", "BUG-", "MI-")):
            return m.group(1)
    return u.get("unit") or "—"


TONE_TEXT = {"ok": "OK", "warn": "Review", "bad": "Critical", "": "No status"}

# Portal filters: search, tool, story, status and date, plus the view by tool or by story.
# They hide with the "out" class (the per-table searches use "hidden": they combine).
CSS_PORTAL = """
.out{display:none!important}
.filters{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:16px 22px 18px}
.filters label{display:flex;flex-direction:column;gap:5px;font-family:var(--mono);font-size:11px;color:var(--muted);text-transform:lowercase}
.filters input,.filters select{font:inherit;font-family:var(--sans);font-size:13px;color:var(--ink);background:var(--surface);
  border:1px solid var(--line);border-radius:10px;padding:8px 11px;min-width:170px}
.filters input:focus,.filters select:focus{outline:none;border-color:var(--yellow-line);box-shadow:var(--glow-k0)}
.filters .group-btn{display:flex;gap:6px;flex-wrap:wrap}
.filters button{font:inherit;font-size:12px;font-weight:500;color:var(--body);background:var(--surface);border:1px solid var(--line);
  border-radius:8px;padding:7px 11px;cursor:pointer}
.filters button.on{color:#0E0C09;background:var(--accent);border-color:var(--accent);font-weight:600}
.filters .count{margin-left:auto;font-family:var(--mono);font-size:12px;color:var(--muted);align-self:flex-end;padding-bottom:8px}
.filters .clear{background:transparent;border-style:dashed}
"""

JS_PORTAL = r"""
(function(){
var f=document.getElementById('filters');if(!f)return;
var q=f.querySelector('[name=q]'),tool=f.querySelector('[name=tool]'),story=f.querySelector('[name=story]'),date=f.querySelector('[name=date]');
var tone='',view='tool',count=f.querySelector('.count');
function stripAccents(t){return (t||'').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'');}
function apply(){
  var now=Date.now(),days=date.value?parseInt(date.value,10):0,txt=stripAccents(q.value.trim()),vis=0,total=0;
  [].forEach.call(document.querySelectorAll('.view'),function(v){v.classList.toggle('out',v.getAttribute('data-view')!==view);});
  var active=document.querySelector('.view[data-view="'+view+'"]');
  [].forEach.call(active.querySelectorAll('tr.pr'),function(tr){
    total++;
    var ok=(!tool.value||tr.dataset.tool===tool.value)&&(!story.value||tr.dataset.story===story.value)&&(!tone||tr.dataset.tone===tone)
      &&(!days||now-parseInt(tr.dataset.date,10)<=days*86400000)&&(!txt||stripAccents(tr.textContent).indexOf(txt)>=0);
    tr.classList.toggle('out',!ok);if(ok)vis++;});
  [].forEach.call(active.querySelectorAll('.section'),function(s){
    var rows=s.querySelectorAll('tr.pr');if(!rows.length)return;
    s.classList.toggle('out',![].some.call(rows,function(tr){return !tr.classList.contains('out');}));});
  count.textContent=vis+' of '+total+' reports';
  try{localStorage.setItem('k0-portal',JSON.stringify({q:q.value,tool:tool.value,story:story.value,date:date.value,tone:tone,view:view}));}catch(e){}
}
f.addEventListener('input',apply);f.addEventListener('change',apply);
f.addEventListener('click',function(ev){var b=ev.target.closest('button');if(!b)return;ev.preventDefault();
  if(b.dataset.tone!==undefined){tone=b.dataset.tone;[].forEach.call(f.querySelectorAll('[data-tone]'),function(x){x.classList.toggle('on',x===b);});}
  if(b.dataset.view){view=b.dataset.view;[].forEach.call(f.querySelectorAll('[data-view]'),function(x){x.classList.toggle('on',x===b);});}
  if(b.classList.contains('clear')){q.value='';tool.value='';story.value='';date.value='';tone='';
    [].forEach.call(f.querySelectorAll('[data-tone]'),function(x){x.classList.toggle('on',x.dataset.tone==='');});}
  apply();});
try{var g=JSON.parse(localStorage.getItem('k0-portal')||'null');if(g){q.value=g.q||'';tool.value=g.tool||'';story.value=g.story||'';date.value=g.date||'';
  tone=g.tone||'';view=g.view||'tool';
  [].forEach.call(f.querySelectorAll('[data-tone]'),function(x){x.classList.toggle('on',x.dataset.tone===tone);});
  [].forEach.call(f.querySelectorAll('[data-view]'),function(x){x.classList.toggle('on',x.dataset.view===view);});}}catch(e){}
apply();
})();
"""


def build_html(tools, target):
    from _report_styles import page, meta, section, kpi_tiles, e, _pill, OK, WARNING, CRITICAL, NEUTRAL

    html_dir = Path(target).resolve().parent

    def link(p, text):
        try:
            rel = os.path.relpath(Path(p).resolve(), html_dir).replace("\\", "/")
        except ValueError:  # a different drive on Windows: there is no relative path
            rel = Path(p).resolve().as_uri()
        return f'<a href="{e(rel)}">{e(text)}</a>'

    def name(h):
        return NAMES.get(h, h.replace("-", " ").capitalize())

    with_reports = {k: v for k, v in tools.items() if v}
    empty = [k for k, v in tools.items() if not v]
    everything = [(h, u) for h, us in with_reports.items() for u in us]
    latest = max((u["date"] for _, u in everything), default=None)
    bad = sum(1 for _, u in everything if _tone(u["status"]) == "bad")
    stories = sorted({story_of(u) for _, u in everything})
    body = [kpi_tiles([
        ("Tools with reports", len(with_reports), "", f"{len(tools)} folder(s) in total", "grid"),
        ("Reports", len(everything), "", f"from {len(stories)} story(ies), site(s) or suite(s)", "list"),
        ("To review", bad, "bad" if bad else "ok", "with a verdict or result in red", "warn"),
        ("Latest report", latest.strftime("%m/%d %H:%M") if latest else "—", "", "", "clock"),
    ])]
    if not everything:
        body.append(section("No reports yet", '<div class="cardbody"><p class="muted">When the agents generate '
                            'reports, they will show up here. This portal updates itself every time one is built.</p></div>'))
    color = {"ok": OK, "warn": WARNING, "bad": CRITICAL}
    icon = {"ok": "✓", "warn": "!", "bad": "✕"}

    def row(h, u, first):
        t = _tone(u["status"])
        status = _pill(u["status"], color.get(t, NEUTRAL), icon.get(t, "●")) if u["status"] else '<span class="muted">—</span>'
        others = " · ".join(link(o, o.stem) for o in u["others"][:4])
        report = link(u["html"], u["html"].name) + (f'<div class="muted" style="font-size:12px">{others}</div>' if others else "")
        hist = (link(u["previous"], f'previous ({u["history"]} saved)')
                if u["previous"] else '<span class="muted">—</span>')
        data = (f' class="pr" data-tool="{e(h)}" data-story="{e(story_of(u))}" data-tone="{t}"'
                f' data-date="{int(u["date"].timestamp() * 1000)}"')
        cells = [first, report, e(u["date"].strftime("%m/%d/%Y %H:%M")), status, hist]
        return f'<tr{data}>' + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"

    def table_(first_col, rows):
        th = "".join(f"<th>{e(x)}</th>" for x in [first_col, "Report", "Date", "Status", "Previous run"])
        return f'<div class="tablecard"><table><thead><tr>{th}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'

    if everything:
        tool_options = "".join(f'<option value="{e(h)}">{e(name(h))}</option>' for h in with_reports)
        story_options = "".join(f'<option value="{e(x)}">{e(x)}</option>' for x in stories)
        tones = "".join(f'<button type="button" data-tone="{k}"{" class=on" if k == "" else ""}>{e(v)}</button>'
                        for k, v in (("", "All"), ("bad", "Critical"), ("warn", "Review"), ("ok", "OK")))
        body.append(section("Filter", f'''<form class="filters" id="filters" onsubmit="return false">
  <label>search<input name="q" type="search" placeholder="Text, story, file…"></label>
  <label>tool<select name="tool"><option value="">All</option>{tool_options}</select></label>
  <label>story / site / suite<select name="story"><option value="">All</option>{story_options}</select></label>
  <label>date<select name="date"><option value="">All</option><option value="1">Last 24 h</option>
    <option value="7">Last 7 days</option><option value="30">Last 30 days</option></select></label>
  <label>status<span class="group-btn">{tones}</span></label>
  <label>view<span class="group-btn"><button type="button" data-view="tool" class="on">By tool</button>
    <button type="button" data-view="story">By story</button></span></label>
  <button type="button" class="clear">Clear filters</button>
  <span class="count"></span>
</form>'''))
        by_tool = [section(name(h), table_("Story / site / suite", [row(h, u, f'<b>{e(u["unit"])}</b>') for u in us]),
                           f"{len(us)} report(s)") for h, us in with_reports.items()]
        grouped = {}
        for h, u in everything:
            grouped.setdefault(story_of(u), []).append((h, u))
        by_story = []
        for x in stories:
            items = sorted(grouped[x], key=lambda hu: hu[1]["date"], reverse=True)
            by_story.append(section(x, table_("Tool", [row(h, u, f'<b>{e(name(h))}</b>') for h, u in items]),
                                    f"{len(items)} report(s)"))
        body.append(f'<div class="view subgrid" data-view="tool">{"".join(by_tool)}</div>')
        # The by-story view does not add entries to the sidebar index (it would duplicate the other view).
        body.append(f'<div class="view subgrid out" data-view="story">{"".join(by_story).replace(" data-nav=", " data-nav-story=")}</div>')
    if empty:
        chips = " ".join(f'<span class="chip">{e(name(v))}</span>' for v in empty)
        body.append(section("No reports yet", f'<div class="cardbody"><div class="meta">{chips}</div></div>'))
    html_ = page("Reports portal", "Portal", meta([("Updated", datetime.now().strftime("%m/%d/%Y %H:%M")),
                                                   ("Folder", "output/")]), "".join(body))
    return html_.replace("</style>", CSS_PORTAL + "</style>", 1).replace("</body>", f"<script>{JS_PORTAL}</script></body>", 1)


def generate(output=None, reports_k0=None, target=None):
    output = Path(output or ROOT / "output")
    reports_k0 = reports_k0 if reports_k0 is not None else ROOT / "tools" / "k0lmena" / "reports"
    target = Path(target or output / "index.html")
    target.parent.mkdir(parents=True, exist_ok=True)
    tools = discover(output, reports_k0)
    target.write_text(build_html(tools, target), encoding="utf-8")
    return target, tools


# ------------------------------------------------------------------ automatic update
_SCHEDULED = [False]


def _update_on_exit():
    try:
        generate()
    except Exception as ex:  # the portal never breaks a report
        print(f"[!] Could not update the reports portal ({ex}).", file=sys.stderr)


def schedule():
    """Regenerates output/index.html when the process ends (after the report was written).
    Does nothing in tests, with K0LMENIA_PORTAL=0 or if output/ does not exist."""
    if _SCHEDULED[0] or os.environ.get("K0LMENIA_PORTAL", "1") == "0" or "pytest" in sys.modules:
        return
    if not (ROOT / "output").is_dir():
        return
    _SCHEDULED[0] = True
    atexit.register(_update_on_exit)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Portal with the latest report of each tool (output/index.html)")
    ap.add_argument("--open", action="store_true", help="opens the portal in the browser")
    ap.add_argument("--output", help=argparse.SUPPRESS)
    ap.add_argument("--reports", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    _SCHEDULED[0] = True  # this process already generates the portal: page() must not schedule it again
    target, tools = generate(a.output, a.reports)
    n = sum(len(v) for v in tools.values())
    print(f"Portal: {target} ({n} report(s) from {sum(1 for v in tools.values() if v)} tool(s))")
    if a.open:
        import webbrowser
        webbrowser.open(target.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
