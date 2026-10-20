"""Mobile app tester: HTML report (mobile-tester agent)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import generate_mobile_report as gm  # noqa: E402

ANALYSIS = {
    "title": "MyApp — US-010", "story": "US-010", "environment": "QA", "generated": "2026-10-19T12:00:00",
    "app": {"name": "MyApp", "version": "4.1.0", "platform": "Android", "type": "Native", "os": "Android 14", "device": "Pixel 7 (emulator)"},
    "verdict": "It works; 1 high finding when denying permissions", "verdict_tone": "warn", "summary": "I tested login, permissions and offline.",
    "tests": [{"id": "TC-001", "area": "Login", "case": "Valid login", "device": "Pixel 7 / Android 14", "result": "Passed",
               "expected": "signs in", "actual": "signs in"},
              {"id": "TC-002", "area": "Permissions", "case": "Deny location", "device": "Pixel 7 / Android 14", "result": "Failed",
               "expected": "degrades with a warning", "actual": "crash"}],
    "compatibility": [{"device": "iPhone SE / iOS 16 / large font", "result": "Failed", "detail": "truncated text"}],
    "findings": [{"id": "H-01", "severity": "High", "area": "Permissions", "text": "Crash when denying location",
                  "impact": "it cannot be used without GPS", "how_to_reproduce": "deny the permission on first use", "recommendation": "handle the deny"}],
    "recommendations": [{"priority": "High", "action": "Handle a denied permission", "reason": "prevents the crash"}],
    "missing_info": [{"id": "MI-01", "what_is_missing": "Minimum OS", "question": "From which Android version?"}],
}


def _gen(tmp_path, data, monkeypatch):
    monkeypatch.setenv("K0LMENIA_PORTAL", "0")
    (tmp_path / "analysis.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    gm.generate(tmp_path / "analysis.json", tmp_path / "report.html")
    return (tmp_path / "report.html").read_text(encoding="utf-8")


def test_full_report(tmp_path, monkeypatch):
    html = _gen(tmp_path, ANALYSIS, monkeypatch)
    assert "MyApp" in html and "Android" in html
    assert "Crash when denying location" in html and "TC-002" in html and "MI-01" in html
    assert "Compatibility" in html and "truncated text" in html
    assert "deny the permission on first use" in html  # "How to reproduce" section


def test_without_tests_or_findings(tmp_path, monkeypatch):
    html = _gen(tmp_path, {"title": "Empty"}, monkeypatch)
    assert "No findings." in html and "Empty" in html


def test_invalid_json_fails(tmp_path):
    (tmp_path / "x.json").write_text("{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        gm.generate(tmp_path / "x.json", tmp_path / "i.html")
