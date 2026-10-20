#!/usr/bin/env python3
"""
Reviews the quality of test cases that already exist (case-reviewer agent): manual case spreadsheets
(.xlsx from generate_cases.py) and BDD scenarios (.feature), and builds the report with a score per case.

Usage (from the repo root):
    python scripts/review_cases.py [--story US-001] [--source cases.xlsx,scenarios.feature,...] [--name review-sprint-5]
    python scripts/review_cases.py --report-only --name US-001      → applies the agent's analysis.json and regenerates

Without --source it takes the ones of the story (output/test-cases/manual/cases-US-XXX.xlsx and bdd/US-XXX*.feature)
or, without a story, all the ones in output/test-cases/.

What it reviews (each issue with its severity; the case score is 100 minus High 25 · Medium 10 · Low 4):
  - Manual: no expected result, vague result ("works correctly"), vague steps ("verify that it
    works", "etc."), steps without a clear action, non-descriptive title, too many steps (or a single one), data
    written inside the steps instead of in Test Data, missing preconditions (the step assumes a
    state), no priority, a case that verifies too many things.
  - BDD: scenario without Then, Then without a concrete verification, imperative UI steps (click on the button,
    selectors), broken Given/When/Then order, Scenario Outline without Examples, no @TC-XXX.
  - Across cases: possible duplicates (very similar steps and title).
  - Per story: no negative or edge cases.
It also calculates the estimated manual execution time of each case (scripts/estimation.py).

Leaves output/case-review/<US or name>/ with review.json and review-report.html; the previous review
moves to history/ (the last 5 are kept).
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
import _history  # noqa: E402
from estimation import estimate_case, format_time, NEGATIVE  # noqa: E402

WEIGHT = {"High": 25, "Medium": 10, "Low": 4}
SEV_ORDER = {"High": 0, "Medium": 1, "Low": 2}
VAGUE_RESULT = re.compile(r"\bworks? (correctly|properly|fine|well|ok)|correctly\s*\.?$|everything (is )?(fine|ok|correct)|(with no|without) errors\s*\.?$|"
                          r"as expected|the expected (result|behavior)|\bok\b\s*\.?$|successfully\s*\.?$", re.I)
VAGUE_STEP = re.compile(r"verif\w* (that )?(it )?(works|is (fine|ok|correct))|check\w* (that )?(it|everything) works|test\w* the (functionality|system|screen)\b|"
                        r"\betc\b|\band/or\b|as (appropriate|applicable|needed)|validat\w* everything|\bthings\b|\bstuff\b", re.I)
VERB = re.compile(r"^\s*(?:the user |the customer |user |)?(go|navigat|access|open|enter|visit|do\b|does\b|click|press|tap|push|select|choos|pick|check|uncheck|mark|complet|fill|writ|typ|input|load|"
                  r"attach|upload|download|export|import|print|wait|receiv|review|verif|validat|confirm|observ|consult|search|look|filter|sort|add|remov|delet|edit|modif|"
                  r"sav|send|submit|accept|cancel|clos|start|log|sign|register|buy|purchas|pay|return|refresh|reload|scroll|drag|copy|past|chang|activat|deactivat|enabl|disabl|leav|"
                  r"set|switch|hover|toggl|expand|collaps|insert|creat)", re.I)
FIXED_DATA = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b|\"[^\"]{3,}\"", re.I)
PREVIOUS_STATUS = re.compile(r"(being|while|with (the|a|an|his|her|their) (user|session|account) (logged|signed|started|active)|logged[- ]in|signed[- ]in|"
                             r"with an? (active|open) session|with products in the cart|(that|who|which) already (has|have|exists))", re.I)
IMPERATIVE_UI = re.compile(r"click\w* (on )?(the )?(button|link|field)|press\w* the button|tap\w* (on )?the button|xpath|css=|#[\w-]+\b|\.[\w-]+\s*>|data-testid|\bid=\w+", re.I)
VAGUE_THEN = re.compile(r"(everything|the system|the screen|the app(lication)?) (works|responds|runs) (correctly|properly|fine|well)|looks (fine|good|correct|ok)|"
                        r"is correct\s*$|^\s*(ok|works|it works)\s*$", re.I)


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "").lower()).strip()


def _tokens(s):
    return {t for t in re.split(r"[^a-záéíóúñü0-9]+", _norm(s)) if len(t) > 2}


def review_manual(c):
    h = []

    def p(sev, kind, title, suggestion=""):
        h.append({"severity": sev, "type": kind, "title": title, "suggestion": suggestion})

    title = c.get("title", "")
    if len(title.split()) < 3 or re.match(r"^\s*(case|test)\b", title, re.I) or re.search(r"verify (the )?functionality", title, re.I):
        p("Medium", "Title", f"Non-descriptive title: “{title}”", "Say what is tested and under which condition: “Login with a wrong password shows an error”.")
    steps = c.get("steps") or []
    result = " ".join(x.get("result", "") for x in steps).strip()
    if not result:
        p("High", "Expected result", "It has no expected result", "Without an expected result you cannot decide whether it passed or failed.")
    elif VAGUE_RESULT.search(result):
        p("Medium", "Expected result", f"Vague expected result: “{result[:80]}”", "Say exactly what is shown: the message, the data or the screen.")
    for i, x in enumerate(steps, 1):
        act = x.get("action", "")
        if VAGUE_STEP.search(act):
            p("Medium", "Vague step", f"Step {i} is vague: “{act[:80]}”", "One concrete action per step, without “etc.” or “verify that it works”.")
        elif act and act != "(no steps)" and not VERB.search(act):
            p("Low", "Step without action", f"Step {i} does not start with an action: “{act[:80]}”", "Start each step with the verb: Go to…, Fill in…, Click…")
    if len(steps) > 12:
        p("Medium", "Length", f"It has {len(steps)} steps", "It probably tests more than one thing: split it into smaller cases.")
    elif len(steps) == 1 and steps[0].get("action") not in ("", "(no steps)"):
        p("Low", "Length", "It has a single step", "Check whether steps are missing to reproduce it.")
    data_col = " ".join(str(x.get("data") or "") for x in steps).strip()
    fixed = [m.group(0) for x in steps for m in FIXED_DATA.finditer(x.get("action", ""))]
    if fixed and not data_col:
        p("Low", "Test data", f"Data written inside the steps: {', '.join(fixed[:3])}", "Move them to the Test Data column: that way the case is reused with other data.")
    if not str(c.get("preconditions") or "").strip() and any(PREVIOUS_STATUS.search(x.get("action", "")) for x in steps):
        p("Low", "Preconditions", "A step assumes a previous state and there are no preconditions", "Write in Preconditions the state it starts from (user logged in, cart with products…).")
    if not c.get("priority"):
        p("Low", "Priority", "No priority", "Critical, High, Medium or Low.")
    if result and len([s for s in re.split(r"[;\n]|\.\s", result) if s.strip()]) >= 5:
        p("Low", "Scope", "The expected result verifies many things", "A case that verifies 5 or more things is hard to diagnose when it fails: split it.")
    return h


def review_bdd(c):
    h = []

    def p(sev, kind, title, suggestion=""):
        h.append({"severity": sev, "type": kind, "title": title, "suggestion": suggestion})

    lines = [l.strip() for l in str(c.get("gherkin") or "").splitlines()]
    keywords, last = [], None
    for l in lines:
        m = re.match(r"(Given|When|Then|And|But)\s+(.*)", l)
        if not m:
            continue
        kw = m.group(1)
        if kw in ("And", "But"):
            kw = last or kw
        last = kw
        keywords.append((kw, m.group(2)))
    kinds = [k for k, _ in keywords]
    if "Then" not in kinds:
        p("High", "Then", "The scenario has no Then", "Without Then it verifies nothing: add the expected result.")
    for k, t in keywords:
        if k == "Then" and VAGUE_THEN.search(t):
            p("Medium", "Then", f"Vague Then: “{t[:80]}”", "Verify something observable: the message, the data, the URL.")
        if k in ("Given", "When") and IMPERATIVE_UI.search(t):
            p("Low", "Style", f"Imperative UI step: “{t[:80]}”", "Declarative BDD: describe the intent (“logs in with…”), not the clicks; the details go in the steps.")
    order = {"Given": 0, "When": 1, "Then": 2}
    sequence = [order[k] for k in kinds if k in order]
    if any(b < a for a, b in zip(sequence, sequence[1:])):
        p("Medium", "Structure", "The Given → When → Then order is broken", "One scenario = one context, one action and its verifications; if you need another action, it is another scenario.")
    if kinds.count("When") > 3:
        p("Low", "Structure", f"{kinds.count('When')} When steps", "Too many actions: they are probably two scenarios.")
    if re.search(r"Scenario (Outline|Template):", c.get("gherkin") or "") and "Examples:" not in (c.get("gherkin") or ""):
        p("High", "Structure", "Scenario Outline without Examples", "Without the examples table it does not run.")
    if not re.match(r"^TC(-API)?-\d+$", c.get("id", "")):
        p("Low", "Traceability", "The scenario has no @TC-XXX", "Without the tag it cannot be traced to the case, the management tool or the results.")
    return h


def duplicates(cases, threshold=0.85):
    output = []
    signatures = [(c, _tokens(c["title"] + " " + " ".join(x.get("action", "") for x in c.get("steps") or []) + " " + (c.get("gherkin") or ""))) for c in cases]
    for i in range(len(signatures)):
        for j in range(i + 1, len(signatures)):
            a, b = signatures[i][1], signatures[j][1]
            if len(a) < 4 or len(b) < 4:
                continue
            sim = len(a & b) / len(a | b)
            if sim >= threshold:
                output.append((signatures[i][0], signatures[j][0], round(sim * 100)))
    return output


def sources(a):
    if a.source:
        return [Path(x.strip()) for x in a.source.split(",") if x.strip()]
    us = a.story
    base = ROOT / "output" / "test-cases"
    if us:
        return [Path(x) for x in sorted(glob.glob(str(base / "manual" / f"cases-{us}.xlsx")) + glob.glob(str(base / "bdd" / f"{us}*.feature")))]
    return [Path(x) for x in sorted(glob.glob(str(base / "manual" / "cases-US-*.xlsx")) + glob.glob(str(base / "bdd" / "*.feature")))]


def review(files):
    from readers import read_feature, read_xlsx
    cases = []
    for f in files:
        try:
            items = read_xlsx(f) if f.suffix.lower() == ".xlsx" else read_feature(f)
        except Exception as e:  # a spreadsheet with another format is reported and we move on
            print(f"[!] I could not read {f.name}: {e}", file=sys.stderr)
            continue
        m = re.search(r"(US-\d+)", f.name, re.I)
        for c in items:
            tags = [t.upper() for t in c.get("tags") or []]
            us = next((t for t in tags if re.fullmatch(r"US-\d+", t)), m.group(1).upper() if m else "NO-US")
            c["story"] = us
            try:
                c["file"] = f.resolve().relative_to(ROOT).as_posix()
            except ValueError:
                c["file"] = str(f)
            cases.append(c)
    for c in cases:
        c["findings"] = review_manual(c) if c["type"] == "manual" else review_bdd(c)
        est = estimate_case(c)
        c["time_min"] = est["minutes"]
        c["time"] = est["text"]
    for a, b, sim in duplicates(cases):
        b["findings"].append({"severity": "Medium", "type": "Duplicate", "title": f"Very similar to {a['id']} ({sim} %)",
                              "suggestion": "If they test the same thing, keep one; if they differ, make the title say how.", "related": a["id"]})
    for c in cases:
        c["findings"].sort(key=lambda x: SEV_ORDER[x["severity"]])
        c["score"] = max(0, 100 - sum(WEIGHT[x["severity"]] for x in c["findings"]))
    stories = {}
    for c in cases:
        stories.setdefault(c["story"], []).append(c)
    by_story = []
    for us, cs in sorted(stories.items()):
        neg = [c for c in cs if NEGATIVE.search(" ".join([c.get("title", ""), c.get("description", ""), " ".join(c.get("tags") or [])]))]
        h = []
        if len(cs) >= 3 and not neg:
            h.append({"severity": "Medium", "type": "Coverage", "title": f"{us} has no negative or edge cases",
                      "suggestion": "Add cases with invalid data, empty fields and boundary values (design-techniques skill)."})
        by_story.append({"story": us, "cases": len(cs), "negatives": len(neg), "avg_score": round(sum(c["score"] for c in cs) / len(cs)),
                         "time_min": sum(c["time_min"] for c in cs), "findings": h})
    return cases, by_story


def summary(cases, by_story):
    found = [x for c in cases for x in c["findings"]] + [x for h in by_story for x in h["findings"]]
    total_t = sum(c["time_min"] for c in cases)
    return {"cases": len(cases), "manual": sum(1 for c in cases if c["type"] == "manual"), "bdd": sum(1 for c in cases if c["type"] != "manual"),
            "avg_score": round(sum(c["score"] for c in cases) / len(cases)) if cases else None,
            "no_issues": sum(1 for c in cases if not c["findings"]), "to_improve": sum(1 for c in cases if c["score"] < 70),
            "findings": len(found), "duplicates": sum(1 for x in found if x["type"] == "Duplicate"),
            "no_result": sum(1 for x in found if x["type"] in ("Expected result", "Then") and x["severity"] == "High"),
            "total_time_min": total_t, "total_time": format_time(total_t),
            "by_severity": {s: sum(1 for x in found if x["severity"] == s) for s in ("High", "Medium", "Low")},
            "by_type": {t: sum(1 for x in found if x["type"] == t) for t in sorted({x["type"] for x in found})}}


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Test case quality review")
    ap.add_argument("--story")
    ap.add_argument("--source", help=".xlsx or .feature files separated by commas")
    ap.add_argument("--name", help="output folder (by default the story or 'all')")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--output")
    a = ap.parse_args()
    a.story = a.story.upper() if a.story else None
    name = a.name or a.story or "all"
    folder = Path(a.output) if a.output else ROOT / "output" / "case-review" / name
    data_file = folder / "review.json"
    if not a.report_only:
        files = sources(a)
        if not files:
            sys.exit("I found no cases to review: pass --source or generate the story's cases first.")
        cases, by_story = review(files)
        _history.archive(folder, ["review.json", "analysis.json", "review-report.html"], "review.json")
        folder.mkdir(parents=True, exist_ok=True)
        cases.sort(key=lambda c: (c["score"], c["story"], c["id"]))
        now = datetime.datetime.now()
        data = {"name": name, "story": a.story, "date": now.isoformat(timespec="seconds"), "stamp": now.strftime("%Y%m%d-%H%M%S"),
                "sources": [str(x) for x in files], "cases": cases, "by_story": by_story, "summary": summary(cases, by_story)}
        data_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        r = data["summary"]
        print(f'Cases: {r["cases"]} ({r["manual"]} manual, {r["bdd"]} BDD) · average score {r["avg_score"]} · to improve: {r["to_improve"]} · '
              f'findings: {r["findings"]} · manual execution time: {r["total_time"]}')
    args = [sys.executable, str(ROOT / "scripts" / "generate_review_report.py"), str(data_file), str(folder / "review-report.html")]
    if (folder / "analysis.json").exists():
        args += ["--analysis", str(folder / "analysis.json")]
    res = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    print(res.stdout.strip() or res.stderr.strip())


if __name__ == "__main__":
    main()
