"""The HTML report generators and the results collector of the closure report."""
import json

import format_tables
import generate_closure_report
import generate_accessibility_report
import generate_exploratory_report
import generate_security_report
import generate_plan
import generate_report
import collect_results


def test_run_report():
    html = generate_report.build_html({
        "title": "Signup", "story": "US-001",
        "cases": [{"id": "TC-001", "title": "OK", "priority": "High", "status": "Passed", "duration_s": 2.5},
                  {"id": "TC-002", "title": "Fails", "priority": "Medium", "status": "Failed", "missing_info": ["MI-01"]}],
    })
    assert "<!doctype html>" in html and "Signup" in html
    assert "50%" in html and "MI-01" in html and "data-tip" in html


def test_plan_and_closure():
    assert "Plan" in generate_plan.build_html({"title": "Plan", "objectives": ["a"], "risks": [{"level": "High", "description": "x"}]})
    html = generate_closure_report.build_html({"title": "Closure", "recommendation": "Go",
                                               "results": {"passed": 3, "failed": 1, "blocked": 0}})
    assert "75%" in html and "Go" in html


def test_security():
    zap = {"site": [{"@name": "https://x", "alerts": [
        {"pluginid": "10038", "name": "CSP Header Not Set", "riskcode": "2", "confidence": "3",
         "desc": "<p>d</p>", "solution": "<p>s</p>", "instances": [{"uri": "https://x/", "method": "GET"}], "count": "1"},
        {"pluginid": "10027", "name": "Comments", "riskcode": "0", "confidence": "1", "instances": [], "count": "1"}]}]}
    html = generate_security_report.build_html(zap, {"false_positives": [{"pluginid": "10027", "reason": "third party"}]}, "https://x", "US-001")
    assert "CSP Header Not Set" in html and "Discarded as false positives" in html


def test_exploratory():
    data = {"url": "https://x.com/", "host": "x.com", "config": {"resolutions": ["360x740", "1366x768"], "max_pages": 5},
            "summary": {"pages": 2, "links": 3, "unverifiable_links": 1},
            "findings": [{"id": "H-01", "category": "Broken link", "severity": "High", "page": "https://x.com/", "title": "Broken internal link (404)", "detail": "https://x.com/no"},
                         {"id": "H-02", "category": "Console error", "severity": "Medium", "page": "https://x.com/", "title": "Error in console", "detail": "third party"}],
            "links": [{"url": "https://x.com/no", "internal": True, "status": 404, "result": "broken", "sources": ["https://x.com/"]},
                      {"url": "https://y.com/", "internal": False, "status": 403, "result": "unverifiable", "sources": ["https://x.com/"]}],
            "responsive": [{"url": "https://x.com/", "resolution": "360x740", "name": "Mobile", "horizontal_overflow": True, "screenshot": "screenshots/home-360x740.png"},
                           {"url": "https://x.com/", "resolution": "1366x768", "name": "Desktop", "horizontal_overflow": False}],
            "pages": [{"url": "https://x.com/", "status": 200, "title": "Home"}]}
    analysis = {"discarded": [{"id": "H-02", "reason": "third-party script"}], "severities": {"H-01": "Critical"},
                "exploratory": [{"id": "EX-01", "title": "The menu does not close", "severity": "Medium", "steps": ["Open menu"]}]}
    html = generate_exploratory_report.build_html(data, analysis)
    assert "Broken internal link (404)" in html and "EX-01" in html and "screenshots/home-360x740.png" in html
    assert "Discarded" in html and "third-party script" in html and "Links that could not be verified" in html
    assert "critical issues" in html  # the severity adjusted to Critical changes the verdict


def test_full_exploratory():
    data = {"url": "https://x.com/", "host": "x.com", "config": {"resolutions": ["360x740"], "slow_ms": 3000},
            "summary": {"pages": 1, "load_avg_ms": 4200, "load_max_ms": 4200, "load_p90_ms": 4200},
            "findings": [{"id": "H-01", "category": "Failing resource", "severity": "High", "page": "https://x.com/",
                          "pages": ["https://x.com/", "https://x.com/b"], "title": "stylesheet that does not load (404)",
                          "detail": "https://x.com/e.css", "evidence": "screenshots/pages/01-home.jpg"}],
            "pages": [{"url": "https://x.com/", "status": 200, "time_ms": 4200, "screenshot": "screenshots/pages/01-home.jpg",
                       "js_errors": ["boom is not defined"], "metrics": {"ttfb_ms": 120, "dom_ms": 900, "requests": 14, "size_kb": 512}}],
            "videos": [{"title": "Walkthrough", "file": "videos/walkthrough.webm"}]}
    html = generate_exploratory_report.build_html(data, {})
    assert 'src="videos/walkthrough.webm#t=1"' in html and 'class="lb thumb' in html  # embedded video and enlargeable screenshot
    assert "and 1 more page(s)" in html and "boom is not defined" in html and "512 KB" in html
    assert "Load time per page" in html and "4.2 s" in html


def test_format_tables_is_idempotent(tmp_path):
    import subprocess
    import sys
    file = tmp_path / "a.md"
    file.write_text("# T\n\n| A | B |\n|---|---|\n| 1 | 2 |\n", encoding="utf-8")
    subprocess.run([sys.executable, format_tables.__file__, str(file)], check=True, capture_output=True)
    once = file.read_text(encoding="utf-8")
    subprocess.run([sys.executable, format_tables.__file__, str(file)], check=True, capture_output=True)
    assert file.read_text(encoding="utf-8") == once  # running it twice changes nothing
    assert once.count("```") == 2 and "+=====+=====+" in once


def test_collect_results(tmp_path, monkeypatch):
    root = tmp_path
    (root / "output" / "runs").mkdir(parents=True)
    (root / "output" / "bug-reports").mkdir(parents=True)
    k0 = root / "tools" / "k0lmena" / "reports"
    (k0 / "web").mkdir(parents=True)
    (root / "output" / "runs" / "_results-US-001-a.json").write_text(json.dumps(
        {"story": "US-001", "cases": [{"id": "TC-001", "status": "Failed"}, {"id": "TC-002", "status": "Passed"}]}), encoding="utf-8")
    (root / "output" / "runs" / "_results-US-002-a.json").write_text(json.dumps(
        {"story": "US-002", "cases": [{"id": "TC-001", "status": "Failed"}]}), encoding="utf-8")
    # More recent npm test: TC-001 passes; a scenario of another story does not count
    import os, time
    report = [{"name": "F", "tags": [{"name": "@US-001"}], "elements": [
        {"type": "scenario", "name": "one", "tags": [{"name": "@TC-001"}], "steps": [{"result": {"status": "passed"}}]}]},
        {"name": "G", "tags": [{"name": "@US-002"}], "elements": [
        {"type": "scenario", "name": "two", "tags": [{"name": "@TC-009"}], "steps": [{"result": {"status": "failed"}}]}]}]
    (k0 / "web" / "cucumber-report.json").write_text(json.dumps(report), encoding="utf-8")
    future = time.time() + 60
    os.utime(k0 / "web" / "cucumber-report.json", (future, future))
    (root / "output" / "bug-reports" / "BUG-001.md").write_text(
        "**ID:** `BUG-001`\n**Title:** x\n**Story:** US-001\n**Status:** Open\n**Criticality / Severity:** High (y)\n", encoding="utf-8")
    monkeypatch.setattr(collect_results, "ROOT", root)
    monkeypatch.setattr(collect_results, "K0", k0)
    data = collect_results.collect("US-001")
    assert data["results"] == {"passed": 2, "failed": 0, "blocked": 0}
    assert data["bugs"]["by_severity"]["High"] == 1
    assert [b["id"] for b in data["bugs"]["open_critical"]] == ["BUG-001"]



def test_collect_distinguishes_stories_and_uses_history(tmp_path, monkeypatch):
    """TCs are numbered per story (TC-001 of US-001 ≠ TC-001 of US-002) and an npm test run filtered
    with TAGS does not hide the result of the scenarios that stayed in history/."""
    import os
    import time
    (tmp_path / "output" / "runs").mkdir(parents=True)
    k0 = tmp_path / "tools" / "k0lmena" / "reports"
    old = k0 / "web" / "history" / "2026-10-01T10-00-00"
    old.mkdir(parents=True)
    sc = lambda name, tc, st: {"type": "scenario", "name": name, "tags": [{"name": f"@{tc}"}],  # noqa: E731
                               "steps": [{"result": {"status": st}}]}
    (old / "cucumber-report.json").write_text(json.dumps([
        {"name": "F", "tags": [{"name": "@US-001"}], "elements": [sc("one", "TC-001", "passed"), sc("two", "TC-002", "failed")]},
        {"name": "G", "tags": [{"name": "@US-002"}], "elements": [sc("other", "TC-001", "failed")]}]), encoding="utf-8")
    a_while_ago = time.time() - 3600
    os.utime(old / "cucumber-report.json", (a_while_ago, a_while_ago))
    # Last filtered run (TAGS=@TC-002): only brings TC-002 of US-001, which now passes.
    (k0 / "web" / "cucumber-report.json").write_text(json.dumps([
        {"name": "F", "tags": [{"name": "@US-001"}], "elements": [sc("two", "TC-002", "passed")]}]), encoding="utf-8")
    monkeypatch.setattr(collect_results, "ROOT", tmp_path)
    monkeypatch.setattr(collect_results, "K0", k0)
    round_ = collect_results.collect()
    assert round_["results"] == {"passed": 2, "failed": 1, "blocked": 0}
    assert {(c["story"], c["id"], c["status"]) for c in round_["cases"]} == {
        ("US-001", "TC-001", "Passed"), ("US-001", "TC-002", "Passed"), ("US-002", "TC-001", "Failed")}
    us1 = collect_results.collect("US-001")
    assert us1["results"] == {"passed": 2, "failed": 0, "blocked": 0}
    assert any("history" in f for f in us1["sources"]) and "npm test · web" in us1["sources"]


def test_newman_without_assertions_is_not_passed():
    import newman_to_results as nar
    ok = {"assertion": "status 200"}
    data = nar.convert({"run": {"executions": [
        {"item": {"name": "API-001 — With test"}, "assertions": [ok]},
        {"item": {"name": "API-002 — Without test"}, "assertions": []},
        {"item": {"name": "API-003 — Down"}, "requestError": {"code": "ECONNREFUSED"}}]}})
    assert [(c["id"], c["status"]) for c in data["cases"]] == [("API-001", "Passed"), ("API-002", "Blocked"), ("API-003", "Blocked")]
    assert data["cases"][1]["reason"] == "No validations (pm.test)"


def test_report_accepts_missing_info_as_text():
    html = generate_report.build_html({"cases": [{"id": "TC-001", "status": "Passed", "missing_info": ["MI-01"]}],
                                       "missing_info": ["MI-01", {"id": "MI-02", "what_is_missing": "Error message"}]})
    assert "Missing information" in html and "MI-02" in html and "Error message" in html

def test_accessibility():
    data = {"url": "https://x.com/", "host": "x.com", "config": {"level": "AA", "best_practices": True, "tabs": 60},
            "summary": {"pages": 1, "compliance_pct": 80.0},
            "findings": [{"id": "A-01", "source": "axe", "rule": "image-alt", "title": "Images without alt", "description": "d",
                          "severity": "Critical", "wcag": ["1.1.1"], "pages": ["https://x.com/"], "total_nodes": 1,
                          "help": "https://dequeuniversity.com/rules/axe/4.13/image-alt",
                          "examples": [{"page": "https://x.com/", "selector": "img", "html": "<img src=a>",
                                        "summary": "Fix any of the following:", "screenshot": "screenshots/elements/01-image-alt-1.jpg"}]},
                         {"id": "A-02", "source": "axe", "rule": "region", "title": "Regions", "severity": "Low", "wcag": [],
                          "pages": ["https://x.com/"], "total_nodes": 3, "examples": []}],
            "review": [{"id": "R-01", "rule": "color-contrast", "title": "Contrast", "wcag": ["1.4.3"], "pages": ["https://x.com/"], "total_nodes": 1}],
            "pages": [{"url": "https://x.com/", "status": 200, "passed": ["a"] * 8, "violations": [{}, {}],
                       "keyboard": {"steps": [{"element": "a", "text": "Home", "visible_indicator": False}], "trap": None}}]}
    html = generate_accessibility_report.build_html(data, {"manual": [{"id": "M-01", "title": "Error not announced", "severity": "High", "wcag": ["3.3.1"]}]})
    assert "Does not meet WCAG AA" in html and "Non-text Content" in html and "Error Identification" in html
    assert "screenshots/elements/01-image-alt-1.jpg" in html and "Fix any of the following:" in html
    assert "To review by hand" in html and "Best practice" in html and "no visible focus" in html
    assert "meets WCAG" not in html.replace("Does not meet WCAG", "")  # never claims conformance
