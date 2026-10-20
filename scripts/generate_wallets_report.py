#!/usr/bin/env python3
"""
HTML report (dark mode) of the digital wallets and payments tester (wallet-tester agent).

Usage (from the repo root):
    python scripts/generate_wallets_report.py <analysis.json> <output.html>

Unlike the tool reports, here there is no binary that generates data: the agent builds
the tests (with api-runner/Newman, Playwright, data-verifier) and writes everything in analysis.json.

analysis.json schema (everything optional except "title"):
{
  "title": "Wallet — US-010 (P2P transfers)", "story": "US-010", "environment": "sandbox",
  "generated": "2026-10-19T12:00:00", "payment_provider": "Mercado Pago (sandbox)",
  "verdict": "The wallet conserves balances and is idempotent; 1 high finding in concurrency",
  "verdict_tone": "warn",  // ok | warn | bad
  "summary": "...",
  "tests": [{"id": "TC-API-003", "category": "Idempotency", "case": "Retry with the same Idempotency-Key",
             "result": "Passed|Failed|Blocked|Pending|N/A", "expected": "a single movement",
             "actual": "a single movement", "evidence": "screenshots/tc-003.png"}],
  "conservation": [{"scenario": "P2P A→B of 500", "before": 10000, "after": 10000, "balances": true, "detail": "system total"}],
  "findings": [{"id": "H-01", "severity": "High", "category": "Concurrency",
                "text": "Two parallel withdrawals with balance for one leave the balance negative (double spending).",
                "impact": "...", "how_to_reproduce": "...", "recommendation": "..."}],
  "reconciliation": {"wallet_movements": 42, "provider_movements": 42, "differences": 0,
                     "detail": [{"concept": "Fees", "wallet": 120.5, "provider": 120.5, "difference": 0}]},
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
                              CRITICAL, SERIOUS, WARNING, NEUTRAL, OK, SERIES, _num)

SEV_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
RESULT_ORDER = {"Failed": 0, "Blocked": 1, "Pending": 2, "Passed": 3, "N/A": 4}
TONE = {"ok": "ok", "warn": "warn", "bad": "bad"}


def _money(v):
    return _num(v) if isinstance(v, (int, float)) else (e(v) if v is not None else "—")


def generate(analysis_json, output):
    d = json.loads(Path(analysis_json).read_text(encoding="utf-8"))
    base = Path(output).resolve().parent

    found = sorted(d.get("findings") or [], key=lambda x: SEV_ORDER.get(x.get("severity"), 9))
    critical = sum(1 for h in found if h.get("severity") in ("Critical", "High"))
    tests = d.get("tests") or []
    failed = sum(1 for p in tests if p.get("result") == "Failed")
    passed = sum(1 for p in tests if p.get("result") == "Passed")
    conserv = d.get("conservation") or []
    mismatch = sum(1 for c in conserv if c.get("balances") is False)
    rec = d.get("reconciliation") or {}
    diffs = rec.get("differences")

    kpis = [("Tests", len(tests), "bad" if failed else ("ok" if tests else ""),
             f"{passed} passed, {failed} failed", "list"),
            ("Findings", len(found), "bad" if critical else ("warn" if found else "ok"), f"{critical} critical or high", "bug"),
            ("Balance conservation", "Does not balance" if mismatch else ("Balances" if conserv else "—"),
             "bad" if mismatch else ("ok" if conserv else ""), f"{len(conserv)} scenario(s)", "shield")]
    if rec:
        kpis.append(("Reconciliation", "With differences" if diffs else "No differences",
                     "bad" if diffs else "ok", f"{rec.get('wallet_movements', '—')} vs. {rec.get('provider_movements', '—')} movements", "load"))

    body = ""
    if d.get("verdict"):
        body += banner(d["verdict"], TONE.get(d.get("verdict_tone"), "ok"))
    body += banner("Test environment: test money and cards, no real movements or data.", "ok") if (d.get("environment") or "").lower().startswith(("sandbox", "test", "qa", "stag")) else ""
    body += section("Summary", kpi_tiles(kpis) + (f'<div class="cardbody"><p>{e(d["summary"])}</p></div>' if d.get("summary") else ""))

    if found:
        by_cat = {}
        for h in found:
            by_cat[h.get("category", "Other")] = by_cat.get(h.get("category", "Other"), 0) + 1
        rows = [[f'<span class="id">{e(h.get("id", ""))}</span>', level_badge(h.get("severity")), e(h.get("category", "")),
                 e(h.get("text", "")), e(h.get("impact", "")), e(h.get("recommendation", ""))] for h in found]
        tbl = section("Findings", table(["ID", "Severity", "Category", "What happens", "Impact", "Recommendation"], rows),
                      f"{len(found)} in total", width=8)
        panel = section("Findings by category", bar_chart([(c, n, SERIES[i % len(SERIES)]) for i, (c, n) in enumerate(sorted(by_cat.items(), key=lambda x: -x[1]))]), width=4)
        body += tbl + panel
        detailed = [h for h in found if h.get("how_to_reproduce")]
        if detailed:
            rows = [[f'<span class="id">{e(h.get("id"))}</span>', e(h.get("text", "")), e(h.get("how_to_reproduce"))] for h in detailed]
            body += section("How to reproduce", table(["ID", "Finding", "Steps"], rows))
    else:
        body += section("Findings", banner("No findings.", "ok"))

    if conserv:
        rows = []
        for c in conserv:
            ok = c.get("balances")
            rows.append([e(c.get("scenario")), _money(c.get("before")), _money(c.get("after")),
                         status_pill("Passed" if ok else "Failed") if ok is not None else "—", e(c.get("detail", ""))])
        body += section("Balance conservation (money is neither created nor destroyed)",
                        table(["Scenario", "Total before", "Total after", "Balances?", "Detail"], rows))

    if tests:
        rows = []
        for p in sorted(tests, key=lambda p: RESULT_ORDER.get(p.get("result"), 5)):
            ev = ""
            if p.get("evidence"):
                path, exists = resolve_evidence(p["evidence"], base)
                ev = thumbnail(path, p.get("case", ""), exists=exists)
            rows.append([f'<span class="id">{e(p.get("id", ""))}</span>', e(p.get("category", "")), e(p.get("case", "")),
                         status_pill(p.get("result")), e(p.get("expected", "")), e(p.get("actual", "")), ev])
        body += section("Tests run", table(["ID", "Category", "Case", "Result", "Expected", "Actual", "Evidence"], rows))

    if rec:
        kp = kpi_tiles([("Movements in the wallet", _num(rec.get("wallet_movements")) if rec.get("wallet_movements") is not None else "—", ""),
                        ("Movements at the provider", _num(rec.get("provider_movements")) if rec.get("provider_movements") is not None else "—", ""),
                        ("Differences", _num(diffs) if diffs is not None else "—", "bad" if diffs else "ok")])
        rows = [[e(x.get("concept")), _money(x.get("wallet")), _money(x.get("provider")),
                 (status_pill("Failed") if x.get("difference") else status_pill("Passed"))] for x in rec.get("detail") or []]
        body += section("Reconciliation with the payment provider",
                        kp + (table(["Concept", "Wallet", "Provider", "Balances?"], rows) if rows else "")
                        + (f'<div class="cardbody"><p>{e(rec["text_detail"])}</p></div>' if rec.get("text_detail") else ""))

    if d.get("recommendations"):
        body += section("Recommendations", table(["Priority", "Action", "Why"],
                                                 [[level_badge(x.get("priority", "Medium")), e(x.get("action", "")), e(x.get("reason", ""))]
                                                  for x in d["recommendations"]]))
    if d.get("next_steps"):
        body += section("Next steps", doc_list(d["next_steps"]))
    body += missing_info(d.get("missing_info"))

    html = page(d.get("title") or "Wallet and payments", "Digital wallets · payments",
                meta([("Generated", d.get("generated")), ("Story", d.get("story")), ("Environment", d.get("environment")),
                      ("Provider", d.get("payment_provider"))]), body)
    Path(output).write_text(html, encoding="utf-8")
    return output


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="HTML report of the wallets and payments tester.")
    ap.add_argument("analysis_json")
    ap.add_argument("output")
    args = ap.parse_args()
    print(generate(args.analysis_json, args.output))


if __name__ == "__main__":
    main()
