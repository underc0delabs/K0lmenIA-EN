#!/usr/bin/env python3
"""
Report of the survey of a whole project (project-researcher agent).

Usage (from the repo root):
    python scripts/generate_research_report.py <research.json> [--output <folder>]

From the JSON written by the agent, it builds in the JSON's folder (or in --output):
  - research-report.html         (full web page: indicators, charts, CONCEPT MAPS, search and navigation)
  - research-report.md           (the same in Markdown, with aligned tables)
  - summary.md                   (short summary, one page: what the project is and what is most urgent)
  - research-presentation.html   (self-contained presentation; <-/-> to navigate, prints to PDF, one slide per page)
  - history/<date-time>/         (copy of this survey; the last 5 are kept). If there is a previous one,
                                 the report includes "Changes since the previous survey": new and resolved
                                 ambiguities and questions.

JSON schema (everything optional except "project"):
{
  "project": "Online store", "key": "PROJ", "date": "2026-10-19",
  "depth": "normal", "focus": "", "audience": "Manual QA",
  "board": "https://my-company.atlassian.net/jira/software/projects/PROJ/boards/12",  // the URL the person gave
  "summary": "What the product is, who it is for and what state it is in (2 or 3 sentences).",
  "coverage": {"total_items": 1240, "read": 85, "criteria": "Open Critical/High, current sprint, 2 per active epic",
               "epics": 14, "stories": 60, "tasks": 110, "comments": 240},
  // hierarchy: what was walked going down the board (epic -> stories -> tasks), with comments and links per item.
  "hierarchy": [{"epic": {"id": "PROJ-3", "title": "Checkout", "status": "In progress", "url": "https://.../PROJ-3"},
                 "stories": [{"id": "PROJ-12", "title": "Card payment", "status": "In progress", "assignee": "Ann",
                              "tasks": 4, "comments": 7, "links": ["Confluence 'Payment rules'", "Figma Checkout"],
                              "note": "decision in a comment: up to 12 installments"}]}],
  // references: every reference link found in epics/stories/tasks/comments.
  "references": [{"type": "Confluence", "title": "Payment rules", "url": "https://.../wiki/...", "origin": "PROJ-12 (comment)", "read": true}],
  // maps: concept maps (nodes + directed edges). Make several: one for architecture, one for how it
  // works (flow), one for modules. If you send none, a modules map is built automatically. The "level" of
  // each node (column) is computed from the longest path from a root; "group" sets the color and the legend.
  "maps": [{"title": "Architecture", "type": "architecture", "description": "Layers and systems.",
            "nodes": [{"id": "web", "label": "Web front end (React)", "group": "Frontend"},
                      {"id": "api", "label": "API (Node)", "group": "Backend", "note": "REST"},
                      {"id": "db", "label": "PostgreSQL", "group": "Data"},
                      {"id": "pg", "label": "Stripe", "group": "External"}],
            "edges": [{"from": "web", "to": "api", "label": "HTTPS"}, {"from": "api", "to": "db"}, {"from": "api", "to": "pg", "label": "charges"}]},
           {"title": "How it works: buying", "type": "flow",
            "nodes": [{"id": "s1", "label": "Adds to cart"}, {"id": "s2", "label": "Checkout"},
                      {"id": "s3", "label": "Pays by card"}, {"id": "s4", "label": "Confirmation"}],
            "edges": [{"from": "s1", "to": "s2"}, {"from": "s2", "to": "s3"}, {"from": "s3", "to": "s4", "label": "ok"}]}],
  "sources": [{"source": "Jira PROJ", "type": "Management", "scope": "epics, active backlog and bugs",
               "status": "read|partial|not_accessible", "reason": "only if it is not read"}],
  "modules": [{"name": "Checkout", "description": "...", "status": "In development",
               "progress": {"done": 12, "total": 20}, "source": "PROJ-3 (epic)"}],
  "actors": [{"role": "Buyer", "can": "...", "source": "..."}],
  "flows": [{"name": "Buy by card", "steps": "Cart -> Payment -> Confirmation", "items": "PROJ-12, PROJ-14", "source": "..."}],
  "integrations": [{"system": "Stripe", "purpose": "charges", "type": "REST API + webhooks", "source": "..."}],
  "environments": [{"name": "QA", "url": "https://qa.store.com", "purpose": "testing", "source": "wiki/Environments"}],
  "stack": [{"layer": "Frontend", "technology": "React 19", "source": "README.md"}],
  "team": [{"role": "PO", "name": "Name shown in the tool", "topics": "payments, business rules", "source": "..."}],
  "decisions": [{"date": "2026-09-02", "decision": "...", "who": "PO", "source": "PROJ-12 (comment)"}],
  "backlog": {"by_status": {"To do": 40, "In progress": 12, "Done": 300},
              "by_type": {"Story": 200, "Bug": 60},
              "bugs_by_severity": {"Critical": 2, "High": 9, "Medium": 20, "Low": 4},
              "current_sprint": {"name": "Sprint 14", "start": "2026-10-13", "end": "2026-10-24", "items": 18},
              "releases": [{"name": "2.4", "date": "2026-11-05", "status": "Planned", "source": "..."}]},
  "current_testing": [{"what": "Manual regression in Test Plans", "status": "Partial", "source": "..."}],
  "glossary": [{"term": "SKU", "definition": "...", "source": "..."}],
  "timeline": [{"date": "2026-11-05", "milestone": "Release 2.4", "source": "..."}],
  "ambiguities": [{"id": "AMB-01", "type": "Ambiguity|Contradiction|Gap|Outdated|Dependency",
                   "what": "...", "sources": ["PROJ-45", "Confluence 'Payment rules'"], "impact": "High", "question": "Q-01"}],
  "questions": [{"id": "Q-01", "question": "...", "to_whom": "PO", "priority": "Critical", "why": "...", "related": "AMB-01"}],
  "startup_questions": ["What test data is there in QA and how do you request it?"],
  "risks": [{"risk": "...", "level": "High|Medium|Low", "reason": "...", "mitigation": "..."}],
  "next_steps": [{"step": "Build your onboarding", "agent": "onboarding-guide", "request": "Build the onboarding for Ann, manual QA"}],
  "missing": ["There is no Figma connector: the designs were not reviewed."]
}
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

SOURCE_STATUS = {"read": ("Read", "ok"), "partial": ("Partial", "warn"), "not_accessible": ("Not accessible", "missing")}
AMBIGUITY_TYPES = ["Contradiction", "Ambiguity", "Gap", "Outdated", "Dependency"]
PRIORITIES = ("Critical", "High", "Medium", "Low")
RISK_LEVELS = ("High", "Medium", "Low")
PRIO_ORDER = {p: i for i, p in enumerate(PRIORITIES)}
RISK_ORDER = {n: i for i, n in enumerate(RISK_LEVELS)}
MAX_HISTORY = 5

CSS_RSCH = """
.progress{display:flex;align-items:center;gap:10px;min-width:150px}
.progress .b{flex:1;height:6px;border-radius:999px;background:rgba(244,239,230,.07);overflow:hidden}
.progress .b span{display:block;height:100%;background:linear-gradient(90deg,#FFD60A,#FF8A00)}
.progress em{font-style:normal;font-family:var(--mono);font-size:12px;color:var(--muted);white-space:nowrap}
.sources-cell{font-family:var(--mono);font-size:12px;color:var(--muted)}
.sources-cell b{color:var(--ink);font-weight:600}
.map{padding:10px 18px 20px}
.map .desc{color:var(--muted);font-size:13px;margin:0 0 12px}
.map .wrap{overflow-x:auto}
.map svg{min-width:100%;height:auto}
.map .nbox{fill:var(--tile);stroke:var(--border)}
.map .ntext{fill:var(--ink);font:600 12.5px var(--sans)}
.map .nnote{fill:var(--muted);font:11px var(--mono)}
.map .edge{fill:none;stroke:var(--muted);stroke-width:1.6;opacity:.7}
.map .edge.back{stroke-dasharray:4 4;opacity:.5}
.map .elabel{fill:var(--muted);font:11px var(--mono)}
.map .elabel-bg{fill:var(--surface)}
"""


def slug(text):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower().translate(str.maketrans("áéíóúñü", "aeiounu"))).strip("-")
    return s or "project"


def _norm(text):
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def validate(d):
    """Warnings on stderr about what would leave the report incomplete or misleading. Does not stop the report."""
    warnings = []
    ids_q = [p.get("id") for p in d.get("questions") or []]
    ids_a = [a.get("id") for a in d.get("ambiguities") or []]
    for name, ids in (("questions", ids_q), ("ambiguities", ids_a)):
        repeated = sorted({i for i in ids if i and ids.count(i) > 1})
        if repeated:
            warnings.append(f"{name}: repeated IDs {', '.join(repeated)}")
    for a in d.get("ambiguities") or []:
        if a.get("type") == "Contradiction" and len(a.get("sources") or []) < 2:
            warnings.append(f"{a.get('id')}: a contradiction needs its two sources")
        if a.get("type") and a["type"] not in AMBIGUITY_TYPES:
            warnings.append(f"{a.get('id')}: type {a['type']!r} not in {'/'.join(AMBIGUITY_TYPES)}")
        if a.get("impact") and a["impact"] not in PRIORITIES:
            warnings.append(f"{a.get('id')}: impact {a['impact']!r} off the scale {'/'.join(PRIORITIES)}")
        if a.get("question") and a["question"] not in ids_q:
            warnings.append(f"{a.get('id')}: question {a['question']} is not in 'questions'")
    for p in d.get("questions") or []:
        if p.get("priority") and p["priority"] not in PRIORITIES:
            warnings.append(f"{p.get('id')}: priority {p['priority']!r} off the scale {'/'.join(PRIORITIES)}")
    for r in d.get("risks") or []:
        if r.get("level") and r["level"] not in RISK_LEVELS:
            warnings.append(f"risk {r.get('risk', '')[:40]!r}: level {r['level']!r} not in {'/'.join(RISK_LEVELS)}")
    for f in d.get("sources") or []:
        if f.get("status") and f["status"] not in SOURCE_STATUS:
            warnings.append(f"source {f.get('source')!r}: status {f['status']!r} not in {'/'.join(SOURCE_STATUS)}")
    for x in warnings:
        print(f"[warning] research.json · {x}", file=sys.stderr)
    return warnings


def compare(current, previous):
    """Which ambiguities and questions are new and which were resolved (by text, not by ID: IDs get renumbered)."""
    if not previous:
        return None

    def index(d, key, field):
        return {_norm(x.get(field)): x for x in d.get(key) or [] if x.get(field)}

    res = {"previous_date": previous.get("date", "")}
    for key, field in (("ambiguities", "what"), ("questions", "question")):
        a, b = index(current, key, field), index(previous, key, field)
        res[key] = {"new": [a[k] for k in a if k not in b], "resolved": [b[k] for k in b if k not in a],
                    "persisting": [a[k] for k in a if k in b]}
    return res


def _progress(av):
    done, total = (av or {}).get("done"), (av or {}).get("total")
    if not isinstance(done, (int, float)) or not total:
        return "—"
    pct = max(0, min(100, 100 * done / total))
    return f'<div class="progress"><span class="b"><span style="width:{pct:.0f}%"></span></span><em>{done:g}/{total:g} · {pct:.0f}%</em></div>'


def _sources(items):
    from _report_styles import e
    if isinstance(items, str):
        items = [items]
    return '<span class="sources-cell">' + " <b>vs.</b> ".join(e(f) for f in items or []) + "</span>" if items else "—"


def _link(url, text=None):
    """Clickable link if there is an http(s) URL; otherwise, the plain text."""
    from _report_styles import e
    text = text or url
    if url and re.match(r"^https?://", str(url)):
        return f'<a href="{e(url)}" target="_blank" rel="noopener">{e(text)}</a>'
    return e(text)


_MAP_N = [0]


def _wrap(text, maxc=24):
    words, lines, current = str(text or "").split(), [], ""
    for p in words:
        if len(current) + len(p) + 1 <= maxc or not current:
            current = f"{current} {p}".strip()
        else:
            lines.append(current)
            current = p
    if current:
        lines.append(current)
    return lines[:3] or [""]


def map_svg(map_):
    """Draws a concept map (nodes + directed edges) as self-contained SVG, in columns by
    level (level = longest path from a root). Works for architecture, flow or modules."""
    from _report_styles import e, SERIES
    nodes = [n for n in map_.get("nodes") or [] if n.get("id")]
    if not nodes:
        return ""
    byid = {n["id"]: n for n in nodes}
    edges = [en for en in map_.get("edges") or [] if en.get("from") in byid and en.get("to") in byid]
    # level by longest path (cycles are cut by the iteration cap)
    level = {n["id"]: 0 for n in nodes}
    for _ in range(len(nodes)):
        changed = False
        for en in edges:
            if level[en["to"]] < level[en["from"]] + 1 <= len(nodes):
                level[en["to"]] = level[en["from"]] + 1
                changed = True
        if not changed:
            break
    cols = {}
    for n in nodes:
        cols.setdefault(level[n["id"]], []).append(n)
    groups = {}
    for n in nodes:
        g = n.get("group") or ""
        if g and g not in groups:
            groups[g] = SERIES[len(groups) % len(SERIES)]
    NW, COLGAP, ROWGAP, LH, PADY = 184, 104, 22, 16, 11
    geo, col_h = {}, {}
    for c, items in cols.items():
        y = 0
        for n in items:
            lines = _wrap(n.get("label") or n["id"])
            h = len(lines) * LH + 2 * PADY + (16 if n.get("note") else 0)
            geo[n["id"]] = {"lines": lines, "h": h, "note": n.get("note"), "group": n.get("group") or "", "col": c, "y0": y}
            y += h + ROWGAP
        col_h[c] = y - ROWGAP if items else 0
    height = max(col_h.values(), default=0) + 20
    for c, items in cols.items():
        off = (height - col_h[c]) / 2
        for n in items:
            g = geo[n["id"]]
            g["x"] = c * (NW + COLGAP) + 10
            g["y"] = g["y0"] + off
    width = (max(cols) + 1) * (NW + COLGAP) - COLGAP + 20 if cols else NW
    _MAP_N[0] += 1
    mid = f"mp{_MAP_N[0]}"
    svg = [f'<svg viewBox="0 0 {width:.0f} {height:.0f}" role="img" aria-label="{e(map_.get("title", "map"))}">',
           f'<defs><marker id="{mid}" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto">'
           f'<path d="M0,0 L7,3 L0,6 Z" fill="currentColor" class="elabel"/></marker></defs>']
    for en in edges:
        a, b = geo[en["from"]], geo[en["to"]]
        back = level[en["to"]] <= level[en["from"]]
        x1, y1 = a["x"] + NW, a["y"] + a["h"] / 2
        x2, y2 = b["x"], b["y"] + b["h"] / 2
        dx = max(40, abs(x2 - x1) / 2)
        svg.append(f'<path class="edge{" back" if back else ""}" marker-end="url(#{mid})" '
                   f'd="M{x1:.0f},{y1:.0f} C{x1 + dx:.0f},{y1:.0f} {x2 - dx:.0f},{y2:.0f} {x2:.0f},{y2:.0f}"/>')
        if en.get("label"):
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2 - 4
            w = len(en["label"]) * 6.3 + 8
            svg.append(f'<rect class="elabel-bg" x="{mx - w / 2:.0f}" y="{my - 11:.0f}" width="{w:.0f}" height="15" rx="4"/>'
                       f'<text class="elabel" x="{mx:.0f}" y="{my:.0f}" text-anchor="middle">{e(en["label"])}</text>')
    for nid, g in geo.items():
        col = groups.get(g["group"], SERIES[0])
        x, y = g["x"], g["y"]
        svg.append(f'<rect class="nbox" x="{x:.0f}" y="{y:.0f}" width="{NW}" height="{g["h"]:.0f}" rx="10"/>'
                   f'<rect x="{x:.0f}" y="{y:.0f}" width="5" height="{g["h"]:.0f}" rx="2.5" fill="{col}"/>')
        ty = y + PADY + 12
        for ln in g["lines"]:
            svg.append(f'<text class="ntext" x="{x + 16:.0f}" y="{ty:.0f}">{e(ln)}</text>')
            ty += LH
        if g["note"]:
            svg.append(f'<text class="nnote" x="{x + 16:.0f}" y="{ty:.0f}">{e(g["note"][:28])}</text>')
    svg.append("</svg>")
    legend_html = ""
    if groups:
        from _report_styles import legend
        legend_html = legend([(g, c) for g, c in groups.items()])
    desc = f'<p class="desc">{e(map_["description"])}</p>' if map_.get("description") else ""
    return f'<div class="map">{desc}<div class="wrap">{"".join(svg)}</div>{legend_html}</div>'


def maps_of(d):
    """The maps the agent sent; if it sent none, builds a modules map from hierarchy/modules."""
    if d.get("maps"):
        return d["maps"]
    root = d.get("project") or "Project"
    nodes, edges = [{"id": "_root", "label": root, "group": "Project"}], []
    seen = set()
    for group in d.get("hierarchy") or []:
        ep = group.get("epic") or {}
        eid = ep.get("id") or ep.get("title")
        if eid and eid not in seen:
            seen.add(eid)
            nodes.append({"id": eid, "label": ep.get("title") or eid, "group": "Epic", "note": ep.get("status")})
            edges.append({"from": "_root", "to": eid})
    if not seen:
        for m in d.get("modules") or []:
            mid = m.get("name")
            if mid and mid not in seen:
                seen.add(mid)
                nodes.append({"id": mid, "label": mid, "group": "Module", "note": m.get("status")})
                edges.append({"from": "_root", "to": mid})
    if len(nodes) < 2:
        return []
    return [{"title": "Modules map", "type": "modules",
             "description": "Built automatically from the surveyed epics/modules.", "nodes": nodes, "edges": edges}]


def build_html(d, changes=None):
    from _report_styles import (e, page, meta, section, kpi_tiles, table, doc_list, two_col, banner, bar_chart,
                                donut_panel, level_badge, _pill, OK, WARNING, CRITICAL, SERIOUS, NEUTRAL, SERIES)
    sources = d.get("sources") or []
    read = sum(1 for f in sources if f.get("status") == "read")
    no_acc = sum(1 for f in sources if f.get("status") == "not_accessible")
    amb = d.get("ambiguities") or []
    contradictions = sum(1 for a in amb if a.get("type") == "Contradiction")
    qs = sorted(d.get("questions") or [], key=lambda p: PRIO_ORDER.get(p.get("priority"), 9))
    urgent = sum(1 for p in qs if p.get("priority") in ("Critical", "High"))
    risks = sorted(d.get("risks") or [], key=lambda r: RISK_ORDER.get(r.get("level"), 9))
    high = sum(1 for r in risks if r.get("level") == "High")
    cov = d.get("coverage") or {}
    total, items_read = cov.get("total_items"), cov.get("read")
    pct_cov = (100 * items_read / total) if isinstance(items_read, (int, float)) and total else None
    hier = d.get("hierarchy") or []
    n_epics = cov.get("epics") if cov.get("epics") is not None else (len(hier) or None)
    n_stories = cov.get("stories") if cov.get("stories") is not None else (sum(len(x.get("stories") or []) for x in hier) or None)
    n_tasks = cov.get("tasks")
    if n_tasks is None and hier:
        n_tasks = sum((h.get("tasks") or 0) if isinstance(h.get("tasks"), int) else len(h.get("tasks") or [])
                      for x in hier for h in x.get("stories") or []) or None
    refs = d.get("references") or []

    tiles = [
        ("Sources read", f"{read}/{len(sources)}" if sources else "—", "warn" if no_acc else ("ok" if sources else ""),
         f"{no_acc} not accessible" if no_acc else "all the connected ones", "search"),
        ("Items read in detail", f"{items_read}" if items_read is not None else "—", "",
         f"of {total} in total" if total else "", "list", {"pct": pct_cov} if pct_cov is not None else None),
    ]
    if n_epics or n_stories or n_tasks:
        detail = " · ".join(x for x in (f"{n_stories} stories" if n_stories else "", f"{n_tasks} tasks" if n_tasks else "") if x)
        tiles.append(("Backlog walked", f"{n_epics or 0} epics", "", detail or "epics, stories and tasks", "grid"))
    tiles += [
        ("Ambiguities", len(amb), "warn" if amb else "ok", f"{contradictions} contradiction(s)", "warn"),
        ("Questions for the team", len(qs), "bad" if any(p.get("priority") == "Critical" for p in qs) else ("warn" if urgent else ""),
         f"{urgent} critical or high", "person"),
        ("Risks for QA", len(risks), "bad" if high else ("warn" if risks else "ok"), f"{high} high", "shield"),
    ]
    body = [kpi_tiles(tiles)]
    if d.get("board"):
        body.append(banner(f'Surveyed from the board: {d["board"]}', "ok"))
    for f in d.get("missing") or []:
        body.append(banner(f, "warn"))
    if d.get("summary"):
        body.append(section("What it is about", f'<div class="cardbody"><p class="lead">{e(d["summary"])}</p></div>'))
    if cov:
        text = f'There are {total} items in total; {items_read} were read in detail.' if total else ""
        if n_epics or n_stories or n_tasks:
            text += f' The board was walked down to {n_epics or 0} epic(s), {n_stories or 0} story(ies) and {n_tasks or 0} task(s), with their comments and links.'
        if cov.get("criteria"):
            text += f' Sampling criteria: {cov["criteria"]}.'
        if text.strip():
            body.append(section("How representative it is", f'<div class="cardbody"><p>{e(text.strip())}</p></div>',
                                "the rest is summarized by counts"))

    for map_ in maps_of(d):
        body.append(section(map_.get("title") or "Concept map", map_svg(map_),
                            "how it is built / how it works"))

    if changes:
        rows = []
        for key, name, field in (("ambiguities", "Ambiguity", "what"), ("questions", "Question", "question")):
            for x in changes[key]["new"]:
                rows.append([_pill("New", WARNING, "+"), name, e(x.get("id", "")), e(x.get(field))])
            for x in changes[key]["resolved"]:
                rows.append([_pill("Resolved", OK, "✓"), name, e(x.get("id", "")), e(x.get(field))])
        sub = f'against the survey of {changes["previous_date"]}' if changes.get("previous_date") else "against the previous survey"
        body.append(section("Changes since the previous survey",
                            table(["Change", "What", "ID", "Detail"], rows) if rows else banner("No changes in ambiguities or questions.", "ok"), sub))

    if sources:
        color = {"ok": OK, "warn": WARNING, "missing": CRITICAL}
        icon = {"ok": "✓", "warn": "!", "missing": "✕"}
        rows = []
        for f in sources:
            txt, tone = SOURCE_STATUS.get(f.get("status"), ("—", "warn"))
            rows.append([f'<b>{e(f.get("source"))}</b>', e(f.get("type", "")), _pill(txt, color[tone], icon[tone]),
                         e(f.get("scope", "")), e(f.get("reason", ""))])
        body.append(section("Sources consulted", table(["Source", "Type", "Status", "What was read", "Reason / what would be needed"], rows)))

    if hier:
        rows = []
        for group in hier:
            ep = group.get("epic") or {}
            ep_cell = _link(ep.get("url"), f'{ep.get("id", "")} {ep.get("title", "")}'.strip() or "—")
            stories = group.get("stories") or []
            if not stories:
                rows.append([f'<b>{ep_cell}</b>', e(ep.get("status", "—")), "—", "", "", "", ""])
            for h in stories:
                tasks = h.get("tasks")
                tasks = len(tasks) if isinstance(tasks, list) else (tasks if tasks is not None else "—")
                h_cell = _link(h.get("url"), f'{h.get("id", "")} {h.get("title", "")}'.strip() or "—")
                links = h.get("links") or []
                links_cell = "<br>".join(_link(l) if isinstance(l, str) else _link(l.get("url"), l.get("title")) for l in links) or "—"
                rows.append([f'<b>{ep_cell}</b>', e(ep.get("status", "—")), h_cell, e(h.get("assignee", "—")),
                             e(tasks), e(h.get("comments", "—")), f'{links_cell}'
                             + (f'<div class="muted" style="margin-top:4px">{e(h.get("note"))}</div>' if h.get("note") else "")])
        body.append(section("Epics, stories and tasks", table(["Epic", "Status", "Story", "Assignee", "Tasks", "Comments", "Links / note"], rows),
                            "what was walked going down the board"))

    if refs:
        rows = [[e(r.get("type", "—")), _link(r.get("url"), r.get("title") or r.get("url")), e(r.get("origin", "—")),
                 _pill("Read", OK, "✓") if r.get("read") else _pill("Pending", WARNING, "◷")] for r in refs]
        body.append(section("Reference links", table(["Type", "Reference", "Comes from", "Read?"], rows),
                            "pages, designs and documents cited in the backlog"))

    if d.get("modules"):
        body.append(section("Product modules", table(["Module", "What it does", "Status", "Progress", "Source"],
                                                     [[f'<b>{e(m.get("name"))}</b>', e(m.get("description")), e(m.get("status", "—")),
                                                       _progress(m.get("progress")), _sources(m.get("source"))] for m in d["modules"]])))
    left = section("Application actors and roles", table(["Role", "What they can do", "Source"],
                                                         [[f'<b>{e(a.get("role"))}</b>', e(a.get("can")), _sources(a.get("source"))]
                                                          for a in d.get("actors") or []]), width=6) if d.get("actors") else ""
    right = section("Key flows", table(["Flow", "Steps", "Items", "Source"],
                                       [[f'<b>{e(f.get("name"))}</b>', e(f.get("steps")), f'<span class="mono">{e(f.get("items", ""))}</span>',
                                         _sources(f.get("source"))] for f in d.get("flows") or []]), width=6) if d.get("flows") else ""
    if left and right:
        body.append(two_col(left, right))
    elif left or right:
        body.append(left or right)
    if d.get("integrations"):
        body.append(section("Integrations with other systems", table(["System", "Purpose", "Type", "Source"],
                                                                    [[f'<b>{e(i.get("system"))}</b>', e(i.get("purpose")), e(i.get("type", "—")),
                                                                      _sources(i.get("source"))] for i in d["integrations"]])))
    left = section("Environments", table(["Environment", "URL", "Purpose", "Source"],
                                         [[f'<b>{e(a.get("name"))}</b>', f'<span class="mono">{e(a.get("url", "—"))}</span>', e(a.get("purpose", "")),
                                           _sources(a.get("source"))] for a in d.get("environments") or []]), width=6) if d.get("environments") else ""
    right = section("Stack and architecture", table(["Layer", "Technology", "Source"],
                                                    [[f'<b>{e(s.get("layer"))}</b>', e(s.get("technology")), _sources(s.get("source"))]
                                                     for s in d.get("stack") or []]), width=6) if d.get("stack") else ""
    if left and right:
        body.append(two_col(left, right))
    elif left or right:
        body.append(left or right)

    bl = d.get("backlog") or {}
    charts = []
    if bl.get("by_status"):
        charts.append(section("Backlog by status", bar_chart([(k, v, SERIES[i % len(SERIES)]) for i, (k, v) in enumerate(bl["by_status"].items())]), width=6))
    if bl.get("bugs_by_severity"):
        sev_color = {"Critical": CRITICAL, "High": SERIOUS, "Medium": WARNING, "Low": NEUTRAL}
        charts.append(section("Open bugs by severity", bar_chart([(k, v, sev_color.get(k, NEUTRAL)) for k, v in bl["bugs_by_severity"].items()]), width=6))
    elif bl.get("by_type"):
        charts.append(section("Backlog by type", bar_chart([(k, v, SERIES[(i + 2) % len(SERIES)]) for i, (k, v) in enumerate(bl["by_type"].items())]), width=6))
    if len(charts) == 2:
        body.append(two_col(*charts))
    elif charts:
        body.append(charts[0])
    sp = bl.get("current_sprint") or {}
    rows = []
    if sp:
        rows.append([f'<b>{e(sp.get("name", "Current sprint"))}</b>', "Current sprint / iteration",
                     e(" → ".join(x for x in (sp.get("start"), sp.get("end")) if x) or "—"),
                     e(f'{sp["items"]} items' if sp.get("items") is not None else ""), "—"])
    for r in bl.get("releases") or []:
        rows.append([f'<b>{e(r.get("name"))}</b>', "Release", e(r.get("date", "—")), e(r.get("status", "")), _sources(r.get("source"))])
    if rows:
        body.append(section("Sprint and upcoming deliveries", table(["Name", "What it is", "Dates", "Status", "Source"], rows)))

    if amb:
        types = [(t, sum(1 for a in amb if a.get("type") == t)) for t in AMBIGUITY_TYPES]
        types = [(t, n) for t, n in types if n]
        colors = {"Contradiction": CRITICAL, "Ambiguity": WARNING, "Gap": SERIOUS, "Outdated": NEUTRAL, "Dependency": SERIES[2]}
        rows = [[f'<span class="id">{e(a.get("id", ""))}</span>', e(a.get("type", "—")), e(a.get("what")), _sources(a.get("sources")),
                 level_badge(a.get("impact")), f'<span class="id">{e(a.get("question", ""))}</span>']
                for a in sorted(amb, key=lambda a: (PRIO_ORDER.get(a.get("impact"), 9), AMBIGUITY_TYPES.index(a["type"]) if a.get("type") in AMBIGUITY_TYPES else 9))]
        panel = section("Ambiguities by type", donut_panel([(n, colors.get(t, NEUTRAL), t) for t, n in types],
                                                           round(100 * contradictions / len(amb)), "contradictions"), width=4) if types else ""
        table_html = section("Ambiguities, contradictions and gaps", table(["ID", "Type", "What", "Sources", "Impact", "Question"], rows),
                             "we do not choose between sources: we ask", width=8 if panel else 12)
        body.append(f'{table_html}{panel}' if panel else table_html)

    if qs:
        body.append(section("Questions for the team", table(["ID", "Question", "To whom", "Priority", "Why", "Related"],
                                                            [[f'<span class="id">{e(p.get("id", ""))}</span>', e(p.get("question")), e(p.get("to_whom", "—")),
                                                              level_badge(p.get("priority")), e(p.get("why", "")),
                                                              f'<span class="mono">{e(p.get("related", ""))}</span>'] for p in qs]),
                            "sorted by priority"))
    if d.get("startup_questions"):
        body.append(section("Getting-started questions", doc_list(d["startup_questions"]), "what every new QA needs and is not documented"))
    if risks:
        body.append(section("Risks for QA", table(["Level", "Risk", "Reason", "Mitigation"],
                                                  [[level_badge(r.get("level")), f'<b>{e(r.get("risk"))}</b>', e(r.get("reason", "")),
                                                    e(r.get("mitigation", ""))] for r in risks])))
    if d.get("team"):
        body.append(section("Team and who to ask", table(["Role", "Who", "Topics", "Source"],
                                                         [[f'<b>{e(x.get("role"))}</b>', e(x.get("name", "—")), e(x.get("topics", "")),
                                                           _sources(x.get("source"))] for x in d["team"]])))
    if d.get("decisions"):
        body.append(section("Recorded decisions", table(["Date", "Decision", "Who", "Source"],
                                                        [[f'<span class="mono">{e(x.get("date", "—"))}</span>', e(x.get("decision")),
                                                          e(x.get("who", "—")), _sources(x.get("source"))]
                                                         for x in sorted(d["decisions"], key=lambda x: x.get("date") or "", reverse=True)])))
    if d.get("current_testing"):
        body.append(section("How it is tested today", table(["What", "Status", "Source"],
                                                            [[e(x.get("what")), e(x.get("status", "—")), _sources(x.get("source"))] for x in d["current_testing"]])))
    if d.get("timeline"):
        body.append(section("Timeline", table(["Date", "Milestone", "Source"],
                                              [[f'<span class="mono">{e(x.get("date"))}</span>', e(x.get("milestone")), _sources(x.get("source"))]
                                               for x in sorted(d["timeline"], key=lambda x: x.get("date") or "")])))
    if d.get("glossary"):
        body.append(section("Glossary", table(["Term", "What it means", "Source"],
                                              [[f'<b>{e(g.get("term"))}</b>', e(g.get("definition")), _sources(g.get("source"))]
                                               for g in sorted(d["glossary"], key=lambda g: _norm(g.get("term")))])))
    if d.get("next_steps"):
        body.append(section("Next steps for newcomers", table(["Step", "With", "Example request"],
                                                              [[e(x.get("step")), f'<b>{e(x.get("agent", "—"))}</b>',
                                                                f'<span class="mono">{e(x.get("request", ""))}</span>'] for x in d["next_steps"]])))

    title = f'Survey of {d.get("project", "")}'.strip()
    html = page(title, "Project research",
                meta([("Project", d.get("key")), ("Date", d.get("date")), ("Depth", d.get("depth")),
                      ("Focus", d.get("focus")), ("Audience", d.get("audience"))]), "".join(body))
    return html.replace("</style>", CSS_RSCH + "</style>", 1)


def build_md(d, changes=None):
    l = [f'# Survey of {d.get("project", "")}', ""]
    for k, v in (("Project", d.get("key")), ("Date", d.get("date")), ("Board", d.get("board")),
                 ("Depth", d.get("depth")), ("Focus", d.get("focus")), ("Audience", d.get("audience"))):
        if v:
            l.append(f"- **{k}:** {v}")
    l.append("")
    for f in d.get("missing") or []:
        l += [f"> {f}", ""]
    if d.get("summary"):
        l += ["## What it is about", "", d["summary"], ""]
    cov = d.get("coverage") or {}
    if cov:
        walked = ""
        if cov.get("epics") or cov.get("stories") or cov.get("tasks"):
            walked = (f' Board walkthrough: {cov.get("epics", 0)} epic(s), {cov.get("stories", 0)} story(ies), '
                      f'{cov.get("tasks", 0)} task(s).')
        l += ["## How representative it is", "",
              f'Items in total: {cov.get("total_items", "—")} · read in detail: {cov.get("read", "—")}.{walked} '
              f'Criteria: {cov.get("criteria", "—")}.', ""]

    def url_or_text(url, text=None):
        text = text or url or ""
        return f"[{text}]({url})" if url and str(url).startswith("http") else text

    def fu(x):
        return " vs. ".join(x) if isinstance(x, list) else (x or "")

    def md_table(title, head, rows):
        if not rows:
            return
        l.extend([f"## {title}", "", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)])
        l.extend("| " + " | ".join(str(c if c is not None else "").replace("|", "/").replace("\n", " ") for c in f) + " |" for f in rows)
        l.append("")

    if changes:
        rows = []
        for key, name, field in (("ambiguities", "Ambiguity", "what"), ("questions", "Question", "question")):
            rows += [["New", name, x.get("id"), x.get(field)] for x in changes[key]["new"]]
            rows += [["Resolved", name, x.get("id"), x.get(field)] for x in changes[key]["resolved"]]
        md_table("Changes since the previous survey", ["Change", "What", "ID", "Detail"], rows or [["No changes", "", "", ""]])
    md_table("Sources consulted", ["Source", "Type", "Status", "What was read", "Reason"],
             [[f.get("source"), f.get("type"), SOURCE_STATUS.get(f.get("status"), ("",))[0], f.get("scope"), f.get("reason")] for f in d.get("sources") or []])
    rows_hier = []
    for group in d.get("hierarchy") or []:
        ep = group.get("epic") or {}
        ep_txt = url_or_text(ep.get("url"), f'{ep.get("id", "")} {ep.get("title", "")}'.strip())
        stories = group.get("stories") or []
        if not stories:
            rows_hier.append([ep_txt, ep.get("status"), "-", "", "", "", ""])
        for h in stories:
            tasks = h.get("tasks")
            tasks = len(tasks) if isinstance(tasks, list) else tasks
            links = h.get("links") or []
            links_txt = "; ".join(l if isinstance(l, str) else (l.get("title") or l.get("url") or "") for l in links)
            rows_hier.append([ep_txt, ep.get("status"), url_or_text(h.get("url"), f'{h.get("id", "")} {h.get("title", "")}'.strip()),
                              h.get("assignee"), tasks, h.get("comments"), (links_txt + (f' — {h.get("note")}' if h.get("note") else "")).strip(" —")])
    md_table("Epics, stories and tasks", ["Epic", "Status", "Story", "Assignee", "Tasks", "Comments", "Links / note"], rows_hier)
    md_table("Reference links", ["Type", "Reference", "Comes from", "Read?"],
             [[r.get("type"), url_or_text(r.get("url"), r.get("title") or r.get("url")), r.get("origin"), "Yes" if r.get("read") else "Pending"]
              for r in d.get("references") or []])

    def av(m):
        a = m.get("progress") or {}
        return f'{a["done"]:g}/{a["total"]:g}' if isinstance(a.get("done"), (int, float)) and a.get("total") else "-"

    md_table("Product modules", ["Module", "What it does", "Status", "Progress", "Source"],
             [[m.get("name"), m.get("description"), m.get("status"), av(m), fu(m.get("source"))] for m in d.get("modules") or []])
    md_table("Application actors and roles", ["Role", "What they can do", "Source"], [[a.get("role"), a.get("can"), fu(a.get("source"))] for a in d.get("actors") or []])
    md_table("Key flows", ["Flow", "Steps", "Items", "Source"],
             [[f.get("name"), f.get("steps"), f.get("items"), fu(f.get("source"))] for f in d.get("flows") or []])
    md_table("Integrations with other systems", ["System", "Purpose", "Type", "Source"],
             [[i.get("system"), i.get("purpose"), i.get("type"), fu(i.get("source"))] for i in d.get("integrations") or []])
    md_table("Environments", ["Environment", "URL", "Purpose", "Source"],
             [[a.get("name"), a.get("url"), a.get("purpose"), fu(a.get("source"))] for a in d.get("environments") or []])
    md_table("Stack and architecture", ["Layer", "Technology", "Source"], [[s.get("layer"), s.get("technology"), fu(s.get("source"))] for s in d.get("stack") or []])
    bl = d.get("backlog") or {}
    md_table("Backlog by status", ["Status", "Items"], list((bl.get("by_status") or {}).items()))
    md_table("Open bugs by severity", ["Severity", "Bugs"], list((bl.get("bugs_by_severity") or {}).items()))
    sp = bl.get("current_sprint") or {}
    deliveries = ([[sp.get("name"), "Current sprint", " -> ".join(x for x in (sp.get("start"), sp.get("end")) if x), sp.get("items"), ""]] if sp else [])
    deliveries += [[r.get("name"), "Release", r.get("date"), r.get("status"), fu(r.get("source"))] for r in bl.get("releases") or []]
    md_table("Sprint and upcoming deliveries", ["Name", "What it is", "Dates", "Status / items", "Source"], deliveries)
    md_table("Ambiguities, contradictions and gaps", ["ID", "Type", "What", "Sources", "Impact", "Question"],
             [[a.get("id"), a.get("type"), a.get("what"), fu(a.get("sources")), a.get("impact"), a.get("question")] for a in d.get("ambiguities") or []])
    md_table("Questions for the team", ["ID", "Question", "To whom", "Priority", "Why", "Related"],
             [[p.get("id"), p.get("question"), p.get("to_whom"), p.get("priority"), p.get("why"), p.get("related")]
              for p in sorted(d.get("questions") or [], key=lambda p: PRIO_ORDER.get(p.get("priority"), 9))])
    if d.get("startup_questions"):
        l += ["## Getting-started questions", ""] + [f"- {p}" for p in d["startup_questions"]] + [""]
    md_table("Risks for QA", ["Level", "Risk", "Reason", "Mitigation"],
             [[r.get("level"), r.get("risk"), r.get("reason"), r.get("mitigation")]
              for r in sorted(d.get("risks") or [], key=lambda r: RISK_ORDER.get(r.get("level"), 9))])
    md_table("Team and who to ask", ["Role", "Who", "Topics", "Source"], [[x.get("role"), x.get("name"), x.get("topics"), fu(x.get("source"))] for x in d.get("team") or []])
    md_table("Recorded decisions", ["Date", "Decision", "Who", "Source"],
             [[x.get("date"), x.get("decision"), x.get("who"), fu(x.get("source"))] for x in d.get("decisions") or []])
    md_table("How it is tested today", ["What", "Status", "Source"], [[x.get("what"), x.get("status"), fu(x.get("source"))] for x in d.get("current_testing") or []])
    md_table("Timeline", ["Date", "Milestone", "Source"],
             [[x.get("date"), x.get("milestone"), fu(x.get("source"))] for x in sorted(d.get("timeline") or [], key=lambda x: x.get("date") or "")])
    md_table("Glossary", ["Term", "What it means", "Source"], [[g.get("term"), g.get("definition"), fu(g.get("source"))] for g in d.get("glossary") or []])
    md_table("Next steps for newcomers", ["Step", "With", "Example request"],
             [[x.get("step"), x.get("agent"), x.get("request")] for x in d.get("next_steps") or []])
    return "\n".join(l)


def build_summary_md(d):
    """Short summary (one page): what the project is, its status and what is most urgent for a new QA."""
    cov = d.get("coverage") or {}
    qs = sorted(d.get("questions") or [], key=lambda p: PRIO_ORDER.get(p.get("priority"), 9))
    amb = d.get("ambiguities") or []
    bl = d.get("backlog") or {}
    l = [f'# {d.get("project", "Project")} — summary', ""]
    if d.get("summary"):
        l += [d["summary"], ""]
    l.append("## In a few lines")
    points = []
    mods = d.get("modules") or []
    if mods:
        points.append(f'**Modules:** {", ".join(m.get("name", "") for m in mods[:6])}' + (" …" if len(mods) > 6 else ""))
    if cov.get("epics") or cov.get("stories"):
        points.append(f'**Backlog walked:** {cov.get("epics", 0)} epics, {cov.get("stories", 0)} stories, {cov.get("tasks", 0)} tasks.')
    sp = bl.get("current_sprint") or {}
    if sp:
        points.append(f'**Current sprint:** {sp.get("name", "")} ({sp.get("end", "no date")}).')
    if bl.get("releases"):
        r = bl["releases"][0]
        points.append(f'**Next delivery:** {r.get("name", "")} ({r.get("date", "no date")}).')
    integ = d.get("integrations") or []
    if integ:
        points.append(f'**Integrations:** {", ".join(i.get("system", "") for i in integ[:5])}.')
    points.append(f'**Open findings:** {len(amb)} ambiguity(ies)/contradiction(s), {len(qs)} question(s) for the team.')
    l += [f"- {p}" for p in points] + [""]
    if qs:
        l += ["## The 3 most urgent questions", ""]
        for p in qs[:3]:
            l.append(f'- **[{p.get("priority", "")}]** {p.get("question", "")}' + (f' — *to {p["to_whom"]}*' if p.get("to_whom") else ""))
        l.append("")
    l += ["---", f'Full report: `research-report.html` · Presentation: `research-presentation.html`'
          + (f' · Board: {d["board"]}' if d.get("board") else "")]
    return "\n".join(l)


def build_presentation(d):
    """Self-contained presentation (one slide per topic; <-/-> to navigate; prints to PDF, one slide per page)."""
    from _report_styles import e
    cov = d.get("coverage") or {}
    amb = d.get("ambiguities") or []
    qs = sorted(d.get("questions") or [], key=lambda p: PRIO_ORDER.get(p.get("priority"), 9))
    risks = sorted(d.get("risks") or [], key=lambda r: RISK_ORDER.get(r.get("level"), 9))
    slides = []

    def ul(items, n=6):
        return "<ul>" + "".join(f"<li>{x}</li>" for x in items[:n]) + "</ul>" if items else '<p class="muted">—</p>'

    # 1. Cover
    meta_bits = " · ".join(x for x in (d.get("key"), d.get("date"), d.get("audience")) if x)
    slides.append(f'<section class="s cover"><span class="eyebrow">Project survey</span>'
                  f'<h1>{e(d.get("project", "Project"))}</h1>'
                  f'<p class="lead">{e(d.get("summary", ""))}</p><p class="metal">{e(meta_bits)}</p>'
                  + (f'<p class="metal">Board: {e(d["board"])}</p>' if d.get("board") else "") + '</section>')
    # 2. At a glance (KPIs)
    kpis = [("Epics", cov.get("epics")), ("Stories", cov.get("stories")), ("Tasks", cov.get("tasks")),
            ("Ambiguities", len(amb)), ("Questions", len(qs)), ("Risks", len(risks))]
    tiles = "".join(f'<div class="k"><div class="n">{e(v if v is not None else "—")}</div><div class="l">{e(t)}</div></div>'
                    for t, v in kpis)
    slides.append(f'<section class="s"><h2>At a glance</h2><div class="kpis">{tiles}</div></section>')
    # 3+. One slide per concept map
    for map_ in maps_of(d):
        slides.append(f'<section class="s"><h2>{e(map_.get("title") or "Concept map")}</h2>{map_svg(map_)}</section>')
    # Modules
    if d.get("modules"):
        items = [f'<b>{e(m.get("name"))}</b> — {e(m.get("status", ""))}'
                 + (f' ({m["progress"]["done"]}/{m["progress"]["total"]})' if (m.get("progress") or {}).get("total") else "")
                 for m in d["modules"]]
        slides.append(f'<section class="s"><h2>Modules</h2>{ul(items, 8)}</section>')
    # Integrations and environments
    left = ul([f'<b>{e(i.get("system"))}</b>: {e(i.get("purpose", ""))}' for i in d.get("integrations") or []])
    right = ul([f'<b>{e(a.get("name"))}</b>: {e(a.get("url", ""))}' for a in d.get("environments") or []])
    if d.get("integrations") or d.get("environments"):
        slides.append(f'<section class="s"><h2>Integrations and environments</h2><div class="two">'
                      f'<div><h3>Integrations</h3>{left}</div><div><h3>Environments</h3>{right}</div></div></section>')
    # Ambiguities
    if amb:
        items = [f'<b>{e(a.get("id"))}</b> ({e(a.get("type", ""))}): {e(a.get("what", ""))}' for a in amb]
        slides.append(f'<section class="s"><h2>Ambiguities and contradictions</h2>{ul(items, 7)}</section>')
    # Questions
    if qs:
        items = [f'<b>[{e(p.get("priority", ""))}]</b> {e(p.get("question", ""))}'
                 + (f' — <i>{e(p["to_whom"])}</i>' if p.get("to_whom") else "") for p in qs]
        slides.append(f'<section class="s"><h2>Questions for the team</h2>{ul(items, 7)}</section>')
    # Risks + next steps
    if risks or d.get("next_steps"):
        r = ul([f'<b>[{e(x.get("level", ""))}]</b> {e(x.get("risk", ""))}' for x in risks])
        n = ul([e(x if isinstance(x, str) else x.get("step", "")) for x in d.get("next_steps") or []])
        slides.append(f'<section class="s"><h2>Risks and next steps</h2><div class="two">'
                      f'<div><h3>Risks for QA</h3>{r}</div><div><h3>Next steps</h3>{n}</div></div></section>')

    total = len(slides)
    body = "\n".join(slides)
    css = """
:root{--bg:#0E0C09;--surface:#1A1712;--tile:#221E17;--border:#2E281F;--ink:#F4EFE6;--muted:#A79F90;--accent:#F9B006}
@media print{@page{size:1280px 720px;margin:0}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,Segoe UI,Roboto,Arial,sans-serif}
.deck{max-width:1280px;margin:0 auto}
.s{min-height:100vh;padding:7vh 8vw;display:flex;flex-direction:column;justify-content:center;gap:14px;border-bottom:1px solid var(--border);page-break-after:always;break-after:page}
.s h1{font-size:46px;margin:.1em 0}.s h2{font-size:30px;margin:0 0 .3em;color:var(--accent)}.s h3{font-size:16px;color:var(--muted);margin:.2em 0}
.s .eyebrow{color:var(--accent);font:600 13px/1 var(--mono,monospace);letter-spacing:.14em;text-transform:uppercase}
.s .lead{font-size:20px;color:var(--ink);max-width:48ch}.s .metal{color:var(--muted);font-size:14px;margin:2px 0}
.cover{background:radial-gradient(1200px 500px at 20% 0%,rgba(249,176,6,.10),transparent)}
.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;max-width:760px}
.k{background:var(--tile);border:1px solid var(--border);border-radius:14px;padding:18px 20px}
.k .n{font-size:40px;font-weight:800;color:var(--accent)}.k .l{color:var(--muted);font-size:13px;text-transform:uppercase;letter-spacing:.08em}
ul{margin:.2em 0;padding-left:1.1em}li{margin:.35em 0}.muted{color:var(--muted)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:28px}
.map{padding:0}.map .wrap{overflow-x:auto}.map svg{max-width:100%;height:auto}
.map .nbox{fill:var(--tile);stroke:var(--border)}.map .ntext{fill:var(--ink);font:600 12.5px sans-serif}
.map .nnote{fill:var(--muted);font:11px monospace}.map .edge{fill:none;stroke:var(--muted);stroke-width:1.6;opacity:.7}
.map .edge.back{stroke-dasharray:4 4}.map .elabel{fill:var(--muted);font:11px monospace}.map .elabel-bg{fill:var(--surface)}
.map .legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:10px;color:var(--muted);font-size:12px}
.map .legend i{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:5px;vertical-align:-1px}
.nav{position:fixed;right:14px;bottom:12px;background:var(--surface);border:1px solid var(--border);border-radius:999px;padding:6px 12px;color:var(--muted);font:12px monospace;z-index:9}
@media print{.nav{display:none}.s{min-height:0;height:720px}}
"""
    js = ("(function(){var s=[].slice.call(document.querySelectorAll('.s')),c=document.querySelector('.nav b');"
          "function upd(){var i=0,y=window.scrollY+innerHeight/2;s.forEach(function(el,k){if(el.offsetTop<=y)i=k;});"
          "if(c)c.textContent=(i+1);}window.addEventListener('scroll',upd);"
          "document.addEventListener('keydown',function(ev){var i=s.findIndex(function(el){return el.getBoundingClientRect().top>=-2;});"
          "if(ev.key==='ArrowRight'||ev.key===' '||ev.key==='PageDown'){ev.preventDefault();(s[Math.min(i+1,s.length-1)]||s[0]).scrollIntoView({behavior:'smooth'});}"
          "if(ev.key==='ArrowLeft'||ev.key==='PageUp'){ev.preventDefault();(s[Math.max((i<0?s.length:i)-1,0)]).scrollIntoView({behavior:'smooth'});}});upd();})();")
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="dark">'
            f'<title>{e(d.get("project", "Project"))} — presentation</title><style>{css}</style></head>'
            f'<body><div class="deck">{body}</div><div class="nav"><b>1</b> / {total} · ←/→ · print to PDF</div>'
            f'<script>{js}</script></body></html>\n')


def previous(folder):
    """The most recent survey saved in history/ (or None)."""
    hist = Path(folder) / "history"
    if not hist.is_dir():
        return None
    for sub in sorted((p for p in hist.iterdir() if p.is_dir()), reverse=True):
        file = sub / "research.json"
        if file.exists():
            try:
                return json.loads(file.read_text(encoding="utf-8"))
            except ValueError:
                continue
    return None


def save_history(folder, files, maximum=MAX_HISTORY):
    """Copies this survey to history/<date-time>/ and keeps the last `maximum`."""
    hist = Path(folder) / "history"
    target = hist / datetime.now().strftime("%Y-%m-%d-%H%M%S")
    target.mkdir(parents=True, exist_ok=True)
    for a in files:
        if Path(a).exists():
            shutil.copy2(a, target / Path(a).name)
    for old in sorted((p for p in hist.iterdir() if p.is_dir()), reverse=True)[maximum:]:
        shutil.rmtree(old, ignore_errors=True)
    return target


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Report of a project survey (project-researcher agent)")
    ap.add_argument("research_json")
    ap.add_argument("--output", help="output folder (by default, the JSON's folder)")
    ap.add_argument("--no-history", action="store_true", help="does not save the copy in history/ nor compare")
    a = ap.parse_args(argv)
    source = Path(a.research_json)
    d = json.loads(source.read_text(encoding="utf-8"))
    if not d.get("project"):
        ap.error('the JSON needs "project"')
    validate(d)
    folder = Path(a.output) if a.output else source.resolve().parent
    folder.mkdir(parents=True, exist_ok=True)
    changes = None if a.no_history else compare(d, previous(folder))
    html = folder / "research-report.html"
    html.write_text(build_html(d, changes), encoding="utf-8")
    md = folder / "research-report.md"
    md.write_text(build_md(d, changes), encoding="utf-8")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "format_tables.py"), str(md)], capture_output=True, text=True)
    summary = folder / "summary.md"
    summary.write_text(build_summary_md(d), encoding="utf-8")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "format_tables.py"), str(summary)], capture_output=True, text=True)
    presentation = folder / "research-presentation.html"
    presentation.write_text(build_presentation(d), encoding="utf-8")
    if not a.no_history:
        save_history(folder, [source, html, md, summary, presentation])
    print(f"Survey: {html}")
    print(f"  short summary: {summary}")
    print(f"  presentation (prints to PDF): {presentation}")
    print(f"  full Markdown: {md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
