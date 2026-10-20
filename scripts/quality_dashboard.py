#!/usr/bin/env python3
"""
Quality dashboard (quality-dashboard agent): gathers what the k0lmenIA tools already left behind and builds
a dashboard per sprint, release or date range.

Usage (from the repo root):
    python scripts/quality_dashboard.py [--name sprint-12] [--from 2026-10-01] [--until 2026-10-14]
    python scripts/quality_dashboard.py --report-only --name sprint-12 --analysis output/dashboard/sprint-12/analysis.json

Sources (the ones that exist; whatever is missing is reported in "no_data", never made up):
  - Live runs: output/runs/_results-*.json
  - npm test: tools/k0lmena/reports/{web,api,mobile}/cucumber-report.json and its history/
  - Case inventory (manual, BDD and automated in k0lmena) with its latest result, the flaky ones,
    the open bugs and the estimated manual run time (the same as select_cases.py). With that it
    computes the automation savings: what running the automated cases by hand would cost minus what
    they take running on their own (savings per run and accumulated over the period).
  - Criteria coverage: output/coverage/*/coverage.json (the most recent)
  - Bugs: output/bug-reports/BUG-*.md (severity, status and story)
  - Failures and flaky tests: output/failures/*/failures.json (the most recent)
  - Accessibility, web performance, performance and security: their JSON files in output/

--from / --until (YYYY-MM-DD, inclusive) filter the runs, the results and the bugs reported in
the period; the inventory, the coverage and the open bugs are always the current snapshot.

Leaves in output/dashboard/<name>/: dashboard.json (the data) and dashboard-report.html. The previous run with
the same name moves to history/ (last 5) and the report shows the trend.

analysis.json (optional, written by the agent):
{
  "verdict": "Sprint quality is acceptable with two risks",
  "verdict_tone": "ok | warn | bad",
  "summary": "Short text for management: where we are, what changed, what is concerning",
  "risks": [{"risk": "...", "impact": "...", "level": "High"}],
  "recommendations": [{"action": "...", "why": "...", "priority": "High"}],
  "next_steps": ["..."],
  "notes": {"<indicator or story>": "comment"}
}
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _history  # noqa: E402
import collect_results as rec  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ["dashboard.json", "analysis.json", "dashboard-report.html"]
SEVERITIES = rec.SEVERITIES
SUITES = ("web", "api", "mobile")


def use_root(root):
    """Points the dashboard (and the readers it reuses) to another root; used by the tests."""
    global ROOT
    ROOT = Path(root)
    rec.ROOT = ROOT
    rec.K0 = ROOT / "tools" / "k0lmena" / "reports"
    try:
        import select_cases as sc
        sc.ROOT = ROOT
    except Exception:
        pass


# ------------------------------------------------------------------ dates
def _ts(text):
    if not text:
        return None
    t = str(text).strip()
    try:
        return datetime.fromisoformat(t.replace(" ", "T")[:19]).timestamp()
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y %H:%M", "%m/%d/%Y"):
        try:
            return datetime.strptime(t, fmt).timestamp()
        except ValueError:
            continue
    return None


def date_range(date_from=None, date_until=None):
    d = datetime.strptime(date_from, "%Y-%m-%d").timestamp() if date_from else None
    h = (datetime.strptime(date_until, "%Y-%m-%d") + timedelta(days=1)).timestamp() if date_until else None
    return d, h


def _in(ts, r):
    if ts is None:
        return r == (None, None)
    return (r[0] is None or ts >= r[0]) and (r[1] is None or ts < r[1])


def _json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _fmt(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else ""


# ------------------------------------------------------------------ sources
def _scenario_status(sc):
    statuses = [(p.get("result") or {}).get("status", "undefined") for p in sc.get("steps", [])]
    if any(s in ("failed", "ambiguous") for s in statuses):
        return "Failed"
    if statuses and all(s == "passed" for s in statuses):
        return "Passed"
    return "Blocked"


def runs(r):
    """Each run (live run or npm test per suite, with its history) within the range."""
    output = []
    for file in sorted(glob.glob(str(ROOT / "output" / "runs" / "_results-*.json"))):
        d = _json(file)
        if not isinstance(d, dict):
            continue
        ts = _ts(d.get("date")) or os.path.getmtime(file)
        count = Counter(rec._status(c.get("status")) for c in d.get("cases") or [])
        output.append({"ts": ts, "source": "live", "story": (d.get("story") or "").upper(), "count": count})
    k0 = ROOT / "tools" / "k0lmena" / "reports"
    for suite in SUITES:
        files = [k0 / suite / "cucumber-report.json"] + sorted((k0 / suite / "history").glob("*/cucumber-report.json"))
        for file in files:
            d = _json(file) if file.exists() else None
            if not isinstance(d, list) or not d:
                continue
            count = Counter(_scenario_status(sc) for f in d for sc in f.get("elements", []) if sc.get("type") != "background")
            output.append({"ts": os.path.getmtime(file), "source": f"npm test · {suite}", "story": "", "count": count})
    out = []
    for c in sorted(output, key=lambda c: c["ts"]):
        if not _in(c["ts"], r) and r != (None, None):
            continue
        n = sum(c["count"].values())
        if not n:
            continue
        out.append({"date": _fmt(c["ts"]), "source": c["source"], "story": c["story"], "total": n,
                    "passed": c["count"]["Passed"], "failed": c["count"]["Failed"], "blocked": c["count"]["Blocked"],
                    "pct_passed": round(c["count"]["Passed"] / n * 100, 1)})
    return out


def period_results(r):
    """Latest result of each case (story + id) run within the range (live and npm test with its history)."""
    latest = {}
    for x in sorted(rec.from_runs(None) + rec.from_cucumber(None), key=lambda x: x["moment"]):
        if r == (None, None) or _in(x["moment"], r):
            latest[rec.case_key(x)] = x  # story + id: TCs are numbered per story
    return Counter(x["status"] for x in latest.values())


def inventory():
    try:
        import select_cases as sc
        sc.ROOT = ROOT
        return sc.inventory()
    except Exception as ex:  # an odd spreadsheet does not stop the dashboard
        print(f"[!] Could not build the case inventory ({ex}).", file=sys.stderr)
        return []


def _most_recent(pattern):
    files = sorted(glob.glob(str(ROOT / pattern)), key=os.path.getmtime)
    return Path(files[-1]) if files else None


def coverage():
    file = _most_recent("output/coverage/*/coverage.json")
    d = _json(file) if file else None
    if not isinstance(d, dict):
        return None
    by_story = {}
    for h in d.get("stories") or []:
        m = h.get("metrics") or {}
        if m.get("criteria"):
            by_story[h.get("story")] = round(m.get("covered_criteria", 0) / m["criteria"] * 100)
    return {"file": file.relative_to(ROOT).as_posix(), "pct": _history._cov_pct(d),
            "gaps": len(_history._gaps(d)), "by_story": by_story}


def bugs(r):
    items = rec.from_bugs(None)
    files = {Path(a).stem: os.path.getmtime(a) for a in glob.glob(str(ROOT / "output" / "bug-reports" / "BUG-*.md"))}
    for b in items:
        b["ts"] = files.get(b["id"]) or next((t for k, t in files.items() if k.startswith(b["id"])), None)
    open_ = [b for b in items if b["status"].lower() in rec.OPEN]
    in_period = [b for b in items if r == (None, None) or _in(b["ts"], r)]
    return {
        "total": len(items), "open": len(open_),
        "period_reported": len(in_period),
        "by_severity": {s: sum(1 for b in open_ if b["severity"] == s) for s in SEVERITIES},
        "by_story": dict(Counter(b["story"] for b in open_).most_common()),
        "open_critical": [{k: b[k] for k in ("id", "title", "severity", "story")} for b in open_
                          if b["severity"] in ("Critical", "High")],
    }


def failures():
    file = _most_recent("output/failures/*/failures.json")
    d = _json(file) if file else None
    if not isinstance(d, dict):
        return None
    pc = (d.get("summary") or {}).get("by_category") or {}
    return {"file": file.relative_to(ROOT).as_posix(), "failed": (d.get("summary") or {}).get("failed", 0),
            "flaky": pc.get("Flaky", 0), "possible_bugs": pc.get("Possible bug", 0), "by_category": pc}


def extras():
    out = {"accessibility": [], "web_performance": [], "performance": rec.from_performance(None), "security": rec.from_security(None)}
    for file in sorted(glob.glob(str(ROOT / "output" / "accessibility" / "*" / "audit.json"))):
        d = _json(file) or {}
        r = d.get("summary") or {}
        if r.get("compliance_pct") is not None:
            out["accessibility"].append({"site": Path(file).parent.name, "compliance": r.get("compliance_pct"),
                                         "critical": r.get("critical", 0)})
    for file in sorted(glob.glob(str(ROOT / "output" / "web-performance" / "*" / "web-performance.json"))):
        r = (_json(file) or {}).get("summary") or {}
        if r.get("web_performance_mobile") is not None or r.get("web_performance_desktop") is not None:
            out["web_performance"].append({"site": Path(file).parent.name, "mobile": r.get("web_performance_mobile"),
                                           "desktop": r.get("web_performance_desktop")})
    # Token usage (scripts/token_metrics.py): the most recent report of each name.
    out["tokens"] = []
    for file in sorted(glob.glob(str(ROOT / "output" / "token-metrics" / "*" / "metrics.json"))):
        d = _json(file) or {}
        r = d.get("summary") or {}
        if r.get("calls"):
            top = (d.get("agents") or [{}])[0]
            out["tokens"].append({"name": Path(file).parent.name, "period": d.get("period", ""), "cost_usd": r.get("cost_usd", 0),
                                  "pct_cache": r.get("pct_cache", 0), "top_agent": top.get("agent", "—")})
    return out


# ------------------------------------------------------------------ assembly
def collect(date_from=None, date_until=None):
    r = date_range(date_from, date_until)
    rns = runs(r)
    period = period_results(r)
    cases = inventory()
    cov = coverage()
    bg = bugs(r)
    fl = failures()
    ex = extras()

    automated = [c for c in cases if c.get("automated")]
    with_result = [c for c in cases if c.get("result")]
    flaky = [f'{c["story"]}:{c["id"]}' for c in cases if c.get("flaky")]
    manual = [c for c in cases if not c.get("automated")]
    executed = sum(period.values())

    stories = {}
    for c in cases:
        h = stories.setdefault(c["story"], {"story": c["story"], "cases": 0, "automated": 0, "passed": 0,
                                            "failed": 0, "blocked": 0, "not_run": 0, "flaky": 0,
                                            "manual_minutes": 0, "automated_minutes": 0, "auto_run_minutes": 0})
        h["cases"] += 1
        h["automated"] += bool(c.get("automated"))
        st = (c.get("result") or {}).get("status")
        h[{"Passed": "passed", "Failed": "failed", "Blocked": "blocked"}.get(st, "not_run")] += 1
        h["flaky"] += bool(c.get("flaky"))
        if c.get("automated"):
            # What it would cost by hand and now runs on its own (savings per run), and what it took automated.
            h["automated_minutes"] += c.get("manual_minutes") or 0
            h["auto_run_minutes"] += (c.get("duration_s") or 0) / 60
        else:
            h["manual_minutes"] += c.get("manual_minutes") or 0
    for us, h in stories.items():
        h["open_bugs"] = bg["by_story"].get(us, 0)
        h["coverage"] = (cov or {}).get("by_story", {}).get(us)
        h["manual_minutes"] = round(h["manual_minutes"], 1)
        h["automated_minutes"] = round(h["automated_minutes"], 1)
        h["auto_run_minutes"] = round(h["auto_run_minutes"], 1)
        h["savings_per_run"] = round(max(0, h["automated_minutes"] - h["auto_run_minutes"]), 1)

    summary = {
        "cases": len(cases), "stories": len(stories),
        "automated": len(automated),
        "pct_automated": round(len(automated) / len(cases) * 100) if cases else None,
        "executed_in_period": executed,
        "passed_in_period": period.get("Passed", 0), "failed_in_period": period.get("Failed", 0),
        "blocked_in_period": period.get("Blocked", 0),
        "pct_passed": round(period.get("Passed", 0) / executed * 100) if executed else None,
        "not_run": len(cases) - len(with_result),
        "coverage_pct": (cov or {}).get("pct"),
        "open_bugs": bg["open"], "open_critical_bugs": len(bg["open_critical"]),
        "flaky": len(flaky) or (fl or {}).get("flaky", 0),
        "manual_minutes": round(sum(c.get("manual_minutes") or 0 for c in manual), 1),
        # Automation savings: what running the automated cases by hand would cost, minus what they
        # take running on their own. It is per run (every time npm test runs, that time is saved).
        "automated_minutes": round(sum(c.get("manual_minutes") or 0 for c in automated), 1),
        "auto_run_minutes": round(sum((c.get("duration_s") or 0) / 60 for c in automated), 1),
        "runs": len(rns),
    }
    summary["savings_per_run"] = round(max(0, summary["automated_minutes"] - summary["auto_run_minutes"]), 1)
    # Estimated accumulated savings: the savings per run times the runs in the period.
    summary["cumulative_savings"] = round(summary["savings_per_run"] * len(rns), 1)
    if len(rns) >= 2:
        half = len(rns) // 2
        avg = lambda xs: sum(x["pct_passed"] for x in xs) / len(xs)
        summary["trend_pp"] = round(avg(rns[half:]) - avg(rns[:half]), 1)

    no_data = []
    if not rns:
        no_data.append("Runs (no live runs and no npm test in the period)")
    if not cases:
        no_data.append("Case inventory (there are no spreadsheets, BDD .feature files or automation)")
    if not cov:
        no_data.append("Criteria coverage (the coverage-analyst has not been run)")
    if not bg["total"]:
        no_data.append("Bugs (there are no reports in output/bug-reports/)")
    if not fl:
        no_data.append("Failure and flaky analysis (the failure-analyst has not been run)")
    for key, text in (("accessibility", "Accessibility"), ("web_performance", "Web performance"),
                      ("performance", "Performance"), ("security", "Security")):
        if not ex[key]:
            no_data.append(text)

    alerts = []
    for b in bg["open_critical"]:
        alerts.append({"type": "Open bug", "level": b["severity"], "title": f'{b["id"]} ({b["story"]}): {b["title"]}'})
    for i in flaky:
        alerts.append({"type": "Flaky", "level": "Medium", "title": f"{i} fails intermittently"})
    for h in stories.values():
        if h["failed"]:
            alerts.append({"type": "Failed", "level": "High", "title": f'{h["story"]}: {h["failed"]} case(s) failed in the latest run'})
        if h["cases"] >= 3 and not h["automated"]:
            alerts.append({"type": "Not automated", "level": "Low", "title": f'{h["story"]}: no automated case ({h["cases"]} cases)'})
        if h["coverage"] is not None and h["coverage"] < 80:
            alerts.append({"type": "Coverage", "level": "Medium", "title": f'{h["story"]}: {h["coverage"]}% of criteria covered'})
    for a in ex["accessibility"]:
        if a.get("critical"):
            alerts.append({"type": "Accessibility", "level": "High", "title": f'{a["site"]}: {a["critical"]} critical problem(s)'})

    return {
        "date": datetime.now().isoformat(timespec="seconds"),
        "period": {"from": date_from, "until": date_until},
        "summary": summary, "runs": rns,
        "stories": sorted(stories.values(), key=lambda h: h["story"]),
        "bugs": bg, "coverage": cov, "failures": fl, "extras": ex,
        "flaky": flaky, "alerts": alerts, "no_data": no_data,
    }


# ------------------------------------------------------------------ report
def build_html(data, analysis=None, hist_html=""):
    from _report_styles import (page, meta, section, kpi_tiles, table, banner, line_chart, donut_panel, bar_chart,
                                stacked_bars, two_col, doc_list, level_badge, e, SERIES, OK, CRITICAL, NEUTRAL, WARNING, LEVEL_COLOR)
    analysis = analysis or {}
    r = data["summary"]
    p = data.get("period") or {}
    period = (f'{p.get("from") or "the start"} to {p.get("until") or "today"}') if (p.get("from") or p.get("until")) else "everything recorded"
    pct = lambda v: "—" if v is None else f"{v}%"

    def fmt_min(m):
        """Minutes -> "45 min" or "2 h 30 min" so the savings can be read at a glance."""
        m = int(round(m or 0))
        if m < 60:
            return f"{m} min"
        h, r_ = divmod(m, 60)
        return f"{h} h {r_} min" if r_ else f"{h} h"

    body = []

    bad = r["open_critical_bugs"] or r["failed_in_period"]
    tone = analysis.get("verdict_tone") or ("bad" if r["open_critical_bugs"] else "warn" if bad or r["flaky"] else "ok")
    text = analysis.get("verdict") or (
        f'{pct(r["pct_passed"])} passed in the period, {pct(r["pct_automated"])} automated, '
        f'{r["open_bugs"]} open bug(s) ({r["open_critical_bugs"]} critical or high).')
    body.append(banner(text, tone))
    series = [c["pct_passed"] for c in data["runs"]][-12:]
    trend = r.get("trend_pp")
    body.append('<div style="margin-top:20px">' + kpi_tiles([
        ("Passed (period)", pct(r["pct_passed"]), "ok" if (r["pct_passed"] or 0) >= 95 else "warn" if (r["pct_passed"] or 0) >= 80 else "bad" if r["pct_passed"] is not None else "",
         f'{r["passed_in_period"]} of {r["executed_in_period"]} cases' + (f' · trend {trend:+} pp' if trend is not None else ""), "ok",
         {"series": series} if len(series) > 1 else {"pct": r["pct_passed"] or 0}),
        ("Automated", pct(r["pct_automated"]), "", f'{r["automated"]} of {r["cases"]} cases', "bolt", {"pct": r["pct_automated"] or 0}),
        ("Criteria coverage", pct(r["coverage_pct"]), "ok" if (r["coverage_pct"] or 0) >= 90 else "warn" if r["coverage_pct"] is not None else "",
         f'{(data.get("coverage") or {}).get("gaps", 0)} gap(s)' if data.get("coverage") else "no coverage analysis", "target",
         {"pct": r["coverage_pct"] or 0}),
        ("Open bugs", r["open_bugs"], "bad" if r["open_critical_bugs"] else "warn" if r["open_bugs"] else "ok",
         f'{r["open_critical_bugs"]} critical or high · {data["bugs"]["period_reported"]} reported in the period', "bug"),
        ("Flaky", r["flaky"], "warn" if r["flaky"] else "ok", "fail intermittently", "warn"),
        ("Not run", r["not_run"], "warn" if r["not_run"] else "", "cases without any result", "list"),
        ("Pending manual execution", fmt_min(r["manual_minutes"]), "", "what is not automated", "person"),
        ("Savings per run", fmt_min(r.get("savings_per_run")), "ok" if r.get("savings_per_run") else "",
         f'{fmt_min(r.get("automated_minutes"))} by hand vs {fmt_min(r.get("auto_run_minutes"))} automated', "bolt"),
        ("Accumulated savings", fmt_min(r.get("cumulative_savings")), "ok" if r.get("cumulative_savings") else "",
         f'{r["runs"]} run(s) in the period', "target"),
        ("Runs", r["runs"], "", "live and npm test in the period", "list"),
    ]) + "</div>")

    if analysis.get("summary"):
        body.append(section("Executive summary", f'<div class="cardbody"><p class="lead">{e(analysis["summary"])}</p></div>'))

    rns = data["runs"]
    if rns:
        labels = [c["date"][5:16] for c in rns]
        chart = line_chart(list(range(len(rns))), [("% passed", SERIES[0], [c["pct_passed"] for c in rns])],
                           fmt=lambda v: f"{v:.0f}%", fmt_x=lambda v: labels[min(len(labels) - 1, max(0, int(round(v))))])
        body.append(section("Pass rate trend", chart, f"{len(rns)} run(s) · {period}"))

    tot = r["passed_in_period"] + r["failed_in_period"] + r["blocked_in_period"]
    donut = (donut_panel([(r["passed_in_period"], OK, "Passed"), (r["failed_in_period"], CRITICAL, "Failed"),
                          (r["blocked_in_period"], NEUTRAL, "Blocked")], round(r["passed_in_period"] / tot * 100) if tot else 0, "passed")
             if tot else '<div class="cardbody"><p class="muted">There are no results in the period.</p></div>')
    sev = data["bugs"]["by_severity"]
    sev_bars = bar_chart([(s, sev.get(s, 0), LEVEL_COLOR.get(s, NEUTRAL)) for s in SEVERITIES])
    body.append(two_col(section("Period results", donut, period, width=6),
                        section("Open bugs by severity", sev_bars, f'{data["bugs"]["open"]} open of {data["bugs"]["total"]}', width=6)))

    hs = data["stories"]
    if hs:
        rows = [(h["story"], [h["passed"], h["failed"], h["blocked"], h["not_run"]]) for h in hs][:20]
        body.append(section("Latest result by story", stacked_bars(rows, [("Passed", OK), ("Failed", CRITICAL),
                                                                          ("Blocked", NEUTRAL), ("Not run", WARNING)])))
        notes = analysis.get("notes") or {}
        body.append(section("Detail by story", table(
            ["Story", "Cases", "Automated", "Passed", "Failed", "Not run", "Flaky", "Open bugs", "Coverage", "Pending manual", "Savings/run", "Note"],
            [[f'<b>{e(h["story"])}</b>', h["cases"], f'{h["automated"]} ({round(h["automated"] / h["cases"] * 100) if h["cases"] else 0}%)',
              h["passed"], h["failed"], h["not_run"], h["flaky"], h["open_bugs"],
              "—" if h["coverage"] is None else f'{h["coverage"]}%', fmt_min(h["manual_minutes"]),
              fmt_min(h.get("savings_per_run")), e(notes.get(h["story"], ""))] for h in hs])))

    if data["alerts"]:
        order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        body.append(section("Alerts", table(["Level", "Type", "Detail"],
                                            [[level_badge(a["level"]), e(a["type"]), e(a["title"])]
                                             for a in sorted(data["alerts"], key=lambda a: order.get(a["level"], 9))]),
                            "generated from the data, without interpretation"))

    ex = data["extras"]
    others = []
    if ex["accessibility"]:
        others.append(section("Accessibility", table(["Site", "Compliance", "Critical"],
                                                     [[e(a["site"]), f'{a["compliance"]}%', a["critical"]] for a in ex["accessibility"]]), width=6))
    if ex["web_performance"]:
        others.append(section("Web performance (Lighthouse)", table(["Site", "Mobile", "Desktop"],
                                                                    [[e(x["site"]), x["mobile"] if x["mobile"] is not None else "—",
                                                                      x["desktop"] if x["desktop"] is not None else "—"] for x in ex["web_performance"]]), width=6))
    if ex["performance"]:
        others.append(section("Performance", table(["Report", "Verdict", "Runs"],
                                                   [[e(x["report"]), e(x["verdict"]), x["runs"]] for x in ex["performance"]]), width=6))
    if ex["security"]:
        others.append(section("Security (ZAP)", table(["Scan", "High", "Medium", "Low"],
                                                      [[e(x["scan"]), x["findings"]["High"], x["findings"]["Medium"], x["findings"]["Low"]]
                                                       for x in ex["security"]]), width=6))
    if ex.get("tokens"):
        others.append(section("Token usage", table(["Metrics", "Period", "Estimated cost", "Cache", "Top-spending agent"],
                                                   [[e(x["name"]), e(x["period"]), f'${x["cost_usd"]:,.2f}', f'{x["pct_cache"]:.0f}%',
                                                     e(x["top_agent"])] for x in ex["tokens"]]), "scripts/token_metrics.py", width=6))
    for i in range(0, len(others), 2):
        body.append(two_col(*others[i:i + 2]) if i + 1 < len(others) else others[i])

    if analysis.get("risks"):
        body.append(section("Risks", table(["Level", "Risk", "Impact"],
                                           [[level_badge(x.get("level")), e(x.get("risk")), e(x.get("impact"))] for x in analysis["risks"]])))
    if analysis.get("recommendations"):
        body.append(section("Recommendations", table(["Priority", "Action", "Why"],
                                                     [[level_badge(x.get("priority")), e(x.get("action")), e(x.get("why"))]
                                                      for x in analysis["recommendations"]])))
    if analysis.get("next_steps"):
        body.append(section("Next steps", doc_list(analysis["next_steps"])))
    if data["no_data"]:
        body.append(section("No data", doc_list(data["no_data"]), "sources without information: they are not estimated"))
    if hist_html:
        body.append(hist_html)
    return page("Quality dashboard", "Dashboard", meta([("Period", period), ("Generated", data["date"][:16].replace("T", " ")),
                                                        ("Stories", r["stories"]), ("Cases", r["cases"])]), "".join(body))


def write_report(folder, data, analysis=None):
    hist = _history.section("dashboard", folder, data)
    (folder / "dashboard-report.html").write_text(build_html(data, analysis, hist), encoding="utf-8")


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Quality dashboard per sprint, release or date range")
    ap.add_argument("--name", help="dashboard name (sprint-12, release-2.4...); by default, the range or 'general'")
    ap.add_argument("--from", dest="date_from", help="YYYY-MM-DD (inclusive)")
    ap.add_argument("--until", dest="date_until", help="YYYY-MM-DD (inclusive)")
    ap.add_argument("--analysis", help="the agent's analysis.json (executive summary, risks, recommendations)")
    ap.add_argument("--report-only", action="store_true", help="regenerates the report with the data already collected")
    ap.add_argument("--root", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    for f in (a.date_from, a.date_until):
        if f and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", f):
            sys.exit("--from and --until must be YYYY-MM-DD")
    if a.root:
        use_root(a.root)
    name = a.name or ("-".join(x for x in (a.date_from, a.date_until) if x) or "general")
    name = re.sub(r"[^\w.-]+", "-", name).strip("-") or "general"
    folder = ROOT / "output" / "dashboard" / name
    folder.mkdir(parents=True, exist_ok=True)
    analysis = _json(a.analysis) if a.analysis else None
    if a.analysis and analysis is None:
        sys.exit(f"Could not read {a.analysis}")
    if a.report_only:
        data = _json(folder / "dashboard.json")
        if not data:
            sys.exit(f"There is no data in {folder}: run it first without --report-only")
    else:
        _history.archive(folder, GENERATED, "dashboard.json")
        data = collect(a.date_from, a.date_until)
        data["name"] = name
        (folder / "dashboard.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if analysis is not None:
        (folder / "analysis.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(folder, data, analysis)
    r = data["summary"]
    pct = lambda v: "—" if v is None else f"{v}%"
    print(f"Dashboard {name}: {pct(r['pct_passed'])} passed · {pct(r['pct_automated'])} automated · "
          f"coverage {pct(r['coverage_pct'])} · {r['open_bugs']} open bugs ({r['open_critical_bugs']} critical or high) · "
          f"{r['flaky']} flaky")
    if data["no_data"]:
        print("No data: " + "; ".join(data["no_data"]))
    print(f"Report: {(folder / 'dashboard-report.html').relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
