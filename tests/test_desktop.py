"""Desktop app tester: HTML report (desktop-tester agent) and the control tree survey."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tools" / "desktop"))

import controls  # noqa: E402
import generate_desktop_report as gi  # noqa: E402

ANALYSIS = {
    "title": "Invoicer — US-010", "story": "US-010", "environment": "QA", "generated": "2026-10-19T12:00:00",
    "app": {"name": "Invoicer", "version": "3.2.1", "technology": "WPF", "automation": "Appium + WinAppDriver", "os": "Windows 11"},
    "verdict": "The app works; 1 medium accessibility finding", "verdict_tone": "warn",
    "summary": "I tested creating, saving and DPI compatibility.",
    "tests": [{"id": "TC-001", "area": "Login", "case": "Log in with valid credentials", "result": "Passed",
               "expected": "logs in", "actual": "logs in"},
              {"id": "TC-002", "area": "New invoice", "case": "Save without a customer", "result": "Failed",
               "expected": "validation error", "actual": "crash"}],
    "compatibility": [{"environment": "Windows 10 / 150% DPI", "result": "Failed", "detail": "truncated texts"}],
    "findings": [{"id": "F-01", "severity": "Medium", "area": "Accessibility", "text": "Button without an accessible name",
                  "impact": "cannot be automated or read", "how_to_reproduce": "inspect the Save button", "recommendation": "set an AutomationId"}],
    "recommendations": [{"priority": "Medium", "action": "Add AutomationId", "reason": "accessibility and automation"}],
    "missing_info": [{"id": "MI-01", "what_is_missing": "DPI to support", "question": "up to which scaling?"}],
}


def _gen(tmp_path, data, monkeypatch):
    monkeypatch.setenv("K0LMENIA_PORTAL", "0")
    (tmp_path / "analysis.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    gi.generate(tmp_path / "analysis.json", tmp_path / "report.html")
    return (tmp_path / "report.html").read_text(encoding="utf-8")


def test_full_report(tmp_path, monkeypatch):
    html = _gen(tmp_path, ANALYSIS, monkeypatch)
    assert "Invoicer" in html and "WPF" in html
    assert "Button without an accessible name" in html and "TC-002" in html and "MI-01" in html
    assert "Compatibility" in html and "150% DPI" in html
    assert "inspect the Save button" in html  # "How to reproduce" section


def test_without_tests_or_findings(tmp_path, monkeypatch):
    html = _gen(tmp_path, {"title": "Empty"}, monkeypatch)
    assert "No findings." in html and "Empty" in html


def test_invalid_json_fails(tmp_path):
    (tmp_path / "x.json").write_text("{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        gi.generate(tmp_path / "x.json", tmp_path / "i.html")


def test_tree_summary():
    tree = {"type": "Window", "name": "Main", "children": [
        {"type": "Button", "name": "Save", "children": []},
        {"type": "Button", "name": "", "children": []},
        {"type": "Edit", "name": "Name", "children": [{"type": "Text", "name": "", "children": []}]}]}
    r = controls.tree_summary(tree)
    assert r["controls"] == 5
    assert r["no_name"] == 2
    assert r["by_type"]["Button"] == 2
