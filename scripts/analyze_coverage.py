#!/usr/bin/env python3
"""
Builds the coverage and traceability matrix of one or several stories for the
coverage-analyst agent: US → acceptance criteria → cases → automation → management → latest
result → bugs, and marks the gaps.

Usage (from the repo root):
    python scripts/analyze_coverage.py [--story US-001] [--criteria criteria.json]

Sources it reads (whichever exist; what is not there is not made up):
  - Criteria (AC1, AC2…): input/stories/*US-XXX*, output/context/context-US-XXX.md, the coverage
    tables (cases-US-XXX-coverage.md, US-XXX-coverage.md) and --criteria (JSON from the agent,
    e.g. read from Jira: {"US-001": [{"id": "AC1", "description": "..."}]}).
  - Manual cases: output/test-cases/manual/cases-US-XXX.xlsx (AC by @AC1 tag or mention).
  - BDD cases: output/test-cases/bdd/US-XXX*.feature (@TC-XXX, @AC1).
  - Automation: tools/k0lmena/{web,api,mobile}/features/**/*.feature with @US-XXX
    (@TC-XXX, @blocked, @missing-info).
  - Management: output/management/US-XXX-<tool>.json (which TC is which remote key).
  - Results: npm test (reports/<suite>/cucumber-report.json and its history/) and live runs; the
    most recent one of each case counts.
  - Bugs: output/bug-reports/BUG-*.md of the story (and the TCs they mention).
  - Missing information: MI-XX from the context sheet and from the cases.

Gaps it marks: criterion without cases, case without criterion, case not automated (by priority),
automated but blocked, automated without result, latest result failed, case not uploaded to the
management tool (if the story already uses one), open missing information.

Leaves output/coverage/<US or all>/coverage.json and coverage-report.html (the previous run moves to
history/).
"""
import argparse
import datetime
import glob
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "management"))
import collect_results as rec  # noqa: E402
import _history  # noqa: E402

RE_US = re.compile(r"\b(US-\d+)\b", re.I)
RE_AC = re.compile(r"\bAC-?(\d+)\b")
RE_TC = re.compile(r"\bTC(-API)?-\d+\b")
RE_MI = re.compile(r"\bMI-\d+\b")
SEV_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
PRIO_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}


def _ac(n):
    return f"AC{int(n)}"


def _read(p):
    try:
        return Path(p).read_text(encoding="utf-8-sig")
    except OSError:
        return ""


def criteria_from_text(text):
    """AC1: description · **AC1** — description · | AC1 | description | … (Markdown or ASCII tables)."""
    output = {}
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("|", "+")) or "|" in stripped:
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if cells and re.fullmatch(r"AC-?\d+", cells[0]):
                output.setdefault(_ac(RE_AC.match(cells[0]).group(1)), cells[1] if len(cells) > 1 else "")
            continue
        m = re.match(r"^[-*#\s]*\**\s*AC-?(\d+)\s*\**\s*[:.\-–—)]\s*\**\s*(.+)$", stripped)
        if m:
            output.setdefault(_ac(m.group(1)), re.sub(r"[*_`]", "", m.group(2)).strip())
    return output


def table_coverage(text):
    """From the coverage table (AC → cases that cover it): {AC: {TC…}}."""
    mapping = {}
    for line in text.splitlines():
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and re.fullmatch(r"AC-?\d+", cells[0]):
            ac = _ac(RE_AC.match(cells[0]).group(1))
            mapping.setdefault(ac, set()).update(m.group(0) for c in cells[1:] for m in RE_TC.finditer(c))
    return mapping


def present_stories():
    seen = set()
    patterns = ["input/stories/*", "output/context/context-*.md", "output/test-cases/manual/cases-*.xlsx",
                "output/test-cases/bdd/*.feature", "output/management/*.json"]
    for p in patterns:
        for a in glob.glob(str(ROOT / p)):
            seen.update(m.upper() for m in RE_US.findall(Path(a).name))
    for a in glob.glob(str(ROOT / "tools" / "k0lmena" / "*" / "features" / "**" / "*.feature"), recursive=True):
        seen.update(m.upper() for m in RE_US.findall(_read(a)))
    return sorted(seen, key=lambda h: int(h.split("-")[1]))


def _features_with_tag(pattern, us):
    """Scenarios (readers.read_feature) of the .feature files that have the @US-XXX tag."""
    from readers import read_feature
    output = []
    for a in sorted(glob.glob(str(ROOT / pattern), recursive=True)):
        text = _read(a)
        if not re.search(rf"@{us}\b", text, re.I) and us.lower() not in Path(a).name.lower():
            continue
        try:
            for c in read_feature(a):
                tags = [t.upper() for t in c["tags"]]
                if f"{us}" in tags or us.lower() in Path(a).name.lower():
                    c["_file"] = Path(a).relative_to(ROOT).as_posix()
                    output.append(c)
        except Exception:  # a .feature without scenarios or malformed does not stop the analysis
            continue
    return output


def analyze_story(us, extra_criteria):
    # ---- criteria
    criteria, ac_origin = {}, []
    ac_sources = sorted(glob.glob(str(ROOT / "input" / "stories" / f"*{us}*"))) + [str(ROOT / "output" / "context" / f"context-{us}.md")]
    for a in ac_sources:
        new = criteria_from_text(_read(a))
        if new:
            ac_origin.append(Path(a).relative_to(ROOT).as_posix())
        for k, v in new.items():
            criteria.setdefault(k, v)
    cov = {}
    tables = glob.glob(str(ROOT / "output" / "test-cases" / "manual" / f"cases-{us}-coverage.md")) + \
        glob.glob(str(ROOT / "output" / "test-cases" / "bdd" / f"{us}-coverage.md"))
    for a in tables:
        text = _read(a)
        for k, v in criteria_from_text(text).items():
            criteria.setdefault(k, v)
        for k, tcs in table_coverage(text).items():
            cov.setdefault(k, set()).update(tcs)
        ac_origin.append(Path(a).relative_to(ROOT).as_posix())
    for c in extra_criteria.get(us, []):
        criteria.setdefault(_ac(RE_AC.search(c["id"]).group(1)), c.get("description", ""))
    if extra_criteria.get(us):
        ac_origin.append("--criteria (agent)")

    # ---- manual and BDD cases
    cases = {}

    def case(cid):
        return cases.setdefault(cid, {"id": cid, "title": "", "priority": "", "sources": [], "criteria": set(),
                                      "automated": [], "management": {}, "result": None, "bugs": [], "missing_info": set()})

    xlsx = ROOT / "output" / "test-cases" / "manual" / f"cases-{us}.xlsx"
    if xlsx.exists():
        from readers import read_xlsx
        try:
            for c in read_xlsx(xlsx):
                x = case(c["id"])
                x["title"] = x["title"] or c["title"]
                x["priority"] = x["priority"] or c["priority"]
                x["sources"].append("Manual")
                text = " ".join([c.get("description", ""), " ".join(c.get("tags") or [])])
                x["criteria"].update(_ac(n) for n in RE_AC.findall(text))
                x["missing_info"].update(RE_MI.findall(" ".join(c.get("tags") or [])))
        except Exception as ex:  # spreadsheet in another format: reported, does not stop
            print(f"[!] Could not read {xlsx.name}: {ex}", file=sys.stderr)
    for c in _features_with_tag(f"output/test-cases/bdd/{us}*.feature", us) + \
            [x for x in _features_with_tag("output/test-cases/bdd/*.feature", us) if us.lower() not in x["_file"].lower()]:
        if not RE_TC.fullmatch(c["id"]):
            continue
        x = case(c["id"])
        x["title"] = x["title"] or c["title"]
        x["priority"] = x["priority"] or c["priority"]
        if "BDD" not in x["sources"]:
            x["sources"].append("BDD")
        x["criteria"].update(_ac(n) for n in RE_AC.findall(" ".join(c["tags"])))
    for ac, tcs in cov.items():
        for tc in tcs:
            case(tc)["criteria"].add(ac)

    # ---- automation in k0lmena
    without_tc = []
    for suite in ("web", "api", "mobile"):
        for c in _features_with_tag(f"tools/k0lmena/{suite}/features/**/*.feature", us):
            tags = [t.lower() for t in c["tags"]]
            if not RE_TC.fullmatch(c["id"]):
                without_tc.append({"suite": suite, "scenario": c["title"], "file": c["_file"]})
                continue
            x = case(c["id"])
            x["title"] = x["title"] or c["title"]
            x["automated"].append({"suite": suite, "file": c["_file"], "blocked": "blocked" in tags,
                                   "missing_info": "missing-info" in tags})
            x["criteria"].update(_ac(n) for n in RE_AC.findall(" ".join(c["tags"])))
            x["missing_info"].update(t.upper() for t in c["tags"] if re.fullmatch(r"MI-\d+", t, re.I))

    # ---- management
    management_tools = []
    for a in sorted(glob.glob(str(ROOT / "output" / "management" / f"{us}-*.json"))):
        try:
            t = json.loads(_read(a))
        except ValueError:
            continue
        tool = t.get("tool") or Path(a).stem.split("-", 2)[-1]
        management_tools.append(tool)
        for tc, v in (t.get("cases") or {}).items():
            case(tc)["management"][tool] = v.get("key") or v.get("id")

    # ---- results (the most recent wins)
    for r in sorted(rec.from_runs(us) + rec.from_cucumber(us), key=lambda r: r.get("moment") or 0):
        if r.get("id") and RE_TC.fullmatch(str(r["id"])):
            case(r["id"])["result"] = {"status": r["status"], "source": r["source"],
                                       "date": datetime.datetime.fromtimestamp(r["moment"]).isoformat(timespec="minutes") if r.get("moment") else ""}

    # ---- bugs
    bugs = []
    for b in rec.from_bugs(us):
        file = ROOT / "output" / "bug-reports" / f'{b["id"]}.md'
        tcs = sorted(set(m.group(0) for m in RE_TC.finditer(_read(file)))) if file.exists() else []
        b["cases"] = tcs
        bugs.append(b)
        for tc in tcs:
            if tc in cases:
                cases[tc]["bugs"].append(b["id"])

    # ---- missing information (context sheet)
    sheet = _read(ROOT / "output" / "context" / f"context-{us}.md")
    open_mi = sorted({m for line in sheet.splitlines() for m in RE_MI.findall(line)
                      if re.search(r"open|pending|abiert|pendiente", line, re.I)})

    # ---- gaps
    gaps = []

    def gap(type_, sev, detail, ref=""):
        gaps.append({"type": type_, "severity": sev, "detail": detail, "ref": ref})

    with_cases = {ac for x in cases.values() for ac in x["criteria"]}
    for ac, desc in sorted(criteria.items(), key=lambda kv: int(kv[0][2:])):
        if ac not in with_cases:
            gap("Criterion without cases", "High", f"{ac}: {desc}" if desc else ac, ac)
    for x in sorted(cases.values(), key=lambda x: x["id"]):
        prio = x["priority"] or "Medium"
        if criteria and not x["criteria"]:
            gap("Case without criterion", "Low", f'{x["id"]} · {x["title"]}: unknown which criterion it covers', x["id"])
        active = [a for a in x["automated"] if not a["blocked"]]
        if not x["automated"] and x["sources"]:
            gap("Not automated", "Medium" if PRIO_ORDER.get(prio, 2) <= 1 else "Low",
                f'{x["id"]} · {x["title"]} (priority {prio})', x["id"])
        elif x["automated"] and not active:
            gap("Automated but blocked", "Medium", f'{x["id"]} · {x["title"]}: has @blocked, it does not run', x["id"])
        if active and not x["result"]:
            gap("Automated without result", "Medium", f'{x["id"]} · {x["title"]}: does not appear in any run', x["id"])
        if x["result"] and x["result"]["status"] == "Failed":
            gap("Latest result failed", "High", f'{x["id"]} · {x["title"]} ({x["result"]["source"]})', x["id"])
        if management_tools and not x["management"] and x["sources"]:
            gap("Not uploaded to management", "Low", f'{x["id"]} · {x["title"]}: not in {", ".join(management_tools)}', x["id"])
    for mi in open_mi:
        gap("Open missing information", "Medium", f"{mi}: no answer in the context sheet", mi)
    for s in without_tc:
        gap("Scenario without @TC", "Low", f'{s["scenario"]} ({s["suite"]}, {s["file"]}): cannot be traced', s["file"])
    gaps.sort(key=lambda h: SEV_ORDER[h["severity"]])

    items = []
    for x in sorted(cases.values(), key=lambda x: (int(re.sub(r"\D", "", x["id"]) or 0))):
        x["criteria"] = sorted(x["criteria"], key=lambda c: int(c[2:]))
        x["missing_info"] = sorted(x["missing_info"])
        items.append(x)
    n = len(items)
    automated = [x for x in items if any(not a["blocked"] for a in x["automated"])]
    with_res = [x for x in items if x["result"]]
    passed = [x for x in with_res if x["result"]["status"] == "Passed"]
    return {
        "story": us, "criteria_source": ac_origin, "management_tools": management_tools,
        "criteria": [{"id": k, "description": v, "cases": sorted(x["id"] for x in items if k in x["criteria"])}
                     for k, v in sorted(criteria.items(), key=lambda kv: int(kv[0][2:]))],
        "cases": items, "bugs": bugs, "open_missing_info": open_mi, "scenarios_without_tc": without_tc, "gaps": gaps,
        "metrics": {
            "criteria": len(criteria), "covered_criteria": len([c for c in criteria if c in with_cases]),
            "cases": n, "automated": len(automated), "with_result": len(with_res), "passed": len(passed),
            "failed": len([x for x in with_res if x["result"]["status"] == "Failed"]),
            "open_bugs": len([b for b in bugs if b["status"].lower() in rec.OPEN]),
        },
    }


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Coverage and traceability matrix per story")
    ap.add_argument("--story", help="US-XXX (by default, every one it finds)")
    ap.add_argument("--criteria", help='JSON {"US-001": [{"id": "AC1", "description": "..."}]} (e.g., read from Jira)')
    ap.add_argument("--output", help="folder (by default output/coverage/<US or all>)")
    ap.add_argument("--analysis", help="the agent's analysis.json (by default, the one in the folder if it exists)")
    ap.add_argument("--report-only", action="store_true", help="regenerates the report with the analysis, without recalculating")
    ap.add_argument("--root", help=argparse.SUPPRESS)  # another project root (tests and demos)
    a = ap.parse_args()
    if a.root:
        global ROOT
        ROOT = Path(a.root).resolve()
        rec.ROOT, rec.K0 = ROOT, ROOT / "tools" / "k0lmena" / "reports"
    us = a.story.upper() if a.story else None
    if us and not re.fullmatch(r"US-\d+", us):
        sys.exit("--story must be an ID like US-001.")
    folder = Path(a.output) if a.output else ROOT / "output" / "coverage" / (us or "all")
    folder.mkdir(parents=True, exist_ok=True)
    data_file = folder / "coverage.json"
    if not a.report_only:
        _history.archive(folder, ["coverage.json", "analysis.json", "coverage-report.html"], "coverage.json")
        extra = json.loads(Path(a.criteria).read_text(encoding="utf-8")) if a.criteria else {}
        stories = [us] if us else present_stories()
        if not stories:
            sys.exit("Found no stories (US-XXX) in input/, output/ or in the k0lmena automation.")
        data = {"date": datetime.datetime.now().isoformat(timespec="seconds"), "scope": us or "all",
                "stories": [analyze_story(h, extra) for h in stories]}
        # Gap IDs unique across the whole report (C-01, C-02…), the most severe first.
        everything = sorted((x for h in data["stories"] for x in h["gaps"]), key=lambda x: SEV_ORDER[x["severity"]])
        for i, x in enumerate(everything):
            x["id"] = f"C-{i + 1:02d}"
        data_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        (folder / "analysis.json").unlink(missing_ok=True) if not a.analysis else None
        for h in data["stories"]:
            m = h["metrics"]
            print(f'{h["story"]}: criteria {m["covered_criteria"]}/{m["criteria"]} · cases {m["cases"]} · automated {m["automated"]}'
                  f' · with result {m["with_result"]} · passed {m["passed"]} · gaps {len(h["gaps"])}')
    args = [sys.executable, str(Path(__file__).resolve().parent / "generate_coverage_report.py"), str(data_file), str(folder / "coverage-report.html")]
    analysis = Path(a.analysis) if a.analysis else folder / "analysis.json"
    if analysis.exists():
        args += ["--analysis", str(analysis)]
    r = subprocess.run(args, capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip())


if __name__ == "__main__":
    main()
