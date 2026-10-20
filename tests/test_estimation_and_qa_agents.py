"""Estimated manual run time, case reviewer, charters, log analysis and the UX and forms reports."""
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import analyze_logs
import estimation
import generate_charters
import generate_forms_report
import generate_logs_report
import generate_review_report
import generate_ux_report
import review_cases

ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ estimation
def _login_case():
    return {"id": "TC-1", "title": "Login with an incorrect password", "preconditions": "Registered user", "steps": [
        {"action": "Go to the login page", "data": "", "result": ""},
        {"action": "Complete the email and the password", "data": "Email: ana@test.com\nPassword: Bad123", "result": ""},
        {"action": "Click Submit", "data": "", "result": "The error message is shown and the user stays on the login page"}]}


def test_formula_per_step_and_per_case():
    r = estimation.estimate_case(_login_case())
    assert [p["category"] for p in r["steps"]] == ["Navigate", "Fill in fields", "Click or select"]
    assert r["steps"][1]["action"] == 0.6                      # 2 fields × 0.3
    assert r["factor"] == 1.1 and r["minutes"] == 5.5 and r["text"] == "5.5 min"
    assert estimation.estimate_step("Wait for the confirmation email")["minutes"] == 2.0
    assert estimation.format_time(75) == "1 h 15 min" and estimation.jira_duration(6.5) == "7m" and estimation.hhmm(75) == "01:15"


def test_labels_as_text_trigger_negatives_factor():
    # In the JSON of generate_cases.py the tags are a text ("@login @negative"), not a list.
    base = {"id": "TC-3", "title": "Sign in to the system", "steps": "1. Go to the login\n2. Click Submit", "result": "Sees a notice"}
    assert estimation.estimate_case(dict(base, tags="@login @negative"))["factor"] == 1.1
    assert estimation.estimate_case(dict(base, tags=["login", "edge"]))["factor"] == 1.1
    assert estimation.estimate_case(dict(base, tags="@login"))["factor"] == 1.0


def test_manual_time_wins_and_bdd():
    c = dict(_login_case(), time_min="12")
    r = estimation.estimate_case(c)
    assert r["minutes"] == 12 and r["source"] == "spreadsheet" and abs(sum(p["minutes"] for p in r["steps"]) - 12) > 0  # the steps are distributed
    bdd = {"id": "TC-2", "title": "Add to the cart", "gherkin": "Scenario: x\n  Given the user is on the catalog\n  When they add a product\n  Then the cart shows 1 product\n  And the total is 1500"}
    r = estimation.estimate_case(bdd)
    assert len(r["steps"]) == 4 and r["steps"][2]["verification"] == 0.5 and r["minutes"] >= 1


def test_spreadsheet_with_time_column_and_total(tmp_path):
    from openpyxl import load_workbook
    source = tmp_path / "c.json"
    source.write_text(json.dumps({"module": "US-9", "cases": [
        {"id": "TC-001", "title": "Valid login", "steps": "1. Go to the login\n2. Complete the email\n3. Click Submit", "result": "Sees the home page", "priority": "High"},
        {"id": "TC-002", "title": "Recover password", "steps": "1. Go to the login", "result": "The email arrives", "priority": "High", "time_min": 12}]}), encoding="utf-8")
    output = tmp_path / "cases-US-9.xlsx"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_cases.py"), str(source), str(output)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    ws = load_workbook(output).active
    headers = [c.value for c in ws[3]]
    col = headers.index("Estimated Time (min)") + 1
    assert ws.cell(row=5, column=col).value == 12 and str(ws.cell(row=6, column=col).value).startswith("=SUM(")
    md = output.with_suffix(".md").read_text(encoding="utf-8")
    assert "Estimated manual run time" in md and "12 min" in md
    sys.path.insert(0, str(ROOT / "scripts" / "management"))
    from readers import read_cases
    cases = read_cases(output)
    assert {c["id"]: c["estimate"]["minutes"] for c in cases}["TC-002"] == 12


def test_management_adds_time_and_retries_without_field():
    sys.path.insert(0, str(ROOT / "scripts" / "management"))
    from adapters.base import with_time, try_with_time
    from common import ManagementError
    case = {"estimate": {"text": "5.5 min", "minutes": 5.5}}
    assert with_time("Description", case).endswith("Estimated manual run time: 5.5 min (k0lmenIA)")
    calls = []

    def create(body):
        calls.append(body)
        if "timetracking" in body:
            raise ManagementError("Field 'timetracking' cannot be set")
        return {"key": "PROJ-1"}

    assert try_with_time(create, {"a": 1, "timetracking": {}}, {"a": 1}) == {"key": "PROJ-1"}
    assert len(calls) == 2 and "timetracking" not in calls[1]


# ------------------------------------------------------------------ case reviewer
def test_reviewer_detects_issues_and_duplicates():
    c1 = {"id": "TC-001", "title": "Cart", "type": "manual", "priority": "High", "preconditions": "",
          "steps": [{"action": "Go to the catalog", "data": "", "result": ""}, {"action": "Verify that it works with ana@test.com", "data": "", "result": "It works correctly"}]}
    types = [h["type"] for h in review_cases.review_manual(c1)]
    assert "Title" in types and "Expected result" in types and "Vague step" in types and "Test data" in types
    bdd = {"id": "Pay", "type": "cucumber", "gherkin": "Scenario: Pay\n  Given the user clicks the #pay button\n  When they pay"}
    types = [h["type"] for h in review_cases.review_bdd(bdd)]
    assert "Then" in types and "Style" in types and "Traceability" in types
    a = {"id": "TC-1", "title": "Adding two products to the cart updates the total", "steps": [{"action": "Add the product Mate to the cart"}, {"action": "Add the product Thermos to the cart"}]}
    b = dict(a, id="TC-2", title="Adding two products to the cart updates the final total")
    assert review_cases.duplicates([a, b])[0][2] >= 85


# ------------------------------------------------------------------ charters
def test_session_notes(tmp_path):
    f = tmp_path / "CH-01.md"
    f.write_text("Charter: CH-01\nTester: Ana\nDuration: 60\nTime: setup 10, testing 35, bugs 15\n"
                 "BUG: The total does not add the shipping [High]\nBUG: Technical message\nQUESTION: Coupon before or after?\nCOVERED: Card\nNOT COVERED: Messages\n# comment\n", encoding="utf-8")
    s = generate_charters.read_notes(f)
    assert s["charter"] == "CH-01" and s["duration"] == 60 and (s["t_setup"], s["t_testing"], s["t_bugs"]) == (10, 35, 15)
    assert [b["severity"] for b in s["bugs"]] == ["High", "Medium"] and s["covered"] == ["Card"] and s["uncovered"] == ["Messages"]
    data = {"story": "US-1", "charters": [{"id": "CH-01", "mission": "Explore the payment", "areas": ["Card", "Messages"], "duration_min": 60},
                                          {"id": "CH-02", "mission": "Explore mobile", "areas": ["Button"], "duration_min": 45}]}
    assert "Session sheets" in generate_charters.html_sheets(data) and "## CH-02" in generate_charters.md_sheets(data)
    html = generate_charters.html_report(data, [s])
    assert "1 of 2 session(s) done" in html and "The total does not add the shipping" in html and "Pending" in html


# ------------------------------------------------------------------ logs
def test_logs_dates_signatures_and_stack(tmp_path):
    z = dt.timezone(dt.timedelta(hours=-3))
    assert analyze_logs.date_of("2026-10-11 10:22:33,123 ERROR x", z)[0] == dt.datetime(2026, 10, 11, 10, 22, 33, 123000, tzinfo=z)
    assert analyze_logs.date_of('1.2.3.4 - - [11/Oct/2026:10:22:33 -0300] "GET / HTTP/1.1" 200', None)[0].utcoffset() == dt.timedelta(hours=-3)
    assert analyze_logs.signature("Failure id=123 for ana@test.com in 8f2c1a9e-77aa-4c1d-9a2b-3f4e5d6c7b8a") == "Failure id=<n> for <email> in <uuid>"
    log = tmp_path / "app.log"
    log.write_text("2026-10-11 10:00:00,000 INFO [main] starting\n"
                   "2026-10-11 10:00:05,000 ERROR [exec-1] c.t.Login - Template 7 not found\n"
                   "java.lang.IllegalStateException: Template not found\n\tat com.t.Login.show(Login.java:42)\n"
                   "2026-10-11 10:00:09,000 ERROR [exec-2] c.t.Login - Template 8 not found\n", encoding="utf-8")
    access = tmp_path / "access.log"
    access.write_text('1.2.3.4 - - [11/Oct/2026:10:00:06 -0300] "GET /login HTTP/1.1" 500 10 "-" "x"\n', encoding="utf-8")
    ents, sources = analyze_logs.entries([log, access], z)
    assert len(ents) == 4 and ents[1]["stack"][0].startswith("java.lang.IllegalStateException") and ents[1]["message"].startswith("c.t.Login")
    sc = [{"scenario": "Login", "uri": "f", "line": 1, "story": "US-1", "case": "TC-002", "status": "Failed", "error": "x",
           "start": dt.datetime(2026, 10, 11, 10, 0, 4, tzinfo=z), "end": dt.datetime(2026, 10, 11, 10, 0, 6, tzinfo=z)}]
    _, signatures, timeline, crosses = analyze_logs.analyze(ents, sc, None, None, 1)
    login = next(f for f in signatures if "Template" in f["example"])
    assert login["count"] == 2 and login["stack"] and login["exception"].endswith("IllegalStateException")
    assert {x["signature"] for x in crosses[0]["errors"]} == {login["id"], next(f["id"] for f in signatures if "→ 500" in f["example"])}
    html = generate_logs_report.build_html({"summary": {"errors": 3, "error_signatures": 2, "failed": 1, "failed_with_errors": 1, "scenarios": 1},
                                            "signatures": signatures, "timeline": timeline, "scenarios": crosses, "sources": sources, "window": {}}, {})
    assert "match server errors" in html and "stack trace" in html


# ------------------------------------------------------------------ reports
def test_review_ux_and_forms_reports():
    case = {"story": "US-1", "id": "TC-001", "title": "Cart", "type": "manual", "score": 61, "time": "4 min", "time_min": 4, "file": "x.xlsx",
            "findings": [{"severity": "Medium", "type": "Title", "title": "Title not descriptive enough", "suggestion": "..."}]}
    html = generate_review_report.build_html({"cases": [case], "by_story": [{"story": "US-1", "cases": 1, "negatives": 0, "avg_score": 61, "time_min": 4, "findings": []}],
                                              "summary": {"cases": 1, "avg_score": 61, "to_improve": 1, "total_time": "4 min"}},
                                             {"proposals": {"US-1:TC-001": {"title": "Adding a product updates the cart"}}})
    assert "Proposed version" in html and "Adding a product updates the cart" in html and "Many cases to improve" in html
    heur = {f"H{i}": f"Heuristic {i}" for i in range(1, 11)}
    ux = {"heuristics": heur, "summary": {"pages": 1}, "resolutions": ["1366x768"], "screens": [],
          "findings": [{"id": "U-01", "heuristic": "H9", "severity": "High", "title": "The error page is technical", "detail": "nginx", "where": [{"url": "https://x.com/"}]}],
          "page_404": {"url": "https://x.com/z", "status": 404, "links": 0, "technical": True, "text": "404 Not Found nginx"}}
    html = generate_ux_report.build_html(ux, {"manual_findings": [{"heuristic": "H1", "severity": "High", "title": "No confirmation when paying"}]})
    assert "Score per heuristic" in html and "manual review" in html and "404 error page" in html
    form = {"id": "F-01", "name": "signup", "url": "https://x.com/r", "method": "POST", "action": "/r", "findings": [],
            "fields": [{"name": "email", "label": "Email", "type": "text", "required": True,
                        "tests": [{"rule": "Email without @", "value": "ana", "expected": "rejects", "result": "accepts", "ok": False, "message": "", "source": None}]}]}
    html = generate_forms_report.build_html({"forms": [form], "findings": [{"id": "V-01", "severity": "High", "type": "Accepts an invalid value",
                                                                           "title": "“Email” accepts: Email without @", "form": "F-01"}],
                                             "summary": {"forms": 1, "fields": 1, "tests": 1, "tests_failing": 1, "accepts_invalid": 1}}, {})
    assert "accepts invalid data" in html and "Email without @" in html
