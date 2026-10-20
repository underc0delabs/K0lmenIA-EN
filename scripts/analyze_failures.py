#!/usr/bin/env python3
"""
Analyzes the failed scenarios of a k0lmena run (`npm test`) for the failure-analyst agent:
classifies them by probable cause, detects the flaky ones by comparing with retries, rescues
the evidence (screenshot, video and trace) and generates the HTML report.

Usage (from the repo root):
    python scripts/analyze_failures.py [--story US-001] [--suites web,api,mobile]
        → takes the current run (tools/k0lmena/reports/<suite>/cucumber-report.json) as
          run 1, REPLACES the previous analysis and generates output/failures/<US or suite>/failures-report.html
    python scripts/analyze_failures.py --add-retry --suites web [--story US-001]
        → after re-running the failed ones (npm test -- web with TAGS=@TC-001 or …), adds the current run
          of those suites as a retry and recalculates: what failed and then passed ends up as Flaky.
          Pass only the retried suites: the others stay in the analysis with their previous runs.
    python scripts/analyze_failures.py --report-only [--analysis analysis.json]
        → regenerates the report (with the agent's analysis) without touching the runs.

Categories (heuristic over the error and the status of the steps; the agent confirms or corrects it):
  Possible bug · Locator or wait · Environment · Test data · Automation error ·
  Undefined step · Flaky · Unclassified

Leaves in output/failures/<US or suite>/: failures.json, runs/ (a copy of each cucumber-report.json),
evidence/ (screenshots, videos and traces of the failed ones) and failures-report.html.
"""
import argparse
import base64
import datetime
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import _history  # noqa: E402
K0 = ROOT / "tools" / "k0lmena" / "reports"
SUITES = ["web", "api", "mobile"]

# (category, pattern, suggestion). Order matters: the first one that matches wins.
RULES = [
    ("Environment", r"ECONNREFUSED|ENOTFOUND|EAI_AGAIN|ECONNRESET|ECONNABORTED|ERR_NAME_NOT_RESOLVED|ERR_CONNECTION|ERR_INTERNET|"
                    r"net::ERR_|socket hang up|\b50[234]\b|Service Unavailable|Bad Gateway|Gateway Time-?out|ERR_CERT|certificate|"
                    r"browserType\.launch|Executable doesn't exist|session not created|Could not start a new session|Appium.*(not running|ECONN)",
     "The system or the infrastructure did not respond. Check that the environment is up and run again; if it repeats, it is an environment problem, not a test problem."),
    ("Test data", r"already exists|ya existe|duplicad|duplicate|\b409\b|Conflict|unique constraint|violates|no hay datos|no data found|not found in (db|database)",
     "The data the test uses already exists or does not exist. Review the data setup and cleanup (or use unique data per run)."),
    ("Automation error", r"TypeError|ReferenceError|SyntaxError|Cannot read propert|is not a function|is not defined|"
                         r"Cannot find module|undefined is not",
     "The automation code (steps or helpers) fails, not the application. Review the step shown in the stack."),
    ("Locator or wait", r"TimeoutError|Timeout \d+ ?ms exceeded|waiting for (locator|selector|element)|locator\.|strict mode violation|"
                        r"element is not (visible|attached|enabled|stable)|No node found|outside of the viewport|"
                        r"element\(s\) not found|no such element|stale element|Unable to locate",
     "An element was not found or could not be used in time. It may be a change in the screen (locator to update), a short wait or a bug that prevents it from appearing: look at the screenshot."),
    ("Possible bug", r"AssertionError|expect\(|Expected|Received|toBe|toEqual|toContain|toHave|esperaba|se esperaba|"
                     r"status code|status \d{3}|assert",
     "The application responded differently than expected. If the expected result of the case is correct, it is a bug: write it up with the evidence."),
]
SUGGESTION = {r[0]: r[2] for r in RULES}
SUGGESTION.update({
    "Undefined step": "The scenario has unimplemented, ambiguous or pending steps: the automation needs to be completed (web-mapper / api-mapper).",
    "Flaky": "It failed and then passed with no changes: the test depends on timing, order or shared data. It has to be stabilized (waits, data isolation) before trusting it.",
    "Unclassified": "The error does not match a known pattern: review it by hand with the evidence.",
})
CATEGORIES = ["Possible bug", "Flaky", "Locator or wait", "Environment", "Test data",
              "Automation error", "Undefined step", "Unclassified"]


def classify(error, step_statuses):
    """(category, text that matched) from the error message and the step statuses."""
    if not error and any(s in ("undefined", "ambiguous", "pending") for s in step_statuses):
        return "Undefined step", next(s for s in step_statuses if s in ("undefined", "ambiguous", "pending"))
    for category, pattern, _ in RULES:
        m = re.search(pattern, error or "", re.I)
        if m:
            return category, m.group(0)
    return "Unclassified", ""


def read_report(file, suite, story=None):
    """cucumber-report.json → {key: scenario} with its status, the step that failed, the error and the evidence."""
    try:
        features = json.loads(Path(file).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    output = {}
    for f in features or []:
        for sc in f.get("elements") or []:
            if sc.get("type") == "background":
                continue
            tags = list(dict.fromkeys(t["name"].lstrip("@") for t in (f.get("tags") or []) + (sc.get("tags") or [])))
            us = next((t for t in tags if re.match(r"^US-\d+$", t, re.I)), None)
            if story and (us or "").upper() != story:
                continue
            tc = next((t for t in tags if re.match(r"^TC(-API)?-\d+$", t)), None)
            statuses, error, step, dur, screenshots, videos, traces, doms, texts, url = [], "", None, 0, [], [], [], [], [], None
            for p in sc.get("steps") or []:
                res = p.get("result") or {}
                st = res.get("status", "undefined")
                if p.get("keyword", "").strip() not in ("Before", "After"):
                    statuses.append(st)
                dur += res.get("duration") or 0
                if st in ("failed", "undefined", "ambiguous", "pending") and step is None:
                    step = f'{p.get("keyword", "").strip()} {p.get("name", "")}'.strip() or "(hook)"
                if st == "failed" and not error:
                    error = re.sub(r"\x1b\[[0-9;]*m", "", res.get("error_message") or "").strip()
                for emb in p.get("embeddings") or []:
                    mime, data = emb.get("mime_type", ""), emb.get("data", "")
                    try:
                        raw = base64.b64decode(data)
                    except (ValueError, TypeError):
                        continue
                    if mime == "image/png":
                        screenshots.append(raw)
                    elif mime == "text/html":
                        h = raw.decode("utf-8", "replace")
                        videos += re.findall(r'<video[^>]*src="([^"]+)"', h)
                    elif mime == "text/plain":
                        t = raw.decode("utf-8", "replace")
                        traces += re.findall(r"TRACE:\s*(\S+)", t)
                        doms += re.findall(r"^DOM:[ \t]*([^\r\n]+)", t, re.M)  # DOM on failure (for the repairer)
                        u = re.search(r"- URL:\s*(\S+)", t)
                        url = url or (u.group(1) if u else None)
                        texts.append(t)
            if "failed" in statuses or "ambiguous" in statuses:
                status = "Failed"
            elif statuses and all(s == "passed" for s in statuses):
                status = "Passed"
            elif any(s in ("undefined", "pending") for s in statuses):
                status = "Failed"
            else:
                status = "Skipped"
            # If the error came in a hook (After), the detail stays in the text attachments.
            if status == "Failed" and not error:
                error = next((t for t in texts if t.startswith("ERROR") or "Error" in t[:80]), "")
            key = f'{suite}:{f.get("uri", "")}:{sc.get("line")}:{sc.get("name")}'
            output[key] = {
                "key": key, "suite": suite, "feature": f.get("name", ""), "uri": f.get("uri", ""), "line": sc.get("line"),
                "scenario": sc.get("name", ""), "tags": tags, "story": us, "case": tc, "status": status,
                "step_statuses": statuses, "failed_step": step, "error": error[:4000], "duration_s": round(dur / 1e9, 2),
                "url": url, "_screenshots": screenshots, "_videos": videos, "_traces": traces, "_doms": doms,
            }
    return output


def _copy_evidence(r, report_base, ev_dir, prefix):
    """Writes the embedded screenshots and copies videos and traces (the next npm test overwrites them)."""
    ev = []
    name = re.sub(r"[^\w.-]+", "_", f'{r.get("case") or ""}-{r["scenario"]}')[:70].strip("_")
    for n, png in enumerate(r.pop("_screenshots", [])):
        file = ev_dir / f"{prefix}-{name}-{hashlib.md5(png).hexdigest()[:6]}-{n}.png"
        file.write_bytes(png)
        ev.append({"type": "screenshot", "file": file})
    for type_, key in (("video", "_videos"), ("trace", "_traces"), ("dom", "_doms")):
        for src in r.pop(key, []):
            clean = src.replace("../", "")
            target = ev_dir / f"{prefix}-{Path(clean).name}"
            if target.exists():  # already copied in a previous analysis (the new npm test may have overwritten the original)
                ev.append({"type": type_, "file": target})
                continue
            for cand in (report_base / clean, report_base / "html" / clean):
                if cand.exists():
                    shutil.copy2(cand, target)
                    ev.append({"type": type_, "file": target})
                    break
    return ev


def analyze(folder, story, suites):
    runs_dir = folder / "runs"
    ev_dir = folder / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)
    meta = json.loads((folder / "runs.json").read_text(encoding="utf-8"))
    rel = lambda p: Path(p).relative_to(folder).as_posix()
    history = {}  # key → [status per run]
    last = {}     # key → the record of the latest failure (with its evidence)
    for i, run in enumerate(meta["runs"]):
        for suite in suites:
            file = runs_dir / f'{run["id"]}-{suite}.json'
            if not file.exists():
                continue
            for key, r in read_report(file, suite, story).items():
                history.setdefault(key, [None] * len(meta["runs"]))[i] = r["status"]
                if r["status"] != "Failed":
                    continue
                evid = _copy_evidence(r, Path(run["origin"][suite]).parent, ev_dir, run["id"])
                r["evidence"] = [{"type": x["type"], "file": rel(x["file"])} for x in evid]
                r["run"] = run["id"]
                last[key] = r
    failures, total, passed = [], len(history), 0
    for key, hist in history.items():
        statuses = [s for s in hist if s]
        if "Failed" not in statuses:
            passed += 1 if statuses and statuses[-1] == "Passed" else 0
            continue
        r = last[key]
        category, match = classify(r["error"], r["step_statuses"])
        if "Passed" in statuses:  # failed and passed in another run: flaky
            category, match = "Flaky", " / ".join(s or "—" for s in hist)
        r.update({"history": hist, "category": category, "match": match, "suggestion": SUGGESTION[category],
                  "final_status": statuses[-1]})
        failures.append(r)
    failures.sort(key=lambda r: (CATEGORIES.index(r["category"]), r["suite"], r["uri"], r["line"] or 0))
    for i, r in enumerate(failures):
        r["id"] = f"F-{i + 1:02d}"
        r.pop("step_statuses", None)
    count = {c: sum(1 for r in failures if r["category"] == c) for c in CATEGORIES}
    return {
        "story": story, "date": datetime.datetime.now().isoformat(timespec="seconds"),
        "suites": [s for s in suites if any(s in c.get("suites", []) for c in meta["runs"])],
        "runs": meta["runs"],
        "summary": {"scenarios": total, "passed": passed, "failed": len(failures),
                    "still_failing": sum(1 for r in failures if r["final_status"] == "Failed"),
                    "by_category": {c: n for c, n in count.items() if n},
                    "by_suite": {s: sum(1 for r in failures if r["suite"] == s) for s in suites if any(r["suite"] == s for r in failures)}},
        "failures": failures,
    }


def capture_run(folder, suites, label, source_dir=K0):
    meta_file = folder / "runs.json"
    meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {"runs": []}
    cid = f"c{len(meta['runs']) + 1}"
    origin, copied = {}, []
    (folder / "runs").mkdir(parents=True, exist_ok=True)
    for suite in suites:
        rep = Path(source_dir) / suite / "cucumber-report.json"
        if rep.exists():
            shutil.copy2(rep, folder / "runs" / f"{cid}-{suite}.json")
            origin[suite] = str(rep)
            copied.append(suite)
    if not copied:
        sys.exit("Found no npm test results (tools/k0lmena/reports/<web|api|mobile>/cucumber-report.json). "
                 "Run npm test first.")
    moment = datetime.datetime.fromtimestamp(max(Path(origin[s]).stat().st_mtime for s in copied)).isoformat(timespec="seconds")
    meta["runs"].append({"id": cid, "label": label, "suites": copied, "origin": origin, "date": moment})
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return cid, copied


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Failure analysis of npm test (k0lmena)")
    ap.add_argument("--story", help="US-XXX: only the scenarios with that tag")
    ap.add_argument("--suites", default="web,api,mobile")
    ap.add_argument("--add-retry", action="store_true", help="adds the current run as a retry")
    ap.add_argument("--report-only", action="store_true", help="regenerates the report without touching the runs")
    ap.add_argument("--analysis", help="the agent's analysis.json (by default, the one in the folder if it exists)")
    ap.add_argument("--output", help="folder (by default output/failures/<US or suite>)")
    ap.add_argument("--reports", default=str(K0), help="folder with <suite>/cucumber-report.json (by default the k0lmena one)")
    a = ap.parse_args()
    story = a.story.upper() if a.story else None
    if story and not re.match(r"^[A-Z]+-\d+$", story):
        sys.exit("--story must be an ID like US-001.")
    suites = [s.strip() for s in a.suites.split(",") if s.strip() in SUITES]
    folder = Path(a.output) if a.output else ROOT / "output" / "failures" / (story or "suite")

    if not a.add_retry and not a.report_only:
        # New run: the previous analysis moves to history/<date>/ (the last 5 are kept).
        _history.archive(folder, ["runs", "evidence", "runs.json", "failures.json", "analysis.json", "failures-report.html"], "failures.json")
        for name in ("runs", "evidence", "runs.json", "failures.json", "analysis.json", "failures-report.html"):
            p = folder / name
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
        folder.mkdir(parents=True, exist_ok=True)
        cid, copied = capture_run(folder, suites, "Original run", a.reports)
        where = folder.resolve()
        where = where.relative_to(ROOT).as_posix() if where.is_relative_to(ROOT) else str(where)
        print(f"Original run ({', '.join(copied)}) saved in {where}")
    elif a.add_retry:
        if not (folder / "runs.json").exists():
            sys.exit("There is no previous analysis in that folder: run first without --add-retry.")
        cid, copied = capture_run(folder, suites, "Retry", a.reports)
        print(f"Retry {cid} ({', '.join(copied)}) added")
    if not (folder / "runs.json").exists():
        sys.exit("There are no saved runs in that folder.")
    # All saved suites are analyzed: a retry of a single suite (--suites web) does not take the others out of the analysis.
    saved = {x for c in json.loads((folder / "runs.json").read_text(encoding="utf-8"))["runs"] for x in c.get("suites", [])}
    data = analyze(folder, story, [x for x in SUITES if x in saved] or suites)
    (folder / "failures.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    r = data["summary"]
    print(f'Scenarios: {r["scenarios"]} · passed: {r["passed"]} · with failures: {r["failed"]} (still failing: {r["still_failing"]})')
    for c, n in r["by_category"].items():
        print(f"  {c}: {n}")
    args = [sys.executable, str(ROOT / "scripts" / "generate_failures_report.py"), str(folder / "failures.json"), str(folder / "failures-report.html")]
    analysis = Path(a.analysis) if a.analysis else folder / "analysis.json"
    if analysis.exists():
        args += ["--analysis", str(analysis)]
    res = subprocess.run(args, capture_output=True, text=True)
    print(res.stdout.strip() or res.stderr.strip())


if __name__ == "__main__":
    main()
