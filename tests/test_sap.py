"""SAP tester: HTML report (sap-tester agent) and the read-only SAP GUI survey."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tools" / "sap"))

import generate_sap_report as gi  # noqa: E402
import sap_gui  # noqa: E402

ANALYSIS = {
    "title": "SAP — US-010 (Order to Cash)", "story": "US-010", "environment": "QA (non-production)",
    "generated": "2026-10-19T12:00:00",
    "system": {"sid": "DQ1", "client": "100", "type": "S/4HANA", "version": "2023", "gui_scripting": True, "fiori": True},
    "verdict": "The O2C flow closes; 1 high authorization finding", "verdict_tone": "warn",
    "summary": "I tested O2C end to end and the sales roles.",
    "tests": [{"id": "TC-001", "area": "SAP GUI", "transaction": "VA01", "case": "Create sales order",
               "result": "Passed", "expected": "order created", "actual": "order 12345"},
              {"id": "TC-002", "area": "Fiori", "transaction": "Manage Sales Orders", "case": "View order",
               "result": "Failed", "expected": "shows the order", "actual": "OData error 500"}],
    "authorizations": [{"role": "Z_SALES", "user": "QA_TEST", "object": "V_VBAK_VKO", "activity": "01 Create",
                        "result": "Failed", "detail": "SU53 shows a missing authorization"}],
    "processes": [{"process": "Order to Cash", "step": "VA01 → VL01N → VF01", "status": "Passed", "detail": "documents ok"}],
    "findings": [{"id": "F-01", "severity": "High", "area": "Authorizations", "text": "The Z_SALES role cannot create deliveries",
                  "impact": "cannot complete O2C", "how_to_reproduce": "VL01N with QA_TEST", "recommendation": "add the object in PFCG"}],
    "recommendations": [{"priority": "High", "action": "Adjust the role in PFCG", "reason": "complete O2C"}],
    "missing_info": [{"id": "MI-01", "what_is_missing": "expected price", "question": "which price list?"}],
}


def _gen(tmp_path, data, monkeypatch):
    monkeypatch.setenv("K0LMENIA_PORTAL", "0")
    (tmp_path / "analysis.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    gi.generate(tmp_path / "analysis.json", tmp_path / "report.html")
    return (tmp_path / "report.html").read_text(encoding="utf-8")


def test_full_report(tmp_path, monkeypatch):
    html = _gen(tmp_path, ANALYSIS, monkeypatch)
    assert "Order to Cash" in html and "DQ1" in html
    assert "V_VBAK_VKO" in html and "TC-002" in html and "MI-01" in html
    assert "Authorizations and roles" in html and "Business processes" in html
    assert "VL01N with QA_TEST" in html  # "How to reproduce" section
    assert "Non-production" in html  # QA environment banner


def test_disabled_scripting_warns(tmp_path, monkeypatch):
    data = dict(ANALYSIS, system={"sid": "DQ1", "client": "100", "gui_scripting": False})
    html = _gen(tmp_path, data, monkeypatch)
    assert "Scripting is disabled" in html


def test_without_tests_or_findings(tmp_path, monkeypatch):
    html = _gen(tmp_path, {"title": "Empty"}, monkeypatch)
    assert "No findings." in html and "Empty" in html


def test_invalid_json_fails(tmp_path):
    (tmp_path / "x.json").write_text("{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        gi.generate(tmp_path / "x.json", tmp_path / "i.html")


def test_sessions_summary():
    connections = [{"description": "QAS", "sessions": [{"system": "DQ1", "client": "100", "user": "QA_TEST"},
                                                       {"system": "DQ1", "client": "100", "user": "QA2"}]},
                   {"description": "other", "sessions": [{"error": "could not be read"}]}]
    r = sap_gui.sessions_summary(connections)
    assert r == {"connections": 2, "sessions": 2, "systems": ["DQ1/100"]}
