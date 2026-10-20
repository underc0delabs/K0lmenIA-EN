#!/usr/bin/env python3
"""
HTML report (dark mode) of the e-commerce testers (shopify-tester, wordpress-tester, prestashop-tester and
vtex-tester): the store survey (<platform>.json, from `npm run shopify`, `npm run wordpress`, `npm run prestashop`
or `npm run vtex`) and, optionally, the agent's analysis and tests.

Usage:
    python scripts/generate_ecommerce_report.py <platform.json> <output.html> [--analysis analysis.json]

analysis.json schema (everything optional):
{
  "verdict": "The store is ready for the campaign, with 2 risks", "verdict_tone": "ok|warn|bad",
  "summary": "...",
  "tests": [{"id": "TC-001", "area": "Checkout", "case": "Payment declined with a test card", "device": "Mobile",
             "result": "Passed|Failed|Blocked|Pending", "detail": "...", "evidence": "screenshots/tc-001.png"}],
  "findings": [{"severity": "High", "area": "Shipping", "text": "..."}],   // the agent's own (added to the survey's)
  "discarded": [{"text": "...", "reason": "..."}],                         // survey findings that do not apply
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
import _history  # noqa: E402
from _report_styles import (page, meta, section, kpi_tiles, banner, table, doc_list, bar_chart, level_badge,  # noqa: E402
                            status_pill, missing_info, thumbnail, resolve_evidence, _pill, e,
                            OK, WARNING, CRITICAL, NEUTRAL, SERIES)

SEV_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
NAME = {"shopify": "Shopify", "wordpress": "WordPress / WooCommerce", "prestashop": "PrestaShop", "vtex": "VTEX"}
CHECK_STATUS = {"ok": ("Good", OK, "✓"), "warning": ("Review", WARNING, "!"), "fail": ("Fail", CRITICAL, "✕"), "info": ("Info", NEUTRAL, "i")}

for _p in NAME:
    _history.TYPES.setdefault(_p, {
        "file": f"{_p}.json", "items": lambda d: d.get("findings") or [],
        "key": lambda h: f'{h.get("area")}|{_history._norm(h.get("text"))}', "title": lambda h: f'[{h.get("area")}] {h.get("text")}',
        "metrics": [("Findings", _history._r("findings"), ""), ("Critical or high", _history._r("critical"), ""),
                    ("Products with issues", _history._r("products_with_issues"), ""), ("Suggestions", _history._r("suggestions"), "")]})


def generate(data_json, output, analysis_json=None):
    data = json.loads(Path(data_json).read_text(encoding="utf-8"))
    analysis = json.loads(Path(analysis_json).read_text(encoding="utf-8")) if analysis_json and Path(analysis_json).exists() else {}
    platform = data.get("platform") or "shopify"
    name = NAME.get(platform, platform.capitalize())
    store = data.get("store") or {}

    discarded = {(d.get("text") or "").strip() for d in analysis.get("discarded") or []}
    findings = [h for h in data.get("findings") or [] if (h.get("text") or "").strip() not in discarded]
    findings += analysis.get("findings") or []
    findings.sort(key=lambda x: SEV_ORDER.get(x.get("severity"), 9))
    tests = analysis.get("tests") or []
    failed = sum(1 for p in tests if p.get("result") == "Failed")
    critical = sum(1 for h in findings if h.get("severity") in ("Critical", "High"))

    kpis = [("Store", store.get("version") or name, "", store.get("environment") if store.get("environment") not in (None, "—") else store.get("url", ""), "screen"),
            ("Findings", len(findings), "bad" if critical else ("warn" if findings else "ok"), f"{critical} critical or high", "bug"),
            ("Test suggestions", len(data.get("suggestions") or []), "", "derived from the survey", "list")]
    kpis += [(i.get("label"), i.get("value"), i.get("tone") or "", i.get("detail") or "") for i in data.get("indicators") or []]
    if tests:
        kpis.append(("Tests run", len(tests), "bad" if failed else "ok", f"{failed} failed", "ok" if not failed else "bad"))

    body = ""
    if analysis.get("verdict"):
        body += banner(analysis["verdict"], analysis.get("verdict_tone") if analysis.get("verdict_tone") in ("ok", "warn", "bad") else "ok")
    body += section("Summary", kpi_tiles(kpis) + (f'<div class="cardbody"><p>{e(analysis["summary"])}</p></div>' if analysis.get("summary") else ""))

    if findings:
        body += section("Findings", table(["Severity", "Area", "Detail"],
                                          [[level_badge(h.get("severity")), e(h.get("area", "")), e(h.get("text", ""))] for h in findings]),
                        sub=f"{len(findings)} in total")
    else:
        body += section("Findings", banner("No findings in the survey.", "ok"))

    if tests:
        base = Path(output).resolve().parent
        rows = []
        for p in tests:
            ev = ""
            if p.get("evidence"):
                path, exists = resolve_evidence(p["evidence"], base)
                ev = thumbnail(path, p.get("case", ""), exists=exists)
            rows.append([f'<span class="id">{e(p.get("id", ""))}</span>', e(p.get("area", "")), e(p.get("case", "")), e(p.get("device", "—")),
                         status_pill(p.get("result")), e(p.get("detail", "")), ev])
        body += section("Tests run", table(["ID", "Area", "Case", "Device", "Result", "Detail", "Evidence"], rows))

    if data.get("suggestions"):
        by_area = {}
        for s in data["suggestions"]:
            by_area[s.get("area", "Other")] = by_area.get(s.get("area", "Other"), 0) + 1
        body += section("Test suggestions", table(["Area", "Element", "Suggested test"],
                                                  [[e(s.get("area")), f'<span class="mono">{e(s.get("element"))}</span>', e(s.get("test"))]
                                                   for s in data["suggestions"]]), "derived from the survey: the agent prioritizes them", width=8)
        body += section("What to test, by area", bar_chart([(a, n, SERIES[i % len(SERIES)]) for i, (a, n) in
                                                            enumerate(sorted(by_area.items(), key=lambda x: -x[1]))]), width=4)

    checks = (data.get("storefront") or {}).get("checks") or []
    if checks:
        rows = []
        for ch in checks:
            txt, color, ic = CHECK_STATUS.get(ch.get("status"), CHECK_STATUS["info"])
            rows.append([e(ch.get("check")), _pill(txt, color, ic), e(ch.get("detail"))])
        body += section("Storefront checks", table(["Check", "Status", "Detail"], rows), "public, no credentials")

    for t in data.get("tables") or []:
        body += section(t.get("title") or "", table(t.get("columns") or [], [[e(x) for x in row] for row in t.get("rows") or []]), t.get("sub") or "")

    body += _history.section(platform, Path(data_json).resolve().parent, data)
    if analysis.get("recommendations"):
        body += section("Recommendations", table(["Priority", "Action", "Why"],
                                                 [[level_badge(x.get("priority", "Medium")), e(x.get("action", "")), e(x.get("reason", ""))]
                                                  for x in analysis["recommendations"]]))
    if analysis.get("next_steps"):
        body += section("Next steps", doc_list(analysis["next_steps"]))
    body += missing_info(analysis.get("missing_info"))
    if data.get("errors"):
        body += section("Queries that could not be run", table(["Query", "Error"],
                                                               [[e(k), f'<span class="mono">{e(v)}</span>'] for k, v in data["errors"].items()]),
                        "the key or the read permission may be missing, or the API version may not have it")

    html = page(name, f"{name} · survey and tests",
                meta([("Generated", data.get("generated")), ("Story", data.get("story")), ("Store", store.get("url"))]), body)
    Path(output).write_text(html, encoding="utf-8")
    return output


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="HTML report of the e-commerce testers (Shopify, WordPress / WooCommerce, PrestaShop, VTEX).")
    ap.add_argument("data_json")
    ap.add_argument("output")
    ap.add_argument("--analysis", default=None)
    args = ap.parse_args()
    print(generate(args.data_json, args.output, args.analysis))


if __name__ == "__main__":
    main()
