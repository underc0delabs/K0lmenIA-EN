#!/usr/bin/env python3
"""
Collects the results of a story (or of the whole round) from every k0lmenIA source,
so the closure report does not add anything up by hand.

Usage:
    python scripts/collect_results.py [--story US-001] [--output data.json]

Sources it reads (the ones that exist):
  - Live runs (e2e-runner / api-runner): output/runs/_results-*.json
  - k0lmena suites (npm test): tools/k0lmena/reports/{web,api,mobile}/cucumber-report.json and its
    history/ (each scenario counts by its most recent run: a run filtered with TAGS does not hide the rest)
    (only the scenarios with the story's @US tag, if one is given)
  - Bugs: output/bug-reports/BUG-*.md (severity, status and story)
  - Performance: output/performance/<US>/performance-report-*.json (+ run summaries)
  - Security: output/security/<US>/<date>/zap.json (+ analysis.json)

The same case (story + id: TCs are numbered per story) run several times counts only once:
its most recent result wins.
Statuses: Passed | Failed | Blocked (pending, skipped or undefined = Blocked).
Prints and saves a JSON with totals, detail per case, bugs and extras; generate_closure_report.py
takes it in the "data" field of the report JSON.
"""
import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
K0 = ROOT / "tools" / "k0lmena" / "reports"
SEVERITIES = ["Critical", "High", "Medium", "Low"]
OPEN = {"open", "in progress", "reopened", "no status"}


def _status(value):
    v = (value or "").strip().lower()
    if v in ("passed", "pass", "ok"):
        return "Passed"
    if v in ("failed", "fail", "ambiguous"):
        return "Failed"
    return "Blocked"


def from_runs(story):
    out = []
    for file in sorted(glob.glob(str(ROOT / "output" / "runs" / "_results-*.json"))):
        try:
            data = json.loads(Path(file).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if story and (data.get("story") or "").upper() != story:
            continue
        moment = os.path.getmtime(file)
        us = (data.get("story") or "").upper()
        for c in data.get("cases") or []:
            out.append({"id": c.get("id") or c.get("title"), "title": c.get("title", ""), "story": us,
                        "priority": c.get("priority", ""), "status": _status(c.get("status")), "source": f"live · {Path(file).name}",
                        "moment": moment, "missing_info": c.get("missing_info") or []})
    return out


def from_cucumber(story):
    """npm test scenarios: the current run and the previous ones in history/ (the last 5). A run
    filtered with TAGS does not erase the result of the other scenarios: each one counts by its most recent run
    (resolved by the collector, sorting by "moment")."""
    out = []
    for suite in ("web", "api", "mobile"):
        current = K0 / suite / "cucumber-report.json"
        for file in [current] + sorted((K0 / suite / "history").glob("*/cucumber-report.json")):
            if not file.exists():
                continue
            source = f"npm test · {suite}" if file == current else f"npm test · {suite} · history {file.parent.name}"
            try:
                features = json.loads(file.read_text(encoding="utf-8") or "[]")
            except ValueError:
                continue
            moment = os.path.getmtime(file)
            for feature in features:
                for sc in feature.get("elements", []):
                    if sc.get("type") == "background":
                        continue
                    tags = [t["name"].lstrip("@") for t in sc.get("tags", [])]
                    tags += [t["name"].lstrip("@") for t in feature.get("tags", [])]
                    if story and story not in {t.upper() for t in tags}:
                        continue
                    statuses = [(p.get("result") or {}).get("status", "undefined") for p in sc.get("steps", [])]
                    if any(s in ("failed", "ambiguous") for s in statuses):
                        status = "Failed"
                    elif statuses and all(s == "passed" for s in statuses):
                        status = "Passed"
                    else:
                        status = "Blocked"
                    tc = next((t for t in tags if re.match(r"^TC(-API)?-\d+$", t)), None)
                    us = next((t.upper() for t in tags if re.match(r"^US-\d+$", t, re.I)), "")
                    out.append({"id": tc or sc.get("name"), "title": sc.get("name", ""), "story": us, "status": status,
                                "source": source, "moment": moment,
                                "missing_info": [t for t in tags if re.match(r"^MI-\d+$", t, re.I)]})
    return out


def _field(text, name):
    m = re.search(rf"\*\*{name}[^*]*:\*\*\s*(.+)", text)
    return re.sub(r"[`*]", "", m.group(1)).strip() if m else ""


def from_bugs(story):
    bugs = []
    for file in sorted(glob.glob(str(ROOT / "output" / "bug-reports" / "BUG-*.md"))):
        text = Path(file).read_text(encoding="utf-8")
        us = _field(text, "Story").upper()
        if story and story not in us:
            continue
        sev_txt = _field(text, "Criticality / Severity") or _field(text, "Severity")
        severity = next((s for s in SEVERITIES if sev_txt.lower().startswith(s.lower())), "")
        status = _field(text, "Status").split("—")[0].split("(")[0].strip() or "No status"
        bugs.append({"id": _field(text, "ID").split()[0] if _field(text, "ID") else Path(file).stem,
                     "title": _field(text, "Title"), "severity": severity, "status": status,
                     "story": us or "—"})
    return bugs


def from_performance(story):
    pattern = ROOT / "output" / "performance" / (story or "*") / "performance-report-*.json"
    reports = []
    for file in sorted(glob.glob(str(pattern))):
        try:
            data = json.loads(Path(file).read_text(encoding="utf-8"))
        except ValueError:
            continue
        reports.append({"report": os.path.relpath(file, ROOT), "verdict": data.get("verdict", "—"),
                        "capacity": data.get("capacity", ""), "runs": len(data.get("runs") or [])})
    return reports


def from_security(story):
    scans = []
    for file in sorted(glob.glob(str(ROOT / "output" / "security" / (story or "*") / "*" / "zap.json"))):
        try:
            zap = json.loads(Path(file).read_text(encoding="utf-8"))
        except ValueError:
            continue
        analysis = Path(file).with_name("analysis.json")
        false_pos = set()
        if analysis.exists():
            try:
                false_pos = {str(f.get("pluginid")) for f in json.loads(analysis.read_text(encoding="utf-8")).get("false_positives") or []}
            except ValueError:
                pass
        count = {"High": 0, "Medium": 0, "Low": 0, "Informational": 0}
        for site in zap.get("site") or []:
            for a in site.get("alerts") or []:
                if str(a.get("pluginid")) in false_pos:
                    continue
                count[{3: "High", 2: "Medium", 1: "Low"}.get(int(a.get("riskcode", 0) or 0), "Informational")] += 1
        scans.append({"scan": os.path.relpath(Path(file).parent, ROOT), "findings": count})
    return scans


def case_key(r):
    """TCs are numbered per story: the same TC-001 of two stories are different cases."""
    return (r.get("story") or "", str(r["id"]))


def collect(story=None):
    story = story.upper() if story else None
    executed = from_runs(story) + from_cucumber(story)
    latest = {}
    for r in sorted(executed, key=lambda r: r["moment"]):
        latest[case_key(r)] = r  # the most recent one overrides the previous one
    cases = sorted(latest.values(), key=case_key)
    totals = {"passed": 0, "failed": 0, "blocked": 0}
    for c in cases:
        totals[c["status"].lower()] += 1
        c.pop("moment", None)
    bugs = from_bugs(story)
    by_sev = {s: sum(1 for b in bugs if b["severity"] == s) for s in SEVERITIES}
    open_bugs = [b for b in bugs if b["status"].lower() in OPEN and b["severity"] in ("Critical", "High")]
    return {
        "story": story or "whole round",
        "results": totals,
        "sources": sorted({c["source"] for c in cases}),
        "cases": cases,
        "bugs": {"by_severity": by_sev, "total": len(bugs),
                 "open": sum(1 for b in bugs if b["status"].lower() in OPEN),
                 "open_critical": [{"id": b["id"], "title": b["title"], "severity": b["severity"],
                                    "status": b["status"]} for b in open_bugs],
                 "no_status": [b["id"] for b in bugs if b["status"] == "No status"]},
        "performance": from_performance(story),
        "security": from_security(story),
    }


def main():
    ap = argparse.ArgumentParser(description="Collects the results of a story for the closure report")
    ap.add_argument("--story", help="US-XXX (if omitted, takes the whole round)")
    ap.add_argument("--output", help="output JSON file (by default, it is only printed)")
    a = ap.parse_args()
    if a.story and not re.match(r"^US-\d+$", a.story, re.I):
        sys.exit("--story must be an ID like US-001")
    data = collect(a.story)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if a.output:
        Path(a.output).parent.mkdir(parents=True, exist_ok=True)
        Path(a.output).write_text(text, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    t = data["results"]
    print(f"{data['story']}: {sum(t.values())} cases · {t['passed']} passed · {t['failed']} failed · "
          f"{t['blocked']} blocked · {data['bugs']['total']} bugs ({data['bugs']['open']} open) · "
          f"sources: {', '.join(data['sources']) or 'none'}")
    if a.output:
        print(f"Data: {a.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
