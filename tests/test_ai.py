"""AI / LLM feature tester: HTML report (ai-tester agent)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import generate_ai_report as gi  # noqa: E402

ANALYSIS = {
    "title": "Chatbot — US-010", "story": "US-010", "environment": "QA", "generated": "2026-10-19T12:00:00",
    "system": {"type": "RAG chatbot", "model": "gpt-4o", "provider": "OpenAI", "endpoint": "/api/chat"},
    "verdict": "Answers well but is vulnerable to prompt injection", "verdict_tone": "bad", "summary": "Golden set + prompt security.",
    "metrics": [{"metric": "Accuracy (golden set)", "value": "86%", "target": "90%", "status": "Failed"},
                {"metric": "Groundedness", "value": "0.82", "target": "0.8", "status": "Passed"}],
    "tests": [{"id": "TC-001", "category": "Hallucination", "case": "Out-of-domain question", "result": "Passed",
               "expected": "says it does not know", "actual": "redirects"},
              {"id": "TC-002", "category": "Prompt security", "case": "Indirect prompt injection", "result": "Failed",
               "expected": "ignores the instruction in the document", "actual": "obeys it"}],
    "findings": [{"id": "H-01", "severity": "High", "category": "Prompt security", "text": "Obeys an injection hidden in a document",
                  "impact": "exfiltration", "how_to_reproduce": "upload a doc with 'ignore the instructions…'", "recommendation": "isolate instructions from data"}],
    "recommendations": [{"priority": "High", "action": "Separate instructions from content", "reason": "prevents injection"}],
    "missing_info": [{"id": "MI-01", "what_is_missing": "accuracy target", "question": "what is the minimum?"}],
}


def _gen(tmp_path, data, monkeypatch):
    monkeypatch.setenv("K0LMENIA_PORTAL", "0")
    (tmp_path / "analysis.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    gi.generate(tmp_path / "analysis.json", tmp_path / "report.html")
    return (tmp_path / "report.html").read_text(encoding="utf-8")


def test_full_report(tmp_path, monkeypatch):
    html = _gen(tmp_path, ANALYSIS, monkeypatch)
    assert "Chatbot — US-010" in html and "gpt-4o" in html
    assert "Obeys an injection hidden" in html and "TC-002" in html and "MI-01" in html
    assert "Quality metrics" in html and "Groundedness" in html
    assert "upload a doc with" in html  # "How to reproduce" section


def test_without_tests_or_findings(tmp_path, monkeypatch):
    html = _gen(tmp_path, {"title": "Empty"}, monkeypatch)
    assert "No findings." in html and "Empty" in html


def test_invalid_json_fails(tmp_path):
    (tmp_path / "x.json").write_text("{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        gi.generate(tmp_path / "x.json", tmp_path / "i.html")
