"""Resilience report (resilience-tester agent)."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_resilience_report as report  # noqa: E402


def _data():
    return {
        "url": "https://app.com/", "host": "app.com", "date": "2026-10-14T10:00:00", "stamp": "20261014-100000", "timeout_ms": 8000,
        "scenarios": [{"id": "api-500", "name": "The API responds 500", "type": "api"}, {"id": "offline", "name": "The connection drops", "type": "network"}],
        "summary": {"pages": 1, "scenarios": 2, "tests": 2, "ok": 0, "with_findings": 1, "not_applicable": 1, "errors": 0, "findings": 1,
                    "blank_screens": 1, "no_recovery": 0, "silent_failures": 0, "by_severity": {"High": 1}},
        "findings": [{"id": "R-01", "severity": "High", "type": "Blank screen", "scenario": "api-500", "page": "https://app.com/",
                      "title": "The API responds 500: the screen is left almost empty", "detail": "10 characters remain"}],
        "pages": [{"url": "https://app.com/", "id": "01-home", "base": {"title": "Home", "text_len": 900, "elements": 120, "api_calls": ["GET /api/x"]},
                   "results": [
                       {"scenario": "api-500", "name": "The API responds 500", "status": "finding", "findings": ["R-01"], "intercepted": 1,
                        "observed": {"text_len": 10, "elements": 3, "messages": []}, "recovery": {"recovers": True}},
                       {"scenario": "offline", "name": "The connection drops", "status": "not-applicable", "reason": "no network", "findings": []}]}],
    }


def test_report_with_matrix_findings_and_analysis():
    analysis = {"verdict": "The home page breaks with the API", "findings": {"R-01": {"severity": "Critical", "note": "It is the home page"}},
                "manual": [{"id": "RM-01", "title": "Double submit at checkout", "severity": "High", "scenario": "slow", "steps": "…", "expected": "1 order", "actual": "2 orders"}],
                "missing_info": [{"id": "MI-01", "what_is_missing": "Message if the API fails", "question": "Which message?"}],
                "recommendations": [{"action": "Show an error with Retry", "reason": "Today it goes blank", "priority": "High"}]}
    html = report.build_html(_data(), analysis)
    for text in ("Page × scenario matrix", "The home page breaks with the API", "It is the home page", "Critical", "RM-01", "Double submit at checkout",
                 "MI-01", "Show an error with Retry", "Not applicable", "Recovers when the network comes back: yes"):
        assert text in html, text


def test_verdict_without_applicable_scenarios():
    d = _data()
    d["summary"].update(tests=2, not_applicable=2, with_findings=0, ok=0)
    d["findings"] = []
    assert "There were no applicable scenarios" in report.build_html(d, {})


def test_command_line_and_evolution(tmp_path):
    data = tmp_path / "resilience.json"
    data.write_text(json.dumps(_data()), encoding="utf-8")
    output = tmp_path / "resilience-report.html"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_resilience_report.py"), str(data), str(output)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "Run history" in output.read_text(encoding="utf-8")
