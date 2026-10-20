"""Onboarding plan (onboarding-guide agent)."""
import json

import generate_onboarding as onb

PLAN = {
    "person": "Ana Pérez", "role": "Manual QA", "project": "Store", "date": "2026-10-14",
    "summary": "Online store with checkout and back office.",
    "product": {"modules": [{"name": "Checkout", "description": "Card payment", "source": "project/summary.md"}],
                "roles": [{"role": "Buyer", "can": "buy"}],
                "flows": [{"name": "Buy", "screens": "Cart → Payment", "source": "functional-map.md"}],
                "glossary": [{"term": "SKU", "definition": "product code"}]},
    "environment": [{"what": "Doctor", "status": "missing", "detail": ".env does not exist", "action": "cp .env.example .env"}],
    "agents": [{"agent": "manual-case-generator", "purpose": "cases", "request": "Generate the cases for PROJ-12"}],
    "plan": [{"when": "Day 1", "task": "Run the doctor", "done_when": "0 missing", "agent": "npm run doctor"}],
    "questions": [{"id": "MI-01", "question": "Installment limit?", "to_whom": "PO", "why": "it is not in the story"}],
    "checklist": ["Have the .env complete", "Run npm test"],
    "missing": ["There is no functional map."],
}


def test_html_and_md(tmp_path):
    file = tmp_path / "plan.json"
    file.write_text(json.dumps(PLAN, ensure_ascii=False), encoding="utf-8")
    assert onb.main([str(file), "--output", str(tmp_path / "o")]) == 0
    html = (tmp_path / "o" / "onboarding-plan.html").read_text(encoding="utf-8")
    assert "Onboarding for Ana Pérez" in html and "Generate the cases for PROJ-12" in html and "MI-01" in html
    assert html.count('type="checkbox"') == 2 and "localStorage" in html and "1 pending" in html
    md = (tmp_path / "o" / "onboarding-plan.md").read_text(encoding="utf-8")
    assert "- [ ] Run npm test" in md and "Checkout" in md and "> There is no functional map." in md


def test_slug_and_validation(tmp_path):
    assert onb.slug("Ana Pérez") == "ana-perez"
    file = tmp_path / "x.json"
    file.write_text("{}", encoding="utf-8")
    import pytest
    with pytest.raises(SystemExit):
        onb.main([str(file)])
