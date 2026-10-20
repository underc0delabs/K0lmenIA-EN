"""Failure analyst, coverage analyst and the failures, coverage and web performance reports."""
import json
import subprocess
import sys
from pathlib import Path

import analyze_coverage
import analyze_failures
import generate_coverage_report
import generate_failures_report
import generate_web_performance_report
import collect_results

ROOT = Path(__file__).resolve().parents[1]


def test_classify_failures():
    c = analyze_failures.classify
    assert c("Error: expect(received).toHaveText(expected)\nExpected: 1\nReceived: 2", ["passed", "failed"])[0] == "Possible bug"
    assert c("TimeoutError: locator.click: Timeout 10000ms exceeded.", ["failed"])[0] == "Locator or wait"
    assert c("Error: connect ECONNREFUSED 10.0.0.1:8080", ["failed"])[0] == "Environment"
    assert c("Request failed with status code 409 Conflict", ["failed"])[0] == "Test data"
    assert c("TypeError: Cannot read properties of undefined (reading 'x')", ["failed"])[0] == "Automation error"
    assert c("", ["passed", "undefined"])[0] == "Undefined step"
    assert c("something weird", ["failed"])[0] == "Unclassified"


def _scenario(name, tags, status, error=""):
    return {"type": "scenario", "name": name, "line": 1, "tags": [{"name": t} for t in tags],
            "steps": [{"keyword": "Then ", "name": "x", "result": {"status": status, "duration": 1, "error_message": error}}]}


def _report(directory, passes):
    rep = [{"name": "F", "uri": "f.feature", "tags": [{"name": "@US-001"}], "elements": [
        _scenario("ok", ["@TC-001"], "passed"),
        _scenario("bug", ["@TC-002"], "failed", "AssertionError: Expected 1 Received 2"),
        _scenario("flaky", ["@TC-003"], "passed" if passes else "failed", "TimeoutError: Timeout 5000ms exceeded")]}]
    (directory / "web").mkdir(parents=True, exist_ok=True)
    (directory / "web" / "cucumber-report.json").write_text(json.dumps(rep), encoding="utf-8")


def test_failures_detects_flaky(tmp_path):
    _report(tmp_path / "c1", False)
    _report(tmp_path / "c2", True)
    output = tmp_path / "out"
    script = str(ROOT / "scripts" / "analyze_failures.py")
    subprocess.run([sys.executable, script, "--reports", str(tmp_path / "c1"), "--output", str(output)], check=True, capture_output=True)
    subprocess.run([sys.executable, script, "--add-retry", "--reports", str(tmp_path / "c2"), "--output", str(output)],
                   check=True, capture_output=True)
    data = json.loads((output / "failures.json").read_text(encoding="utf-8"))
    by_case = {f["case"]: f for f in data["failures"]}
    assert by_case["TC-002"]["category"] == "Possible bug"
    assert by_case["TC-003"]["category"] == "Flaky"
    assert by_case["TC-003"]["history"] == ["Failed", "Passed"]
    assert data["summary"]["passed"] == 1 and data["suites"] == ["web"]
    html = (output / "failures-report.html").read_text(encoding="utf-8")
    assert "Flaky" in html and "F-01" in html



def test_failures_retry_of_one_suite_does_not_touch_others(tmp_path):
    """Retrying only web (--suites web) does not take api out of the analysis nor add a "retry" that was not done."""
    _report(tmp_path / "c1", False)
    (tmp_path / "c1" / "api").mkdir(parents=True)
    (tmp_path / "c1" / "api" / "cucumber-report.json").write_text(json.dumps([{"name": "A", "uri": "a.feature", "tags": [{"name": "@US-001"}],
        "elements": [_scenario("api", ["@TC-API-001"], "failed", "AssertionError: Expected 200 Received 500")]}]), encoding="utf-8")
    _report(tmp_path / "c2", True)
    (tmp_path / "c2" / "api").mkdir(parents=True)
    (tmp_path / "c2" / "api" / "cucumber-report.json").write_text("[]", encoding="utf-8")  # not retried
    output = tmp_path / "out"
    script = str(ROOT / "scripts" / "analyze_failures.py")
    subprocess.run([sys.executable, script, "--reports", str(tmp_path / "c1"), "--output", str(output)], check=True, capture_output=True)
    subprocess.run([sys.executable, script, "--add-retry", "--suites", "web", "--reports", str(tmp_path / "c2"),
                    "--output", str(output)], check=True, capture_output=True)
    data = json.loads((output / "failures.json").read_text(encoding="utf-8"))
    by_case = {f["case"]: f for f in data["failures"]}
    assert by_case["TC-003"]["category"] == "Flaky"
    assert by_case["TC-API-001"]["history"] == ["Failed", None] and data["suites"] == ["web", "api"]

def test_coverage_crosses_sources(tmp_path, monkeypatch):
    def write(path, text):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text, encoding="utf-8")

    write("input/stories/US-001.md", "- AC1: Valid signup\n- AC2: Invalid email\n- AC3: Duplicate email\n")
    write("output/test-cases/bdd/US-001-signup.feature",
          "@US-001\nFeature: R\n  @TC-001 @AC1\n  Scenario: a\n    Given x\n  @TC-002 @AC2\n  Scenario: b\n    Given x\n")
    write("tools/k0lmena/web/features/US-001.feature",
          "@US-001\nFeature: R\n  @TC-001\n  Scenario: a\n    Given x\n  @TC-002 @blocked\n  Scenario: b\n    Given x\n")
    write("tools/k0lmena/reports/web/cucumber-report.json", json.dumps([{"name": "R", "uri": "f", "tags": [{"name": "@US-001"}], "elements": [
        _scenario("a", ["@TC-001"], "failed")]}]))
    monkeypatch.setattr(analyze_coverage, "ROOT", tmp_path)
    monkeypatch.setattr(collect_results, "ROOT", tmp_path)
    monkeypatch.setattr(collect_results, "K0", tmp_path / "tools" / "k0lmena" / "reports")
    h = analyze_coverage.analyze_story("US-001", {})
    types = {x["type"] for x in h["gaps"]}
    assert {"Criterion without cases", "Automated but blocked", "Latest result failed"} <= types
    assert h["metrics"]["criteria"] == 3 and h["metrics"]["covered_criteria"] == 2
    tc1 = next(x for x in h["cases"] if x["id"] == "TC-001")
    assert tc1["criteria"] == ["AC1"] and tc1["result"]["status"] == "Failed"
    for i, x in enumerate(h["gaps"]):
        x["id"] = f"C-{i + 1:02d}"
    html = generate_coverage_report.build_html({"scope": "US-001", "stories": [h]}, {})
    assert "Criterion without cases" in html and "Traceability matrix" in html


def test_criteria_and_coverage_table():
    text = "- **AC1** — Login ok\nAC2: Lockout\n| AC3 | Expires | TC-004, TC-005 | Covered |\n"
    assert analyze_coverage.criteria_from_text(text) == {"AC1": "Login ok", "AC2": "Lockout", "AC3": "Expires"}
    assert analyze_coverage.table_coverage(text) == {"AC3": {"TC-004", "TC-005"}}


def test_web_performance_report():
    data = {"url": "https://x.com/", "host": "x.com", "config": {"devices": ["mobile"], "repetitions": 1,
            "thresholds": {"lcp": {"name": "LCP", "title": "Largest Contentful Paint", "good": 2500, "poor": 4000, "unit": "ms"}}},
            "summary": {"web_performance_mobile": 62, "vitals_ok_mobile": 0, "opportunities": 1},
            "results": [{"url": "https://x.com/", "device": "mobile", "scores": {"performance": 62, "seo": 100},
                         "metrics": {"lcp": {"value": 4800, "text": "4.8 s", "status": "poor"}}, "total_size": 1048576, "requests": 40,
                         "resources": {"JavaScript": {"bytes": 700000, "requests": 12}}, "lcp": {"selector": "img.hero", "label": "Banner"},
                         "sequence": [{"ms": 500, "screenshot": "screenshots/01-t00.jpg"}], "lighthouse": "lighthouse/01.html"}],
            "findings": [{"id": "R-01", "category": "Core Web Vitals", "severity": "High", "page": "https://x.com/", "device": "mobile",
                          "title": "Poor LCP: 4.8 s", "detail": "x"}],
            "opportunities": [{"id": "unused-javascript", "title": "Reduce unused JavaScript", "description": "d", "savings_ms_max": 1200,
                               "savings_bytes_max": 300000, "pages": ["https://x.com/"], "devices": ["mobile"], "metrics": ["LCP"],
                               "items": [{"url": "https://x.com/app.js", "savings_bytes": 300000}]}]}
    html = generate_web_performance_report.build_html(data, {})
    assert "Core Web Vitals in red" in html and "4.8 s · Poor" in html and "Reduce unused JavaScript" in html
    assert "img.hero" in html and "screenshots/01-t00.jpg" in html


def test_failures_report_with_analysis():
    data = {"summary": {"scenarios": 2, "passed": 1}, "runs": [{"id": "c1", "label": "Original run"}], "suites": ["web"],
            "failures": [{"id": "F-01", "category": "Locator or wait", "scenario": "Login", "suite": "web", "history": ["Failed"],
                          "final_status": "Failed", "error": "TimeoutError", "evidence": []}]}
    html = generate_failures_report.build_html(data, {"failures": {"F-01": {"category": "Possible bug", "cause": "The button does not appear", "bug": "BUG-009"}}})
    assert "signs of a bug" in html and "BUG-009" in html and "The button does not appear" in html
