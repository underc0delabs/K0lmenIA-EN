"""Quality dashboard (scripts/quality_dashboard.py) and reports portal (scripts/reports_portal.py)."""
import json
import os
import time
from pathlib import Path

import pytest

import _history
import reports_portal as portal
import collect_results as rec
import quality_dashboard as dashboard

REAL_ROOT = Path(__file__).resolve().parents[1]


def _write(path, content, mtime=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
    if mtime:
        os.utime(path, (mtime, mtime))
    return path


def _scenario(name, tags, status):
    return {"name": name, "type": "scenario", "tags": [{"name": f"@{t}"} for t in tags],
            "steps": [{"result": {"status": status, "duration": 1_000_000_000}}]}


def _ts(date):
    return time.mktime(time.strptime(date, "%Y-%m-%d %H:%M"))


@pytest.fixture
def project(tmp_path):
    """A synthetic project with a bit of everything."""
    o = tmp_path / "output"
    k0 = tmp_path / "tools" / "k0lmena"
    _write(o / "runs" / "_results-US-002-2026-10-05-1200.json", {
        "story": "US-002", "date": "2026-10-05 12:00",
        "cases": [{"id": "TC-003", "title": "No balance", "status": "Failed"},
                  {"id": "TC-004", "title": "Empty fields", "status": "Passed"}]}, _ts("2026-10-05 12:00"))
    _write(o / "runs" / "report-US-002-2026-10-05-1200.html", "<html></html>", _ts("2026-10-05 12:00"))
    _write(k0 / "web" / "features" / "US-001-signup.feature",
           "@US-001\nFeature: Signup\n\n  @TC-001 @smoke\n  Scenario: Valid signup\n    Given something\n    When I do\n    Then it passes\n\n"
           "  @TC-002\n  Scenario: Repeated email\n    Given something\n    Then it fails\n")
    _write(k0 / "reports" / "web" / "history" / "2026-10-01T10-00-00" / "cucumber-report.json",
           [{"tags": [{"name": "@US-001"}], "elements": [_scenario("Valid signup", ["TC-001"], "failed"),
                                                        _scenario("Repeated email", ["TC-002"], "passed")]}],
           _ts("2026-10-01 10:00"))
    _write(k0 / "reports" / "web" / "cucumber-report.json",
           [{"tags": [{"name": "@US-001"}], "elements": [_scenario("Valid signup", ["TC-001"], "passed"),
                                                        _scenario("Repeated email", ["TC-002"], "passed")]}],
           _ts("2026-10-08 09:00"))
    _write(o / "test-cases" / "bdd" / "US-002-payments.feature",
           "@US-002\nFeature: Payments\n\n  @TC-001\n  Scenario: Payment ok\n    Given x\n    Then y\n\n"
           "  @TC-002\n  Scenario: Expired card\n    Given x\n    Then y\n\n  @TC-003\n  Scenario: No balance\n    Given x\n    Then y\n")
    _write(o / "bug-reports" / "BUG-001.md", "# BUG-001\n\n- **ID:** BUG-001\n- **Title:** The total does not add the shipping\n"
           "- **Story:** US-002\n- **Severity:** High\n- **Status:** Open\n", _ts("2026-10-06 10:00"))
    _write(o / "bug-reports" / "BUG-002.md", "- **ID:** BUG-002\n- **Title:** Typo\n- **Story:** US-001\n"
           "- **Severity:** Low\n- **Status:** Closed\n", _ts("2026-09-01 10:00"))
    _write(o / "coverage" / "all" / "coverage.json", {"stories": [
        {"story": "US-001", "metrics": {"criteria": 4, "covered_criteria": 4, "automated": 2}, "gaps": []},
        {"story": "US-002", "metrics": {"criteria": 5, "covered_criteria": 3, "automated": 0},
         "gaps": [{"type": "Criterion without cases", "ref": "AC4", "detail": "x"}, {"type": "Criterion without cases", "ref": "AC5", "detail": "y"}]}]})
    _write(o / "failures" / "US-001" / "failures.json", {"summary": {"failed": 1, "by_category": {"Flaky": 1}},
                                                        "failures": [{"story": "US-001", "case": "TC-001", "category": "Flaky"}]})
    _write(o / "accessibility" / "my-app.com" / "audit.json", {"summary": {"compliance_pct": 82, "critical": 2}})
    dashboard.use_root(tmp_path)
    yield tmp_path
    dashboard.use_root(REAL_ROOT)


def test_dashboard_merges_all_sources(project):
    d = dashboard.collect()
    r = d["summary"]
    assert r["cases"] == 5 and r["stories"] == 2
    assert r["automated"] == 2 and r["pct_automated"] == 40
    # latest result of each case: TC-001 and TC-002 (npm test) passed, TC-003 failed, TC-004 passed
    assert (r["passed_in_period"], r["failed_in_period"], r["pct_passed"]) == (3, 1, 75)
    assert r["coverage_pct"] == 78  # 7 of 9 criteria
    assert r["open_bugs"] == 1 and r["open_critical_bugs"] == 1
    assert d["bugs"]["by_severity"]["High"] == 1 and d["bugs"]["by_story"] == {"US-002": 1}
    assert r["flaky"] == 1 and "US-001:TC-001" in d["flaky"]
    assert r["runs"] == 3  # previous npm test (history), the live run and the current npm test
    assert [c["source"] for c in d["runs"]] == ["npm test · web", "live", "npm test · web"]
    assert r["trend_pp"] > 0
    us2 = next(h for h in d["stories"] if h["story"] == "US-002")
    assert (us2["cases"], us2["automated"], us2["failed"], us2["not_run"], us2["open_bugs"], us2["coverage"]) == (3, 0, 1, 2, 1, 60)
    types = {a["type"] for a in d["alerts"]}
    assert {"Open bug", "Flaky", "Failed", "Not automated", "Coverage", "Accessibility"} <= types
    assert d["extras"]["accessibility"][0]["compliance"] == 82
    assert "Web performance" in d["no_data"] and not any("Coverage" in s for s in d["no_data"])


def test_dashboard_filters_by_range(project):
    d = dashboard.collect("2026-10-04", "2026-10-06")
    assert [c["source"] for c in d["runs"]] == ["live"]
    assert d["summary"]["executed_in_period"] == 2
    assert d["bugs"]["period_reported"] == 1  # BUG-002 is from September
    assert d["bugs"]["open"] == 1  # the open ones are the current snapshot


def test_dashboard_without_data_does_not_invent(tmp_path):
    dashboard.use_root(tmp_path)
    try:
        d = dashboard.collect()
    finally:
        dashboard.use_root(REAL_ROOT)
    r = d["summary"]
    assert r["cases"] == 0 and r["pct_passed"] is None and r["pct_automated"] is None and r["coverage_pct"] is None
    assert len(d["no_data"]) >= 5 and not d["alerts"]
    html = dashboard.build_html(d)
    assert "No data" in html and "—" in html


def test_dashboard_cli_report_history_and_analysis(project, capsys):
    assert dashboard.main(["--name", "sprint 12"]) == 0
    folder = project / "output" / "dashboard" / "sprint-12"
    assert (folder / "dashboard.json").exists() and (folder / "dashboard-report.html").exists()
    analysis = _write(project / "a.json", {"verdict": "Ready with observations", "verdict_tone": "warn",
                                           "summary": "Stable sprint, payments is a concern.",
                                           "risks": [{"risk": "Payments not automated", "impact": "Slow regression", "level": "High"}],
                                           "recommendations": [{"action": "Automate US-002", "why": "3 manual cases", "priority": "High"}],
                                           "notes": {"US-002": "in progress"}})
    assert dashboard.main(["--name", "sprint 12", "--analysis", str(analysis)]) == 0
    html = (folder / "dashboard-report.html").read_text(encoding="utf-8")
    assert "Ready with observations" in html and "Automate US-002" in html and "in progress" in html
    assert "Run history" in html  # the previous run was left in history/
    assert len(list((folder / "history").iterdir())) == 1
    assert dashboard.main(["--name", "sprint 12", "--report-only"]) == 0
    assert "Dashboard sprint-12" in capsys.readouterr().out


def test_dashboard_history_type():
    t = _history.TYPES["dashboard"]
    d = {"summary": {"pct_passed": 90, "open_bugs": 2}, "alerts": [{"type": "Flaky", "title": "US-001:TC-003 fails"}]}
    assert t["metrics"][0][1](d) == 90 and len(t["items"](d)) == 1


# ------------------------------------------------------------------ portal
def test_portal_discovers_folders_and_takes_latest_report(tmp_path):
    o = tmp_path / "output"
    old, new = time.time() - 3600, time.time()
    _write(o / "exploratory" / "my-app.com" / "exploratory-report.html", "x", new)
    _write(o / "exploratory" / "my-app.com" / "analysis.json", {"verdict": "With observations"})
    _write(o / "exploratory" / "my-app.com" / "screenshots" / "x.html", "not a report")
    _write(o / "exploratory" / "my-app.com" / "history" / "2026-10-01T10-00-00" / "exploratory-report.html", "old")
    _write(o / "runs" / "report-US-001-2026-10-01-1000.html", "x", old)
    _write(o / "runs" / "report-US-001-2026-10-05-1200.html", "x", new)
    _write(o / "runs" / "_results-US-001-2026-10-05-1200.json",
           {"cases": [{"status": "Passed"}, {"status": "Failed"}]})
    _write(o / "charters" / "US-003" / "charters.html", "x", old)
    _write(o / "charters" / "US-003" / "sessions-report.html", "x", old)
    (o / "my-new-tool").mkdir(parents=True)
    k0 = tmp_path / "reports"
    _write(k0 / "web" / "cucumber-report.html", "x", new)
    _write(k0 / "web" / "cucumber-report.json", [{"elements": [_scenario("a", [], "passed"), _scenario("b", [], "failed")]}])

    h = portal.discover(o, k0)
    assert list(h)[:2] == ["runs", "k0lmena"]  # order: what is looked at most comes first
    rn = h["runs"]
    assert len(rn) == 1 and rn[0]["unit"] == "US-001" and rn[0]["html"].name.endswith("1200.html")
    assert rn[0]["status"] == "1/2 passed"
    ex = h["exploratory"][0]
    assert ex["status"] == "With observations" and ex["history"] == 1 and ex["previous"].name == "exploratory-report.html"
    ch = h["charters"][0]
    assert ch["html"].name == "sessions-report.html" and [o_.name for o_ in ch["others"]] == ["charters.html"]
    assert h["k0lmena"][0]["unit"] == "web" and h["k0lmena"][0]["status"] == "1/2 scenarios passed"
    assert h["my-new-tool"] == []


def test_portal_prefers_full_k0lmena_report(tmp_path):
    k0 = tmp_path / "reports"
    _write(k0 / "web" / "front-report.html", "x", _ts("2026-10-05 12:01"))
    _write(k0 / "web" / "index.html", "x", _ts("2026-10-05 12:00"))
    _write(k0 / "web" / "features" / "abc.html", "x", _ts("2026-10-05 12:00"))
    _write(k0 / "web" / "cucumber-report.json", [{"elements": [_scenario("a", [], "passed")]}])
    _write(k0 / "web" / "history" / "2026-10-01T10-00-00" / "front-report.html", "x", _ts("2026-10-01 10:01"))
    _write(k0 / "web" / "history" / "2026-10-01T10-00-00" / "index.html", "x", _ts("2026-10-01 10:00"))
    _write(k0 / "web" / "history" / "2026-10-01T10-00-00" / "cucumber-report.json", [])

    k = portal.discover(tmp_path / "output", k0)["k0lmena"]
    assert len(k) == 1 and k[0]["unit"] == "web" and k[0]["html"].name == "index.html"
    assert [o_.name for o_ in k[0]["others"]] == ["front-report.html"]
    assert k[0]["status"] == "1/1 scenarios passed"
    assert k[0]["history"] == 1 and k[0]["previous"].name == "index.html"


def test_portal_html_with_relative_links(tmp_path):
    o = tmp_path / "output"
    _write(o / "accessibility" / "my-app.com" / "accessibility-report.html", "x")
    target, h = portal.generate(o, tmp_path / "does-not-exist")
    html = target.read_text(encoding="utf-8")
    assert target == o / "index.html"
    assert 'href="accessibility/my-app.com/accessibility-report.html"' in html
    assert "Accessibility" in html and "Reports portal" in html


def test_portal_without_output_and_tones(tmp_path):
    target, h = portal.generate(tmp_path / "output", tmp_path / "reports")
    assert "No reports yet" in target.read_text(encoding="utf-8")
    assert portal._tone("Not ready") == "bad" and portal._tone("Ready with observations") == "warn"
    assert portal._tone("Ready") == "ok" and portal._tone("10/10 passed") == "ok" and portal._tone("5/10 passed") == "bad"


def test_portal_is_not_scheduled_in_tests(monkeypatch):
    monkeypatch.setattr(portal, "_SCHEDULED", [False])
    portal.schedule()
    assert portal._SCHEDULED == [False]


def test_portal_is_not_versioned():
    rules = (REAL_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "/output/**" in rules and "!/output/**/.gitkeep" in rules


def test_portal_story_and_filters(tmp_path):
    from pathlib import Path as P
    assert portal.story_of({"unit": "US-001", "html": P("x/report.html")}) == "US-001"
    assert portal.story_of({"unit": "web", "html": P("output/runs/report-PROJ-12-20261014.html")}) == "PROJ-12"
    assert portal.story_of({"unit": "sprint-12", "html": P("dashboard/sprint-12/report.html")}) == "sprint-12"
    assert portal.story_of({"unit": "qarmy.ar", "html": P("a/qarmy.ar/i.html")}) == "qarmy.ar"
    d = tmp_path / "output" / "permissions" / "US-002"
    d.mkdir(parents=True)
    (d / "permissions-report.html").write_text("<html></html>", encoding="utf-8")
    (d / "analysis.json").write_text('{"verdict": "There is improper access: critical"}', encoding="utf-8")
    target, _ = portal.generate(tmp_path / "output", tmp_path / "reports")
    html = target.read_text(encoding="utf-8")
    assert 'id="filters"' in html and 'data-view="story"' in html
    assert 'data-tool="permissions" data-story="US-002" data-tone="bad"' in html
    assert html.count('data-nav="US-002"') == 0  # the by-story view does not duplicate the index


def test_dashboard_computes_automation_savings(monkeypatch):
    # 2 automated cases (10 and 20 min by hand, 0.5 and 1 min automated) and 1 manual (15 min pending).
    cases = [
        {"story": "US-001", "id": "TC-001", "automated": [{"blocked": False}], "manual_minutes": 10,
         "duration_s": 30, "result": {"status": "Passed"}, "flaky": False},
        {"story": "US-001", "id": "TC-002", "automated": [{"blocked": False}], "manual_minutes": 20,
         "duration_s": 60, "result": {"status": "Passed"}, "flaky": False},
        {"story": "US-002", "id": "TC-001", "automated": [], "manual_minutes": 15, "result": None, "flaky": False},
    ]
    monkeypatch.setattr(dashboard, "inventory", lambda: cases)
    monkeypatch.setattr(dashboard, "runs", lambda r: [{"date": "2026-10-17T10:00", "pct_passed": 100},
                                                      {"date": "2026-10-17T11:00", "pct_passed": 100}])
    monkeypatch.setattr(dashboard, "period_results", lambda r: {"Passed": 2})
    monkeypatch.setattr(dashboard, "coverage", lambda: None)
    monkeypatch.setattr(dashboard, "bugs", lambda r: {"open": 0, "open_critical": [], "by_story": {},
                                                      "by_severity": {}, "total": 0, "period_reported": 0})
    monkeypatch.setattr(dashboard, "failures", lambda: {"flaky": 0})
    monkeypatch.setattr(dashboard, "extras", lambda: {"accessibility": [], "web_performance": [], "performance": [], "security": [], "tokens": []})
    r = dashboard.collect()["summary"]
    assert r["automated_minutes"] == 30 and r["auto_run_minutes"] == 1.5
    assert r["savings_per_run"] == 28.5  # 30 by hand − 1.5 automated
    assert r["cumulative_savings"] == 57.0    # 28.5 × 2 runs
    assert r["manual_minutes"] == 15        # the pending manual work does not count toward the savings


def test_dashboard_does_not_mix_same_tc_from_two_stories(tmp_path):
    _write(tmp_path / "output" / "runs" / "_results-US-001-a.json",
           {"story": "US-001", "cases": [{"id": "TC-001", "status": "Passed"}]})
    _write(tmp_path / "output" / "runs" / "_results-US-002-a.json",
           {"story": "US-002", "cases": [{"id": "TC-001", "status": "Failed"}]})
    dashboard.use_root(tmp_path)
    try:
        period = dashboard.period_results((None, None))
    finally:
        dashboard.use_root(REAL_ROOT)
    assert period == {"Passed": 1, "Failed": 1}
