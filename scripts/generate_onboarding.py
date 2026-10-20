#!/usr/bin/env python3
"""
Onboarding plan for a QA who joins the project (onboarding-guide agent).

Usage (from the repo root):
    python scripts/generate_onboarding.py <plan.json> [--output <folder>]

From the JSON written by the agent, it builds output/onboarding/<person or role>/ with:
  - onboarding-plan.html  (with the style of the reports; the checklist can be ticked and is saved
                          in the browser)
  - onboarding-plan.md    (the same in Markdown, with the tables aligned)

Schema of the JSON (everything optional except "person" and "role"):
{
  "person": "Ana", "role": "Manual QA",                    // role: Manual QA | Automation engineer | QA lead | …
  "project": "Online store", "date": "2026-10-14",
  "summary": "What the product is and what the person will do in the first weeks.",
  "product": {
    "modules": [{"name": "Checkout", "description": "...", "source": "input/documentation/project/summary.md"}],
    "roles": [{"role": "Buyer", "can": "..."}],
    "flows": [{"name": "Buy with a card", "screens": "Cart → Payment → Confirmation", "source": "functional-map.md"}],
    "glossary": [{"term": "SKU", "definition": "..."}]
  },
  "environment": [{"what": "Doctor", "status": "ok|warning|missing", "detail": "...", "action": "..."}],
  "agents": [{"agent": "manual-case-generator", "purpose": "...", "request": "Generate the cases for PROJ-12"}],
  "plan": [{"when": "Day 1", "task": "...", "done_when": "...", "agent": "optional"}],
  "questions": [{"id": "MI-01", "question": "...", "to_whom": "PO", "why": "..."}],
  "checklist": ["Have the .env complete", "..."],
  "missing": ["There is no project documentation: ask the project-documenter to build it."]
}
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

TONE = {"ok": "ok", "warning": "warn", "missing": "bad"}
STATUS_TEXT = {"ok": "Ready", "warning": "Review", "missing": "Missing"}

CSS_ONB = """
.check{list-style:none;display:flex;flex-direction:column;gap:8px;padding:6px 22px 22px}
.check li label{display:flex;align-items:flex-start;gap:12px;padding:10px 14px;border:1px solid var(--line);border-radius:10px;
  background:var(--surface);cursor:pointer;color:var(--body);transition:border-color .15s}
.check li label:hover{border-color:var(--yellow-line)}
.check input{appearance:none;flex:none;width:20px;height:18px;margin-top:2px;cursor:pointer;
  clip-path:polygon(25% 3%,75% 3%,100% 50%,75% 97%,25% 97%,0 50%);background:var(--border)}
.check input:checked{background:var(--accent)}
.check input:checked+span{color:var(--muted);text-decoration:line-through}
.progress{display:flex;align-items:center;gap:12px;padding:0 22px 6px;font-family:var(--mono);font-size:12px;color:var(--muted)}
.progress .b{flex:1;height:6px;border-radius:999px;background:rgba(244,239,230,.07);overflow:hidden}
.progress .b span{display:block;height:100%;width:0;background:linear-gradient(90deg,#FFD60A,#FF8A00);transition:width .2s}
.order-ex{font-family:var(--mono);font-size:12.5px;color:var(--ink)}
.order-ex::before{content:"› ";color:var(--accent)}
"""

JS_ONB = r"""
(function(){
var key='k0-onboarding-'+document.title,boxes=[].slice.call(document.querySelectorAll('.check input'));
if(!boxes.length)return;
var st={};try{st=JSON.parse(localStorage.getItem(key)||'{}');}catch(e){}
var bar=document.querySelector('.progress .b span'),txt=document.querySelector('.progress .t');
function paint(){var n=boxes.filter(function(c){return c.checked;}).length;
  if(bar)bar.style.width=(100*n/boxes.length)+'%';if(txt)txt.textContent=n+' of '+boxes.length+' done';}
boxes.forEach(function(c){c.checked=!!st[c.id];c.addEventListener('change',function(){st[c.id]=c.checked;
  try{localStorage.setItem(key,JSON.stringify(st));}catch(e){}paint();});});
paint();
})();
"""


def slug(text):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower().translate(str.maketrans("áéíóúñü", "aeiounu"))).strip("-")
    return s or "person"


def build_html(d):
    from _report_styles import e, page, meta, section, kpi_tiles, table, doc_list, two_col, banner, _pill, OK, WARNING, CRITICAL
    prod = d.get("product") or {}
    env = d.get("environment") or []
    missing = sum(1 for x in env if x.get("status") == "missing")
    body = [kpi_tiles([
        ("Product modules", len(prod.get("modules") or []), "", f'{len(prod.get("flows") or [])} key flow(s)', "grid"),
        ("Recommended agents", len(d.get("agents") or []), "", f'for the {d.get("role", "")} role', "person"),
        ("Plan tasks", len(d.get("plan") or []), "", "with their definition of done", "list"),
        ("Environment", "Ready" if env and not missing else f"{missing} pending" if env else "—",
         "ok" if env and not missing else "warn" if env else "", "according to npm run doctor", "ok" if env and not missing else "warn"),
    ])]
    for f in d.get("missing") or []:
        body.append(banner(f, "warn"))
    if d.get("summary"):
        body.append(section("Welcome", f'<div class="cardbody"><p class="lead">{e(d["summary"])}</p></div>'))
    if prod.get("modules"):
        body.append(section("The product: modules", table(["Module", "What it does", "Source"],
                                                          [[f'<b>{e(m.get("name"))}</b>', e(m.get("description")), f'<span class="mono">{e(m.get("source", "—"))}</span>']
                                                           for m in prod["modules"]])))
    left = section("Key flows", table(["Flow", "Screens", "Source"], [[f'<b>{e(f.get("name"))}</b>', e(f.get("screens")),
                                                                       f'<span class="mono">{e(f.get("source", "—"))}</span>'] for f in prod.get("flows") or []]), width=6) \
        if prod.get("flows") else ""
    right = section("Application roles", table(["Role", "Can"], [[f'<b>{e(r.get("role"))}</b>', e(r.get("can"))] for r in prod.get("roles") or []]), width=6) \
        if prod.get("roles") else ""
    if left and right:
        body.append(two_col(left, right))
    elif left or right:
        body.append(left or right)
    if env:
        color = {"ok": OK, "warning": WARNING, "missing": CRITICAL}
        icon = {"ok": "✓", "warning": "!", "missing": "✕"}
        body.append(section("Your environment", table(["What", "Status", "Detail", "What to do"],
                                                      [[f'<b>{e(x.get("what"))}</b>', _pill(STATUS_TEXT.get(x.get("status"), "—"), color.get(x.get("status"), WARNING),
                                                                                          icon.get(x.get("status"), "●")),
                                                        e(x.get("detail")), f'<span class="mono">{e(x.get("action", ""))}</span>'] for x in env])))
    if d.get("agents"):
        body.append(section(f'k0lmenIA for your role: {d.get("role", "")}', table(["Agent", "What for", "Sample request for this project"],
                                                                                 [[f'<b>{e(a.get("agent"))}</b>', e(a.get("purpose")),
                                                                                   f'<span class="order-ex">{e(a.get("request"))}</span>'] for a in d["agents"]])))
    if d.get("plan"):
        body.append(section("Plan for the first weeks", table(["When", "Task", "Done when", "With"],
                                                              [[f'<b>{e(p.get("when"))}</b>', e(p.get("task")), e(p.get("done_when")),
                                                                e(p.get("agent") or "—")] for p in d["plan"]])))
    if d.get("questions"):
        body.append(section("Questions for the team", table(["ID", "Question", "To whom", "Why"],
                                                            [[f'<span class="id">{e(q.get("id", ""))}</span>', e(q.get("question")), e(q.get("to_whom", "—")),
                                                              e(q.get("why", ""))] for q in d["questions"]]),
                            "what is not documented: nothing is made up"))
    if prod.get("glossary"):
        body.append(section("Glossary", table(["Term", "What it means"], [[f'<b>{e(g.get("term"))}</b>', e(g.get("definition"))]
                                                                          for g in prod["glossary"]])))
    if d.get("checklist"):
        items = "".join(f'<li><label><input type="checkbox" id="c{i}"><span>{e(c)}</span></label></li>' for i, c in enumerate(d["checklist"]))
        body.append(section("Checklist", f'<div class="progress"><span class="t"></span><span class="b"><span></span></span></div><ul class="check">{items}</ul>',
                            "saved in this browser"))
    title = f'Onboarding for {d.get("person", "")}'.strip()
    html = page(title, "Onboarding", meta([("Role", d.get("role")), ("Project", d.get("project")), ("Date", d.get("date"))]), "".join(body))
    return html.replace("</style>", CSS_ONB + "</style>", 1).replace("</body>", f"<script>{JS_ONB}</script></body>", 1)


def build_md(d):
    prod = d.get("product") or {}
    l = [f'# Onboarding for {d.get("person", "")}', "", f'- **Role:** {d.get("role", "")}', f'- **Project:** {d.get("project", "")}',
         f'- **Date:** {d.get("date", "")}', ""]
    for f in d.get("missing") or []:
        l += [f"> {f}", ""]
    if d.get("summary"):
        l += ["## Welcome", "", d["summary"], ""]

    def md_table(title, head, rows):
        if not rows:
            return
        l.extend([f"## {title}", "", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)])
        l.extend("| " + " | ".join(str(c or "").replace("|", "/").replace("\n", " ") for c in f) + " |" for f in rows)
        l.append("")

    md_table("The product: modules", ["Module", "What it does", "Source"], [[m.get("name"), m.get("description"), m.get("source")] for m in prod.get("modules") or []])
    md_table("Key flows", ["Flow", "Screens", "Source"], [[f.get("name"), f.get("screens"), f.get("source")] for f in prod.get("flows") or []])
    md_table("Application roles", ["Role", "Can"], [[r.get("role"), r.get("can")] for r in prod.get("roles") or []])
    md_table("Your environment", ["What", "Status", "Detail", "What to do"],
             [[x.get("what"), STATUS_TEXT.get(x.get("status"), ""), x.get("detail"), x.get("action")] for x in d.get("environment") or []])
    md_table(f'k0lmenIA for your role: {d.get("role", "")}', ["Agent", "What for", "Sample request"],
             [[a.get("agent"), a.get("purpose"), a.get("request")] for a in d.get("agents") or []])
    md_table("Plan for the first weeks", ["When", "Task", "Done when", "With"],
             [[p.get("when"), p.get("task"), p.get("done_when"), p.get("agent") or "-"] for p in d.get("plan") or []])
    md_table("Questions for the team", ["ID", "Question", "To whom", "Why"],
             [[q.get("id"), q.get("question"), q.get("to_whom"), q.get("why")] for q in d.get("questions") or []])
    md_table("Glossary", ["Term", "What it means"], [[g.get("term"), g.get("definition")] for g in prod.get("glossary") or []])
    if d.get("checklist"):
        l += ["## Checklist", ""] + [f"- [ ] {c}" for c in d["checklist"]] + [""]
    return "\n".join(l)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Onboarding plan (onboarding-guide agent)")
    ap.add_argument("plan_json")
    ap.add_argument("--output", help="output folder (by default output/onboarding/<person or role>)")
    a = ap.parse_args(argv)
    d = json.loads(Path(a.plan_json).read_text(encoding="utf-8"))
    if not d.get("person") and not d.get("role"):
        ap.error('the JSON needs "person" or "role"')
    folder = Path(a.output) if a.output else ROOT / "output" / "onboarding" / slug(d.get("person") or d.get("role"))
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "onboarding-plan.html").write_text(build_html(d), encoding="utf-8")
    md = folder / "onboarding-plan.md"
    md.write_text(build_md(d), encoding="utf-8")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "format_tables.py"), str(md)], capture_output=True, text=True)
    print(f"Onboarding plan: {folder / 'onboarding-plan.html'} (and onboarding-plan.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
