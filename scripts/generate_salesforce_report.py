#!/usr/bin/env python3
"""
HTML report (dark mode) of the Salesforce tester: the org inventory (salesforce.json, from
`npm run salesforce`) and, optionally, the analysis and tests of the salesforce-tester agent.

Usage:
    python scripts/generate_salesforce_report.py <salesforce.json> <output.html> [--analysis analysis.json]

analysis.json schema (everything optional):
{
  "verdict": "The org is ready to test release 2.4, with 2 risks", "verdict_tone": "ok|warn|bad",
  "summary": "...",
  "tests": [{"id": "TC-001", "area": "Validation", "case": "Opportunity without amount", "profile": "Sales",
               "result": "Passed|Failed|Blocked|Pending", "detail": "...", "evidence": "screenshots/tc-001.png"}],
  "findings": [{"severity": "High", "area": "Sharing", "text": "..."}],      // the agent's own (added to the inventory's)
  "discarded": [{"text": "...", "reason": "..."}],                            // inventory findings that do not apply
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
from _report_styles import (page, meta, section, kpi_tiles, banner, table, doc_list, two_col, bar_chart,
                              level_badge, status_pill, missing_info, thumbnail, resolve_evidence, e,
                              CRITICAL, SERIOUS, WARNING, SERIES)

SEV_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
TONE = {"ok": "ok", "warn": "warn", "bad": "bad"}


def _rel(r, rel, field="Name"):
    v = r.get(rel)
    return v.get(field) if isinstance(v, dict) else r.get(field)


def generate(sf_json, output, analysis_json=None):
    data = json.loads(Path(sf_json).read_text(encoding="utf-8"))
    analysis = json.loads(Path(analysis_json).read_text(encoding="utf-8")) if analysis_json and Path(analysis_json).exists() else {}
    inv = data.get("inventory") or {}
    org = data.get("org") or {}

    discarded = {(d.get("text") or "").strip() for d in analysis.get("discarded") or []}
    findings = [h for h in data.get("findings") or [] if (h.get("text") or "").strip() not in discarded]
    findings += analysis.get("findings") or []
    findings.sort(key=lambda x: SEV_ORDER.get(x.get("severity"), 9))
    tests = analysis.get("tests") or []
    failed = sum(1 for p in tests if p.get("result") == "Failed")
    critical = sum(1 for h in findings if h.get("severity") in ("Critical", "High"))
    coverage = inv.get("org_coverage")

    kpis = [("Org", "Sandbox" if org.get("sandbox") else "PRODUCTION", "ok" if org.get("sandbox") else "bad", org.get("type") or "", "screen"),
            ("Apex coverage", f"{coverage:.0f} %" if isinstance(coverage, (int, float)) else "—",
             ("ok" if coverage >= 75 else "bad") if isinstance(coverage, (int, float)) else "", "minimum 75 % for production", "code",
             {"pct": coverage} if isinstance(coverage, (int, float)) else None),
            ("Findings", len(findings), "bad" if critical else ("warn" if findings else "ok"), f"{critical} critical or high", "bug"),
            ("Test suggestions", len(data.get("suggestions") or []), "", "derived from the inventory", "list")]
    if tests:
        kpis.append(("Tests run", len(tests), "bad" if failed else "ok", f"{failed} failed", "ok" if not failed else "bad"))

    body = ""
    if analysis.get("verdict"):
        body += banner(analysis["verdict"], TONE.get(analysis.get("verdict_tone"), "ok"))
    if not org.get("sandbox"):
        body += banner("PRODUCTION org: it was only surveyed read-only. Functional tests go in a sandbox.", "bad")
    body += section("Summary", kpi_tiles(kpis) + (f'<div class="cardbody"><p>{e(analysis["summary"])}</p></div>' if analysis.get("summary") else ""))

    if findings:
        body += section("Findings", table(["Severity", "Area", "Detail"],
                                             [[level_badge(h.get("severity")), e(h.get("area", "")), e(h.get("text", ""))] for h in findings]),
                          sub=f"{len(findings)} in total")
    else:
        body += section("Findings", banner("No findings in the inventory.", "ok"))

    if tests:
        base = Path(output).resolve().parent
        rows = []
        for p in tests:
            ev = ""
            if p.get("evidence"):
                path, exists = resolve_evidence(p["evidence"], base)
                ev = thumbnail(path, p.get("case", ""), exists=exists)
            rows.append([f'<span class="id">{e(p.get("id", ""))}</span>', e(p.get("area", "")), e(p.get("case", "")), e(p.get("profile", "—")),
                          status_pill(p.get("result")), e(p.get("detail", "")), ev])
        body += section("Tests run", table(["ID", "Area", "Case", "Profile", "Result", "Detail", "Evidence"], rows))

    if data.get("suggestions"):
        by_area = {}
        for s in data["suggestions"]:
            by_area[s.get("area", "Other")] = by_area.get(s.get("area", "Other"), 0) + 1
        left = section("What to test, by area", bar_chart([(a, n, SERIES[i % len(SERIES)]) for i, (a, n) in enumerate(sorted(by_area.items(), key=lambda x: -x[1]))]), width=4)
        right = section("Test suggestions", table(["Area", "Element", "Suggested test"],
                                                     [[e(s.get("area")), f'<span class="mono">{e(s.get("element"))}</span>', e(s.get("test"))]
                                                      for s in data["suggestions"]]), "derived from the inventory: the agent prioritizes them", width=8)
        body += right + left

    org_rows = [["Alias", e(org.get("alias"))], ["Name", e(org.get("name"))], ["Type", e(org.get("type"))],
                 ["Instance", e(org.get("instance"))], ["Language", e(org.get("language"))], ["Time zone", e(org.get("timezone"))],
                 ["API version", e(org.get("api"))]]
    left = section("The org", table(["Field", "Value"], org_rows), width=6)
    sev_lim = []
    for lim in inv.get("limits") or []:
        mx, rem = lim.get("max") or 0, lim.get("remaining")
        if mx and rem is not None and (mx - rem) / mx >= 0.5:
            pct = 100 * (mx - rem) / mx
            sev_lim.append((lim.get("name"), round(pct), CRITICAL if pct >= 90 else SERIOUS if pct >= 80 else WARNING))
    right = section("Most used limits", bar_chart(sorted(sev_lim, key=lambda x: -x[1])[:10], label_width=220) if sev_lim
                  else banner("No limit is above 50 % usage.", "ok"), "% used", width=6)
    body += two_col(left, right)

    if inv.get("apex"):
        ax = inv["apex"]
        if ax.get("error"):
            body += section("Apex tests", banner(f'They could not be run: {ax["error"]}', "warn"))
        else:
            rows = [["Result", e(ax.get("result"))], ["Ran", e(ax.get("ran"))], ["Passed", e(ax.get("passed"))],
                     ["Failed", e(ax.get("failed_n"))], ["Org coverage", e(ax.get("org_coverage"))]]
            body += section("Apex tests", table(["Field", "Value"], rows))

    cov = sorted(inv.get("coverage") or [], key=lambda c: (c.get("NumLinesCovered") or 0) / max(1, (c.get("NumLinesCovered") or 0) + (c.get("NumLinesUncovered") or 0)))
    if cov:
        rows = []
        for c in cov[:25]:
            covered, uncovered = c.get("NumLinesCovered") or 0, c.get("NumLinesUncovered") or 0
            pct = 100 * covered / (covered + uncovered) if covered + uncovered else 0
            rows.append([f'<span class="mono">{e(_rel(c, "ApexClassOrTrigger"))}</span>', f"{pct:.0f} %", e(covered), e(uncovered)])
        body += section("Classes with the lowest coverage", table(["Class or trigger", "Coverage", "Covered lines", "Uncovered"], rows), "the 25 lowest")

    if inv.get("validations"):
        body += section("Validation rules", table(["Object", "Rule", "Active", "Message", "Field"],
                                                        [[e(_rel(v, "EntityDefinition", "QualifiedApiName")), f'<span class="mono">{e(v.get("ValidationName"))}</span>',
                                                          "Yes" if v.get("Active") else "No", e(v.get("ErrorMessage")), e(v.get("ErrorDisplayField") or "top")]
                                                         for v in inv["validations"]]), f'{len(inv["validations"])} in total')
    if inv.get("flows"):
        body += section("Flows and automations", table(["Flow", "Type", "Trigger", "Active", "Last modified"],
                                                            [[e(f.get("Label")), e("Process Builder" if f.get("ProcessType") == "Workflow" else f.get("ProcessType")),
                                                              e(f.get("TriggerType") or "—"), "Yes" if f.get("IsActive") else "No", e((f.get("LastModifiedDate") or "")[:10])]
                                                             for f in inv["flows"]]), f'{len(inv["flows"])} in total')
    if inv.get("triggers"):
        body += section("Apex triggers", table(["Object", "Trigger", "Status"],
                                                    [[e(t.get("TableEnumOrId")), f'<span class="mono">{e(t.get("Name"))}</span>', e(t.get("Status"))] for t in inv["triggers"]]))
    left = section("Profiles with active users", table(["Profile", "Active users"],
                                                         [[e(_rel(p, "Profile")), e(p.get("total"))]
                                                          for p in sorted(inv.get("users_by_profile") or [], key=lambda p: -(p.get("total") or 0))]),
                  width=6) if inv.get("users_by_profile") else ""
    right = section("Permission sets", table(["Permission set", "Package"],
                                           [[e(p.get("Label")), e(p.get("NamespacePrefix") or "—")] for p in inv.get("permission_sets") or []]),
                  width=6) if inv.get("permission_sets") else ""
    if left and right:
        body += two_col(left, right)
    elif left or right:
        body += left or right
    if inv.get("sharing"):
        body += section("Default access (OWD)", table(["Object", "Internal", "External"],
                                                            [[e(o.get("QualifiedApiName")), e(o.get("InternalSharingModel")), e(o.get("ExternalSharingModel"))]
                                                             for o in inv["sharing"]]))
    if inv.get("record_types"):
        body += section("Record types", table(["Object", "Record type", "Active"],
                                                [[e(r.get("SobjectType")), e(r.get("Name")), "Yes" if r.get("IsActive") else "No"] for r in inv["record_types"]]))

    if analysis.get("recommendations"):
        body += section("Recommendations", table(["Priority", "Action", "Why"],
                                                   [[level_badge(x.get("priority", "Medium")), e(x.get("action", "")), e(x.get("reason", ""))]
                                                    for x in analysis["recommendations"]]))
    if analysis.get("next_steps"):
        body += section("Next steps", doc_list(analysis["next_steps"]))
    body += missing_info(analysis.get("missing_info"))
    if inv.get("errors"):
        body += section("Queries that could not be run", table(["Query", "Error"],
                                                                      [[e(k), f'<span class="mono">{e(v)}</span>'] for k, v in inv["errors"].items()]),
                          "a permission may be missing (View Setup, API Enabled) or the object does not exist in this edition")

    html = page("Salesforce", "Salesforce · inventory and tests",
                meta([("Generated", data.get("generated")), ("Story", data.get("story")), ("Org", org.get("alias")),
                      ("Type", "Sandbox" if org.get("sandbox") else "Production")]), body)
    Path(output).write_text(html, encoding="utf-8")
    return output


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="HTML report of the Salesforce tester.")
    ap.add_argument("sf_json")
    ap.add_argument("output")
    ap.add_argument("--analysis", default=None)
    args = ap.parse_args()
    print(generate(args.sf_json, args.output, args.analysis))


if __name__ == "__main__":
    main()
