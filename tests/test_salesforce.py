"""Salesforce tester: the inventory's findings/suggestions logic and the HTML report."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "salesforce"))

import generate_salesforce_report as gi
import inventory as inv


def test_findings_low_coverage_and_uncovered():
    data = {"coverage": [{"ApexClassOrTrigger": {"Name": "AService"}, "NumLinesCovered": 10, "NumLinesUncovered": 40},
                         {"ApexClassOrTrigger": {"Name": "BService"}, "NumLinesCovered": 0, "NumLinesUncovered": 20}],
            "organization": {"IsSandbox": True}}
    h, _ = inv.findings_and_suggestions(data)
    assert data["org_coverage"] == round(100 * 10 / 70, 1)  # 10 covered out of 70 total
    texts = " ".join(x["text"] for x in h)
    assert "below the 75 %" in texts and "BService" in texts


def test_active_process_builder_is_finding():
    h, _ = inv.findings_and_suggestions({"organization": {"IsSandbox": True},
                                        "flows": [{"Label": "Assign", "ProcessType": "Workflow", "IsActive": True}]})
    assert any("Process Builder" in x["text"] for x in h)


def test_multiple_triggers_per_object_and_bulk_suggestion():
    h, s = inv.findings_and_suggestions({"organization": {"IsSandbox": True},
                                        "triggers": [{"Name": "T1", "TableEnumOrId": "Account", "Status": "Active"},
                                                     {"Name": "T2", "TableEnumOrId": "Account", "Status": "Active"}]})
    assert any("2 active triggers" in x["text"] for x in h)
    assert any("200 Account records" in x["test"] for x in s)


def test_production_flags_critical_finding():
    h, _ = inv.findings_and_suggestions({"organization": {"IsSandbox": False}})
    assert any(x["severity"] == "Critical" and "PRODUCTION" in x["text"] for x in h)


def test_active_validation_suggests_negative_and_positive():
    _, s = inv.findings_and_suggestions({"organization": {"IsSandbox": True},
                                        "validations": [{"ValidationName": "Amount", "Active": True, "ErrorMessage": "Amount is missing",
                                                         "ErrorDisplayField": "Amount", "EntityDefinition": {"QualifiedApiName": "Opportunity"}}]})
    assert any("Opportunity" in x["element"] and "Amount is missing" in x["test"] for x in s)


def test_objects_to_review_filters_invalid_names():
    assert inv.objects_to_review("Account, Opp, 1drop; x", []) == ["Account", "Opp"]  # discards the invalid ones
    custom = [{"DeveloperName": "Order", "NamespacePrefix": None}]
    assert "Order__c" in inv.objects_to_review("", custom) and "Account" in inv.objects_to_review("", custom)


def test_html_report(tmp_path, monkeypatch):
    monkeypatch.setenv("K0LMENIA_PORTAL", "0")
    data = {"generated": "2026-10-19T10:00:00", "story": "US-010",
            "org": {"alias": "qa-sb", "name": "QA", "type": "Developer", "sandbox": True, "api": "62.0"},
            "inventory": {"org_coverage": 68.0, "validations": [], "flows": [], "triggers": [],
                          "limits": [{"name": "DailyApiRequests", "max": 100, "remaining": 5}], "errors": {}},
            "findings": [{"severity": "High", "area": "Apex", "text": "Coverage 68 %"}],
            "suggestions": [{"area": "Validation", "element": "Opportunity.Amount", "test": "Save without amount"}]}
    (tmp_path / "salesforce.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    gi.generate(tmp_path / "salesforce.json", tmp_path / "report.html")
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "Salesforce" in html and "Sandbox" in html and "Coverage 68 %" in html and "Save without amount" in html
    assert "DailyApiRequests" in html  # the limit used at 95 % appears in "Most used limits"


def test_report_production_warns(tmp_path, monkeypatch):
    monkeypatch.setenv("K0LMENIA_PORTAL", "0")
    data = {"org": {"alias": "prod", "sandbox": False, "type": "Production"}, "inventory": {"errors": {}}, "findings": [], "suggestions": []}
    (tmp_path / "s.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    gi.generate(tmp_path / "s.json", tmp_path / "i.html")
    assert "PRODUCTION" in (tmp_path / "i.html").read_text(encoding="utf-8")
