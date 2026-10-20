#!/usr/bin/env python3
"""
HTML report (dark mode) of the SAP tester (sap-tester agent): SAP GUI (transactions) and Fiori/UI5.

Usage (from the repo root):
    python scripts/generate_sap_report.py <analysis.json> <output.html>

Unlike the tool reports, there is no binary here that generates data: the agent builds the
tests (SAP GUI Scripting, Playwright for Fiori, OData with api-runner) and writes everything to analysis.json.

analysis.json schema (everything optional except "title"):
{
  "title": "SAP — US-010 (Order to Cash)", "story": "US-010", "environment": "QA (non-production)",
  "generated": "2026-10-19T12:00:00",
  "system": {"sid": "DQ1", "client": "100", "type": "S/4HANA", "version": "2023", "gui_scripting": true, "fiori": true},
  "verdict": "The O2C flow closes; 1 high finding in an authorization", "verdict_tone": "warn",
  "summary": "...",
  "tests": [{"id": "TC-001", "area": "SAP GUI", "transaction": "VA01", "case": "Create sales order",
               "result": "Passed|Failed|Blocked|Pending|N/A", "expected": "...", "actual": "...",
               "evidence": "screenshots/tc-001.png"}],
  "authorizations": [{"role": "Z_SALES", "user": "QA_TEST", "object": "V_VBAK_VKO", "activity": "01 Create",
                      "result": "Passed|Failed", "detail": "SU53 with no failures"}],
  "processes": [{"process": "Order to Cash", "step": "VA01 → VL01N → VF01", "status": "Passed", "detail": "..."}],
  "findings": [{"id": "F-01", "severity": "High", "area": "Authorizations", "text": "...",
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
    sys_info = d.get("system") or {}

    findings = sorted(d.get("findings") or [], key=lambda x: SEV_ORDER.get(x.get("severity"), 9))
    critical = sum(1 for h in findings if h.get("severity") in ("Critical", "High"))
    tests = d.get("tests") or []
    failed = sum(1 for p in tests if p.get("result") == "Failed")
    passed = sum(1 for p in tests if p.get("result") == "Passed")
    auth = d.get("authorizations") or []
    bad_auth = sum(1 for a in auth if a.get("result") == "Failed")
    processes = d.get("processes") or []

    kpis = [("Tests", len(tests), "bad" if failed else ("ok" if tests else ""),
             f"{passed} passed, {failed} failed", "list"),
            ("Findings", len(findings), "bad" if critical else ("warn" if findings else "ok"), f"{critical} critical or high", "bug")]
    if auth:
        kpis.append(("Authorizations", "With failures" if bad_auth else "OK", "bad" if bad_auth else "ok", f"{len(auth)} reviewed", "shield"))
    if processes:
        ok_proc = sum(1 for p in processes if p.get("status") == "Passed")
        kpis.append(("Business processes", f"{ok_proc}/{len(processes)}", "bad" if ok_proc < len(processes) else "ok", "complete steps", "flow"))

    body = ""
    if d.get("verdict"):
        body += banner(d["verdict"], TONE.get(d.get("verdict_tone"), "ok"))
    if (d.get("environment") or "").lower().startswith(("qa", "sandbox", "test", "dev", "non-prod", "non prod", "stag")):
        body += banner("Non-production system: tests on a QA client, with no real production data.", "ok")
    if sys_info.get("gui_scripting") is False:
        body += banner("SAP GUI Scripting is disabled: GUI automation is not possible until it is enabled (RZ11 sapgui/user_scripting).", "warn")
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

    if auth:
        rows = [[e(a.get("role") or a.get("user", "")), e(a.get("object", "")), e(a.get("activity", "")),
                  status_pill(a.get("result")), e(a.get("detail", ""))] for a in auth]
        body += section("Authorizations and roles", table(["Role / user", "Authorization object", "Activity", "Result", "Detail"], rows),
                          "PFCG / SU01 / SU53")

    if processes:
        rows = [[e(p.get("process", "")), e(p.get("step", "")), status_pill(p.get("status")), e(p.get("detail", ""))] for p in processes]
        body += section("Business processes", table(["Process", "Step", "Status", "Detail"], rows))

    if tests:
        rows = []
        for p in sorted(tests, key=lambda p: RESULT_ORDER.get(p.get("result"), 5)):
            ev = ""
            if p.get("evidence"):
                path, exists = resolve_evidence(p["evidence"], base)
                ev = thumbnail(path, p.get("case", ""), exists=exists)
            rows.append([f'<span class="id">{e(p.get("id", ""))}</span>', e(p.get("area", "")), e(p.get("transaction", "")), e(p.get("case", "")),
                          status_pill(p.get("result")), e(p.get("expected", "")), e(p.get("actual", "")), ev])
        body += section("Tests run", table(["ID", "Area", "Transaction / App", "Case", "Result", "Expected", "Actual", "Evidence"], rows))

    if d.get("recommendations"):
        body += section("Recommendations", table(["Priority", "Action", "Why"],
                          [[level_badge(x.get("priority", "Medium")), e(x.get("action", "")), e(x.get("reason", ""))] for x in d["recommendations"]]))
    if d.get("next_steps"):
        body += section("Next steps", doc_list(d["next_steps"]))
    body += missing_info(d.get("missing_info"))

    html = page(d.get("title") or "SAP", "SAP GUI · Fiori / UI5",
                meta([("Generated", d.get("generated")), ("Story", d.get("story")), ("Environment", d.get("environment")),
                      ("System", f'{sys_info.get("sid", "—")} / client {sys_info.get("client", "—")}' if sys_info else None),
                      ("Type", f'{sys_info.get("type", "")} {sys_info.get("version", "")}'.strip() or None),
                      ("GUI Scripting", {True: "enabled", False: "disabled"}.get(sys_info.get("gui_scripting")))]), body)
    Path(output).write_text(html, encoding="utf-8")
    return output


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="HTML report of the SAP tester (GUI and Fiori).")
    ap.add_argument("analysis_json")
    ap.add_argument("output")
    args = ap.parse_args()
    print(generate(args.analysis_json, args.output))


if __name__ == "__main__":
    main()
