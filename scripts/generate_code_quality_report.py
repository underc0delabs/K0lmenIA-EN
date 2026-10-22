#!/usr/bin/env python3
"""
HTML report (dark mode) of the static code quality analysis (code-quality-analyst agent).

Usage (from the repo root):
    python scripts/generate_code_quality_report.py <analysis.json> <output.html>

The survey is done by `tools/quality/code_quality.py` (`npm run code-quality`); the agent triages it
(confirms each candidate by reading the code, discards false positives, prioritizes) and writes analysis.json.

analysis.json schema (everything optional except "title"):
{
  "title": "Code quality — my-app", "generated": "2026-10-22T12:00:00",
  "project": {"path": "C:/projects/my-app", "repo": "my-company/my-app", "branch": "main", "commit": "a1b2c3d"},
  "scanners": ["heuristics (built-in)", "duplication (built-in)", "lizard", "eslint"],
  "verdict": "Maintainable, with 3 performance hotspots", "verdict_tone": "warn", "summary": "...",
  "metrics": {"files": 120, "loc": 18000, "duplication_pct": 4.2, "avg_complexity": 3.1, "max_complexity": 42,
              "complex_functions": 12, "large_files": 5, "markers": 37, "linter_issues": 210},
  "languages": [{"language": "TypeScript", "files": 80, "loc": 12000}],
  "findings": [{"id": "CQ-01", "severity": "High", "category": "Performance", "rule": "query-in-loop",
                 "file": "src/orders.ts", "line": 42, "text": "...", "impact": "...", "recommendation": "..."}],
  "discarded": [{"rule": "sync-io", "file": "scripts/build.js", "reason": "build script, not a request path"}],
  "hotspots": [{"file": "src/orders.ts", "findings": 7, "complexity": 38, "loc": 900, "why": "..."}],
  "duplicates": [{"lines": 24, "locations": ["src/a.ts:10", "src/b.ts:55"]}],
  "recommendations": [{"priority": "High", "action": "...", "reason": "..."}],
  "next_steps": ["..."], "missing_info": [{"id": "MI-01", "what_is_missing": "...", "question": "..."}]
}
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _report_styles import (page, meta, section, kpi_tiles, banner, table, doc_list, bar_chart,  # noqa: E402
                              level_badge, missing_info, e, SERIES)

SEV_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
TONE = {"ok": "ok", "warn": "warn", "bad": "bad"}


def _num(v):
    return "—" if v is None else v


def generate(analysis_json, output):
    d = json.loads(Path(analysis_json).read_text(encoding="utf-8"))
    proj = d.get("project") or {}
    m = d.get("metrics") or {}
    findings = sorted(d.get("findings") or [], key=lambda x: SEV_ORDER.get(x.get("severity"), 9))
    high = sum(1 for h in findings if h.get("severity") in ("Critical", "High"))
    dup = m.get("duplication_pct")

    kpis = [("Findings", len(findings), "bad" if high else ("warn" if findings else "ok"), f"{high} critical or high", "bug"),
            ("Duplicated code", f"{dup}%" if dup is not None else "—",
             "" if dup is None else ("bad" if dup > 10 else ("warn" if dup > 5 else "ok")), "of the lines of code"),
            ("Complex functions", _num(m.get("complex_functions")), "warn" if m.get("complex_functions") else "",
             f"average {m['avg_complexity']}, max {m.get('max_complexity')}" if m.get("avg_complexity") is not None else "lizard not run"),
            ("Lines of code", _num(m.get("loc")), "", f"{_num(m.get('files'))} files")]

    body = ""
    if d.get("verdict"):
        body += banner(d["verdict"], TONE.get(d.get("verdict_tone"), "ok"))
    body += section("Summary", kpi_tiles(kpis) + (f'<div class="cardbody"><p>{e(d["summary"])}</p></div>' if d.get("summary") else ""))

    metric_rows = [[e(k), e(v)] for k, v in (
        ("Files analyzed", m.get("files")), ("Lines of code", m.get("loc")), ("Duplicated code (%)", dup),
        ("Average cyclomatic complexity", m.get("avg_complexity")), ("Maximum complexity", m.get("max_complexity")),
        ("Functions over the complexity/length limit", m.get("complex_functions")), ("Large files (> 500 lines)", m.get("large_files")),
        ("TODO / FIXME / HACK markers", m.get("markers")), ("Linter issues", m.get("linter_issues"))) if v is not None]
    if metric_rows:
        body += section("Metrics", table(["Metric", "Value"], metric_rows), width=6)
    langs = d.get("languages") or []
    if langs:
        body += section("Lines of code by language", bar_chart([(x.get("language", "?"), x.get("loc", 0), SERIES[i % len(SERIES)])
                                                                for i, x in enumerate(sorted(langs, key=lambda x: -x.get("loc", 0)))]), width=6)

    if findings:
        by_cat = {}
        for h in findings:
            by_cat[h.get("category", "Other")] = by_cat.get(h.get("category", "Other"), 0) + 1
        rows = [[f'<span class="id">{e(h.get("id", ""))}</span>', level_badge(h.get("severity")), e(h.get("category", "")),
                 f'{e(h.get("file", ""))}:{e(h.get("line", ""))}', e(h.get("text", "")), e(h.get("impact", "")), e(h.get("recommendation", ""))]
                for h in findings]
        body += section("Confirmed findings", table(["ID", "Severity", "Category", "Location", "What happens", "Impact", "Recommendation"], rows),
                        f"{len(findings)} in total", width=8)
        body += section("By category", bar_chart([(a, n, SERIES[i % len(SERIES)]) for i, (a, n) in
                                                  enumerate(sorted(by_cat.items(), key=lambda x: -x[1]))]), width=4)
    else:
        body += section("Confirmed findings", banner("No confirmed findings.", "ok"))

    if d.get("hotspots"):
        body += section("Hotspots (where to start)", table(["File", "Findings", "Max complexity", "Lines", "Why"],
                        [[e(h.get("file", "")), e(_num(h.get("findings"))), e(_num(h.get("complexity"))), e(_num(h.get("loc"))), e(h.get("why", ""))]
                         for h in d["hotspots"]]))
    if d.get("duplicates"):
        body += section("Duplicated blocks", table(["Lines", "Where"],
                        [[e(x.get("lines", "")), e(" · ".join(str(loc) for loc in x.get("locations") or []))] for x in d["duplicates"]]),
                        "consider extracting a shared function")
    if d.get("discarded"):
        body += section("Discarded (false positives)", table(["Rule", "Location", "Why it was discarded"],
                        [[e(x.get("rule", "")), e(x.get("file", "")), e(x.get("reason", ""))] for x in d["discarded"]]))
    if d.get("recommendations"):
        body += section("Recommendations", table(["Priority", "Action", "Why"],
                        [[level_badge(x.get("priority", "Medium")), e(x.get("action", "")), e(x.get("reason", ""))] for x in d["recommendations"]]))
    if d.get("next_steps"):
        body += section("Next steps", doc_list(d["next_steps"]))
    body += missing_info(d.get("missing_info"))

    source = proj.get("repo") and f'{proj.get("repo")}@{proj.get("branch") or "default"}' + (f' ({proj["commit"]})' if proj.get("commit") else "")
    html = page(d.get("title") or "Code quality", "Static analysis · best practices, maintainability and performance",
                meta([("Generated", d.get("generated")), ("Repository", source or None), ("Path", proj.get("path")),
                      ("Scanners", ", ".join(d.get("scanners") or []) or None)]), body)
    Path(output).write_text(html, encoding="utf-8")
    return output


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="HTML report of the static code quality analysis.")
    ap.add_argument("analysis_json")
    ap.add_argument("output")
    args = ap.parse_args()
    print(generate(args.analysis_json, args.output))


if __name__ == "__main__":
    main()
