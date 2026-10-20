#!/usr/bin/env python3
"""
HTML report (dark mode) of the dependency analysis / SCA (dependency-analyst agent).

Usage (from the repo root):
    python scripts/generate_dependencies_report.py <analysis.json> <output.html>

The survey is done by `tools/security/dependencies.py` (`npm run dependencies`); the agent triages it
and writes analysis.json.

analysis.json schema (everything optional except "title"):
{
  "title": "SCA — my-app", "project": {"path": "C:/projects/my-app", "ecosystems": ["Node", "Python"]},
  "generated": "2026-10-19T12:00:00", "scanners": ["npm audit", "pip-audit"],
  "verdict": "2 critical vulnerabilities with a fix available", "verdict_tone": "bad", "summary": "...",
  "vulnerabilities": [{"package": "lodash 4.17.4", "severity": "Critical", "id": "CVE-2021-23337",
                        "ecosystem": "Node", "fix": true, "recommendation": "upgrade to 4.17.21"}],
  "licenses": [{"package": "pkg", "license": "GPL-3.0", "risk": "review compatibility"}],
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
                              level_badge, status_pill, missing_info, e, SERIES)

SEV_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
TONE = {"ok": "ok", "warn": "warn", "bad": "bad"}


def generate(analysis_json, output):
    d = json.loads(Path(analysis_json).read_text(encoding="utf-8"))
    proj = d.get("project") or {}
    vulns = sorted(d.get("vulnerabilities") or [], key=lambda x: SEV_ORDER.get(x.get("severity"), 9))
    crit = sum(1 for v in vulns if v.get("severity") in ("Critical", "High"))
    with_fix = sum(1 for v in vulns if v.get("fix"))
    lic = d.get("licenses") or []

    kpis = [("Vulnerabilities", len(vulns), "bad" if crit else ("warn" if vulns else "ok"), f"{crit} critical or high", "shield"),
            ("Fix available", with_fix, "ok" if with_fix else "", "upgrading resolves it", "load")]
    if lic:
        kpis.append(("Licenses to review", len(lic), "warn" if lic else "ok", "compatibility", "list"))

    body = ""
    if d.get("verdict"):
        body += banner(d["verdict"], TONE.get(d.get("verdict_tone"), "ok"))
    body += section("Summary", kpi_tiles(kpis) + (f'<div class="cardbody"><p>{e(d["summary"])}</p></div>' if d.get("summary") else ""))

    if vulns:
        by_eco = {}
        for v in vulns:
            by_eco[v.get("ecosystem", "?")] = by_eco.get(v.get("ecosystem", "?"), 0) + 1
        rows = [[level_badge(v.get("severity")), e(v.get("package", "")), e(v.get("id", "")), e(v.get("ecosystem", "")),
                  status_pill("Passed") if v.get("fix") else "—", e(v.get("recommendation", ""))] for v in vulns]
        body += section("Vulnerabilities (CVE)", table(["Severity", "Package", "ID", "Ecosystem", "Fix?", "Recommendation"], rows), f"{len(vulns)} in total", width=8)
        body += section("By ecosystem", bar_chart([(a, n, SERIES[i % len(SERIES)]) for i, (a, n) in enumerate(sorted(by_eco.items(), key=lambda x: -x[1]))]), width=4)
    else:
        body += section("Vulnerabilities (CVE)", banner("No known vulnerabilities in the scanners that were run.", "ok"))

    if lic:
        body += section("Licenses to review", table(["Package", "License", "Risk"],
                          [[e(x.get("package", "")), e(x.get("license", "")), e(x.get("risk", ""))] for x in lic]))

    if d.get("recommendations"):
        body += section("Recommendations", table(["Priority", "Action", "Why"],
                          [[level_badge(x.get("priority", "Medium")), e(x.get("action", "")), e(x.get("reason", ""))] for x in d["recommendations"]]))
    if d.get("next_steps"):
        body += section("Next steps", doc_list(d["next_steps"]))
    body += missing_info(d.get("missing_info"))

    html = page(d.get("title") or "Dependency analysis (SCA)", "Security · dependencies (SCA)",
                meta([("Generated", d.get("generated")), ("Project", proj.get("path")),
                      ("Ecosystems", ", ".join(proj.get("ecosystems") or []) or None),
                      ("Scanners", ", ".join(d.get("scanners") or []) or None)]), body)
    Path(output).write_text(html, encoding="utf-8")
    return output


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="HTML report of the dependency analysis (SCA).")
    ap.add_argument("analysis_json")
    ap.add_argument("output")
    args = ap.parse_args()
    print(generate(args.analysis_json, args.output))


if __name__ == "__main__":
    main()
