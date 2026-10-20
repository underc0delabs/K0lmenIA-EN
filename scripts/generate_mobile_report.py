#!/usr/bin/env python3
"""
HTML report (dark mode) of the mobile app tester (mobile-tester agent).

Usage (from the repo root):
    python scripts/generate_mobile_report.py <analysis.json> <output.html>

There is no binary that generates the data: the agent runs the tests with Appium (MCP) and writes everything to
analysis.json.

Schema of analysis.json (everything optional except "title"):
{
  "title": "App — US-010", "story": "US-010", "environment": "QA", "generated": "2026-10-19T12:00:00",
  "app": {"name": "MyApp", "version": "4.1.0", "platform": "Android", "type": "Native",
          "os": "Android 14", "device": "Pixel 7 (emulator)"},
  "verdict": "The app works; 1 high finding when denying permissions", "verdict_tone": "warn",
  "summary": "...",
  "tests": [{"id": "TC-001", "area": "Login", "case": "Sign in with valid credentials", "device": "Pixel 7 / Android 14",
             "result": "Passed|Failed|Blocked|Pending|N/A", "expected": "...", "actual": "...",
             "evidence": "screenshots/tc-001.png"}],
  "compatibility": [{"device": "iPhone SE / iOS 16 / large font", "result": "Failed", "detail": "truncated text"}],
  "findings": [{"id": "H-01", "severity": "High", "area": "Permissions", "text": "...",
                "impact": "...", "how_to_reproduce": "...", "recommendation": "..."}],
  "recommendations": [{"priority": "High", "action": "...", "reason": "..."}],
  "next_steps": ["..."],
  "missing_info": [{"id": "MI-01", "what_is_missing": "...", "question": "..."}]
}
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _report_styles import (page, meta, section, kpi_tiles, banner, table, doc_list, bar_chart,  # noqa: E402
                            level_badge, status_pill, missing_info, thumbnail, resolve_evidence, e, SERIES)

SEV_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
RESULT_ORDER = {"Failed": 0, "Blocked": 1, "Pending": 2, "Passed": 3, "N/A": 4}
TONE = {"ok": "ok", "warn": "warn", "bad": "bad"}


def generate(analysis_json, output):
    d = json.loads(Path(analysis_json).read_text(encoding="utf-8"))
    base = Path(output).resolve().parent
    app = d.get("app") or {}

    findings = sorted(d.get("findings") or [], key=lambda x: SEV_ORDER.get(x.get("severity"), 9))
    critical = sum(1 for h in findings if h.get("severity") in ("Critical", "High"))
    tests = d.get("tests") or []
    failed = sum(1 for p in tests if p.get("result") == "Failed")
    passed = sum(1 for p in tests if p.get("result") == "Passed")
    compat = d.get("compatibility") or []
    compat_bad = sum(1 for cp in compat if cp.get("result") == "Failed")

    kpis = [("Tests", len(tests), "bad" if failed else ("ok" if tests else ""),
             f"{passed} passed, {failed} failed", "list"),
            ("Findings", len(findings), "bad" if critical else ("warn" if findings else "ok"), f"{critical} critical or high", "bug")]
    if compat:
        kpis.append(("Compatibility", "With failures" if compat_bad else "OK", "bad" if compat_bad else "ok", f"{len(compat)} device(s)/OS", "shield"))

    body = ""
    if d.get("verdict"):
        body += banner(d["verdict"], TONE.get(d.get("verdict_tone"), "ok"))
    body += section("Summary", kpi_tiles(kpis) + (f'<div class="cardbody"><p>{e(d["summary"])}</p></div>' if d.get("summary") else ""))

    if findings:
        by_area = {}
        for h in findings:
            by_area[h.get("area", "Other")] = by_area.get(h.get("area", "Other"), 0) + 1
        rows = [[f'<span class="id">{e(h.get("id", ""))}</span>', level_badge(h.get("severity")), e(h.get("area", "")),
                 e(h.get("text", "")), e(h.get("impact", "")), e(h.get("recommendation", ""))] for h in findings]
        body += section("Findings", table(["ID", "Severity", "Area", "What happens", "Impact", "Recommendation"], rows), f"{len(findings)} in total", width=8)
        body += section("Findings by area", bar_chart([(a, n, SERIES[i % len(SERIES)]) for i, (a, n) in enumerate(sorted(by_area.items(), key=lambda x: -x[1]))]), width=4)
        detailed = [h for h in findings if h.get("how_to_reproduce")]
        if detailed:
            body += section("How to reproduce", table(["ID", "Finding", "Steps"],
                            [[f'<span class="id">{e(h.get("id"))}</span>', e(h.get("text", "")), e(h.get("how_to_reproduce"))] for h in detailed]))
    else:
        body += section("Findings", banner("No findings.", "ok"))

    if tests:
        rows = []
        for p in sorted(tests, key=lambda p: RESULT_ORDER.get(p.get("result"), 5)):
            ev = ""
            if p.get("evidence"):
                path, exists = resolve_evidence(p["evidence"], base)
                ev = thumbnail(path, p.get("case", ""), exists=exists)
            rows.append([f'<span class="id">{e(p.get("id", ""))}</span>', e(p.get("area", "")), e(p.get("case", "")), e(p.get("device", "")),
                         status_pill(p.get("result")), e(p.get("expected", "")), e(p.get("actual", "")), ev])
        body += section("Tests run", table(["ID", "Area", "Case", "Device", "Result", "Expected", "Actual", "Evidence"], rows))

    if compat:
        rows = [[e(cp.get("device", "")), status_pill(cp.get("result")), e(cp.get("detail", ""))] for cp in compat]
        body += section("Compatibility (devices, OS and densities)", table(["Device / OS", "Result", "Detail"], rows))

    if d.get("recommendations"):
        body += section("Recommendations", table(["Priority", "Action", "Why"],
                        [[level_badge(x.get("priority", "Medium")), e(x.get("action", "")), e(x.get("reason", ""))] for x in d["recommendations"]]))
    if d.get("next_steps"):
        body += section("Next steps", doc_list(d["next_steps"]))
    body += missing_info(d.get("missing_info"))

    html = page(d.get("title") or "Mobile application", "Mobile applications · Android / iOS",
                meta([("Generated", d.get("generated")), ("Story", d.get("story")), ("Environment", d.get("environment")),
                      ("App", f'{app.get("name", "—")} {app.get("version", "")}'.strip() if app else None),
                      ("Platform", f'{app.get("platform", "")} {app.get("type", "")}'.strip() or None),
                      ("OS / device", f'{app.get("os", "")} · {app.get("device", "")}'.strip(" ·") or None)]), body)
    Path(output).write_text(html, encoding="utf-8")
    return output


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="HTML report of the mobile app tester.")
    ap.add_argument("analysis_json")
    ap.add_argument("output")
    args = ap.parse_args()
    print(generate(args.analysis_json, args.output))


if __name__ == "__main__":
    main()
