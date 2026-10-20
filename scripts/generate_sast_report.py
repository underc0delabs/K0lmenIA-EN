#!/usr/bin/env python3
"""
HTML report (dark mode) of the static security analysis and secrets (secure-code-analyst agent).

Usage (from the repo root):
    python scripts/generate_sast_report.py <analysis.json> <output.html>

The survey is done by `tools/security/sast.py` (`npm run sast`); the agent triages it (discards
false positives, prioritizes) and writes analysis.json. Secrets are referenced redacted (file:line),
never with the full value.

analysis.json schema (everything optional except "title"):
{
  "title": "SAST — my-app", "project": {"path": "C:/projects/my-app"}, "generated": "2026-10-19T12:00:00",
  "scanners": ["secrets (built-in)", "semgrep"],
  "verdict": "1 exposed secret and 3 injection findings", "verdict_tone": "bad", "summary": "...",
  "findings": [{"id": "F-01", "severity": "High", "category": "SQL injection", "file": "src/db.js",
                 "line": 42, "text": "...", "how_to_reproduce": "...", "recommendation": "..."}],
  "secrets": [{"type": "AWS access key", "file": ".env", "line": 3, "severity": "High", "status": "confirmed"}],
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


def generate(analysis_json, output):
    d = json.loads(Path(analysis_json).read_text(encoding="utf-8"))
    proj = d.get("project") or {}
    findings = sorted(d.get("findings") or [], key=lambda x: SEV_ORDER.get(x.get("severity"), 9))
    crit = sum(1 for h in findings if h.get("severity") in ("Critical", "High"))
    secrets = d.get("secrets") or []

    kpis = [("Exposed secrets", len(secrets), "bad" if secrets else "ok", "credentials in the code", "shield"),
            ("SAST findings", len(findings), "bad" if crit else ("warn" if findings else "ok"), f"{crit} critical or high", "bug")]

    body = ""
    if d.get("verdict"):
        body += banner(d["verdict"], TONE.get(d.get("verdict_tone"), "ok"))
    if secrets:
        body += banner("There are secrets in the code: rotate the exposed credentials and remove them from the repository (git history included).", "bad")
    body += section("Summary", kpi_tiles(kpis) + (f'<div class="cardbody"><p>{e(d["summary"])}</p></div>' if d.get("summary") else ""))

    if secrets:
        rows = [[level_badge(s.get("severity", "High")), e(s.get("type", "")), e(s.get("file", "")), e(s.get("line", "")), e(s.get("status", ""))] for s in secrets]
        body += section("Secrets found", table(["Severity", "Type", "File", "Line", "Status"], rows),
                          "the value is redacted; confirm and rotate")
    else:
        body += section("Secrets found", banner("No secrets detected.", "ok"))

    if findings:
        by_cat = {}
        for h in findings:
            by_cat[h.get("category", "Other")] = by_cat.get(h.get("category", "Other"), 0) + 1
        rows = [[f'<span class="id">{e(h.get("id", ""))}</span>', level_badge(h.get("severity")), e(h.get("category", "")),
                  f'{e(h.get("file", ""))}:{e(h.get("line", ""))}', e(h.get("text", "")), e(h.get("recommendation", ""))] for h in findings]
        body += section("Code findings (SAST)", table(["ID", "Severity", "Category", "Location", "What happens", "Recommendation"], rows), f"{len(findings)} in total", width=8)
        body += section("By category", bar_chart([(a, n, SERIES[i % len(SERIES)]) for i, (a, n) in enumerate(sorted(by_cat.items(), key=lambda x: -x[1]))]), width=4)
        detailed = [h for h in findings if h.get("how_to_reproduce")]
        if detailed:
            body += section("How to reproduce", table(["ID", "Finding", "Steps"],
                              [[f'<span class="id">{e(h.get("id"))}</span>', e(h.get("text", "")), e(h.get("how_to_reproduce"))] for h in detailed]))
    else:
        body += section("Code findings (SAST)", banner("No SAST findings.", "ok"))

    if d.get("recommendations"):
        body += section("Recommendations", table(["Priority", "Action", "Why"],
                          [[level_badge(x.get("priority", "Medium")), e(x.get("action", "")), e(x.get("reason", ""))] for x in d["recommendations"]]))
    if d.get("next_steps"):
        body += section("Next steps", doc_list(d["next_steps"]))
    body += missing_info(d.get("missing_info"))

    html = page(d.get("title") or "Static security analysis (SAST)", "Security · static code (SAST) and secrets",
                meta([("Generated", d.get("generated")), ("Project", proj.get("path")),
                      ("Scanners", ", ".join(d.get("scanners") or []) or None)]), body)
    Path(output).write_text(html, encoding="utf-8")
    return output


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="HTML report of the static security analysis (SAST) and secrets.")
    ap.add_argument("analysis_json")
    ap.add_argument("output")
    args = ap.parse_args()
    print(generate(args.analysis_json, args.output))


if __name__ == "__main__":
    main()
