#!/usr/bin/env python3
"""
Generates a Test Plan in HTML (dashboard, dark mode) from a JSON.

Usage:
    python scripts/generate_plan.py <plan.json> <output.html>

Input JSON:
{
  "title": "Test plan — Account signup",
  "story": "US-001",
  "date": "2026-06-29",
  "version": "1.0",
  "objectives": ["...", "..."],
  "scope": { "includes": ["..."], "excludes": ["..."] },
  "approach": "Text of the approach, or several lines.",
  "test_types": ["Functional", "E2E", "API", "Regression", "Exploratory"],
  "risks": [ {"description": "...", "level": "High", "mitigation": "..."} ],
  "environment_data": ["...", "..."],
  "entry_criteria": ["...", "..."],
  "exit_criteria": ["...", "..."],
  "assumptions": ["...", "..."],
  "po_questions": ["...", "..."]
}

Risk levels: High | Medium | Low
The HTML is self-contained (inline CSS and SVG), it does not use the internet.
"""
import sys
import json

from _report_styles import (e, page, meta, section, section_group, kpi_tiles, bar_chart,
                            doc_list, two_col, table, level_badge, LEVEL_COLOR)

LEVELS = ["High", "Medium", "Low"]


def _scope_card(title, tone, items):
    body = ("".join(f'<li>{e(it)}</li>' for it in items)
            if items else '<li class="muted">—</li>')
    return (f'<div class="card"><div class="cardbody">'
            f'<div class="subhead {tone}">{e(title)}</div>'
            f'<ul class="doclist">{body}</ul></div></div>')


def build_html(data):
    objectives = data.get("objectives", []) or []
    scope = data.get("scope", {}) or {}
    includes = scope.get("includes", []) or []
    excludes = scope.get("excludes", []) or []
    approach = data.get("approach", "") or ""
    types = data.get("test_types", []) or []
    risks = data.get("risks", []) or []
    env_data = data.get("environment_data", []) or []
    c_entry = data.get("entry_criteria", []) or []
    c_exit = data.get("exit_criteria", []) or []
    assumptions = data.get("assumptions", []) or []
    questions = data.get("po_questions", []) or []

    open_items = len(assumptions) + len(questions)
    kpis = kpi_tiles([
        ("Objectives", len(objectives), ""),
        ("Test types", len(types), ""),
        ("Risks", len(risks), "warn" if risks else ""),
        ("Assumptions / questions", open_items, "warn" if open_items else ""),
    ])

    body = [kpis]

    # Objectives
    body.append(section("Objectives", doc_list(objectives)))

    # Scope (two columns)
    body.append(section_group("Scope", two_col(_scope_card("In scope", "ok", includes),
                                               _scope_card("Out of scope", "bad", excludes))))

    # Approach
    if approach:
        if isinstance(approach, list):
            body.append(section("Approach", doc_list(approach)))
        else:
            body.append(section("Approach", f'<div class="cardbody"><p>{e(approach)}</p></div>'))

    # Test types (chips)
    if types:
        chips = "".join(f'<span class="chip">{e(t)}</span>' for t in types)
        body.append(section("Test types",
                            f'<div class="cardbody"><div class="meta" style="margin-top:0">{chips}</div></div>'))

    # Risks: bars by level + table
    if risks:
        cnt = {n: sum(1 for r in risks if (r.get("level") or "").strip() == n) for n in LEVELS}
        bars = bar_chart([(n, cnt[n], LEVEL_COLOR[n]) for n in LEVELS])
        rows = [[level_badge(r.get("level")), e(r.get("description")),
                 e(r.get("mitigation") or "—")] for r in risks]
        tbl = table(["Level", "Risk", "Mitigation"], rows)
        body.append(section("Risks", bars + tbl))

    # Data and environment
    if env_data:
        body.append(section("Data and environment", doc_list(env_data)))

    # Entry / exit criteria (two columns)
    if c_entry or c_exit:
        body.append(section_group("Criteria", two_col(_scope_card("Entry", "ok", c_entry),
                                                      _scope_card("Exit", "ok", c_exit))))

    # Assumptions and questions for the PO
    if assumptions or questions:
        parts = ""
        if assumptions:
            parts += ('<div class="cardbody"><div class="subhead">Assumptions</div>'
                      '<ul class="doclist">' + "".join(f'<li>{e(s)}</li>' for s in assumptions) + '</ul></div>')
        if questions:
            parts += ('<div class="cardbody"><div class="subhead warn">Questions for the PO</div>'
                      '<ul class="doclist">' + "".join(f'<li>{e(q)}</li>' for q in questions) + '</ul></div>')
        body.append(section("Assumptions and questions", parts))

    meta_html = meta([("Story", data.get("story")),
                      ("Date", data.get("date")),
                      ("Version", data.get("version"))])
    title = data.get("title") or "Test plan"
    return page(title, "Test plan", meta_html, "".join(body))


def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/generate_plan.py <plan.json> <output.html>")
        sys.exit(1)
    source, target = sys.argv[1], sys.argv[2]
    if not target.lower().endswith(".html"):
        print("The output must end in .html")
        sys.exit(1)
    with open(source, encoding="utf-8") as f:
        data = json.load(f)
    with open(target, "w", encoding="utf-8") as f:
        f.write(build_html(data))
    print(f"OK: {target}")


if __name__ == "__main__":
    main()
