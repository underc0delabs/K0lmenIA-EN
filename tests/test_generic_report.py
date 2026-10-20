"""Generic report generator (used by contract-tester, seo-analyst, data-tester, etc.)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import generate_generic_report as gi  # noqa: E402

ANALYSIS = {
    "title": "Contracts — US-010", "eyebrow": "Contract testing (Pact)", "story": "US-010", "environment": "QA",
    "generated": "2026-10-19T12:00:00", "meta": [["Provider", "payments-api"], ["Consumer", "web"]],
    "verdict": "1 broken contract", "verdict_tone": "bad", "summary": "I verified the provider pacts.",
    "metrics": [{"metric": "Contract coverage", "value": "80%", "target": "100%", "status": "Failed"}],
    "tables": [{"title": "Interactions", "columns": ["Interaction", "Status"], "rows": [["GET /payment/{id}", "Failed"]]}],
    "tests": [{"id": "TC-001", "category": "Provider", "case": "Verify pact", "result": "Failed",
               "expected": "200 with {id,status,amount}", "actual": "'amount' is missing"}],
    "findings": [{"id": "F-01", "severity": "High", "category": "Contract", "text": "Field amount removed",
                  "impact": "breaks the web consumer", "how_to_reproduce": "run the provider verification", "recommendation": "do not remove fields"}],
    "recommendations": [{"priority": "High", "action": "Restore 'amount'", "reason": "compatibility"}],
    "next_steps": ["Run can-i-deploy"],
    "missing_info": [{"id": "MI-01", "what_is_missing": "pact version", "question": "which one?"}],
}


def _gen(tmp_path, data, monkeypatch):
    monkeypatch.setenv("K0LMENIA_PORTAL", "0")
    (tmp_path / "a.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    gi.generate(tmp_path / "a.json", tmp_path / "i.html")
    return (tmp_path / "i.html").read_text(encoding="utf-8")


def test_full_report(tmp_path, monkeypatch):
    html = _gen(tmp_path, ANALYSIS, monkeypatch)
    assert "Contracts — US-010" in html and "Contract testing" in html
    assert "payments-api" in html  # extra meta
    assert "Interactions" in html and "Field amount removed" in html
    assert "Contract coverage" in html and "TC-001" in html and "MI-01" in html
    assert "run the provider verification" in html  # "How to reproduce" section
    assert "Run can-i-deploy" in html  # next steps


def test_minimal(tmp_path, monkeypatch):
    html = _gen(tmp_path, {"title": "Empty"}, monkeypatch)
    assert "No findings." in html and "Empty" in html


def test_invalid_json_fails(tmp_path):
    (tmp_path / "x.json").write_text("{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        gi.generate(tmp_path / "x.json", tmp_path / "i.html")
