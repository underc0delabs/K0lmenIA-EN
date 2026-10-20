"""Report of a project survey (project-researcher agent)."""
import json

import pytest

import generate_research_report as inv

SURVEY = {
    "project": "Online store", "key": "PROJ", "date": "2026-10-19", "depth": "normal", "audience": "Manual QA",
    "board": "https://my-company.atlassian.net/jira/software/projects/PROJ/boards/12",
    "summary": "Online store with checkout, wallet and back office.",
    "coverage": {"total_items": 400, "read": 80, "criteria": "Open critical ones and current sprint",
                 "epics": 2, "stories": 3, "tasks": 7, "comments": 20},
    "hierarchy": [{"epic": {"id": "PROJ-3", "title": "Checkout", "status": "In progress", "url": "https://x/PROJ-3"},
                   "stories": [{"id": "PROJ-12", "title": "Card payment", "status": "In progress", "assignee": "Ann",
                                "tasks": 4, "comments": 7, "links": ["Confluence 'Payment rules'"],
                                "note": "decision: up to 12 installments", "url": "https://x/PROJ-12"}]}],
    "references": [{"type": "Confluence", "title": "Payment rules", "url": "https://x/wiki/payments", "origin": "PROJ-12 (comment)", "read": True}],
    "maps": [{"title": "Architecture", "type": "architecture", "description": "Layers and external systems.",
              "nodes": [{"id": "web", "label": "Web front end", "group": "Frontend"},
                        {"id": "api", "label": "API", "group": "Backend", "note": "REST"},
                        {"id": "db", "label": "PostgreSQL", "group": "Data"}],
              "edges": [{"from": "web", "to": "api", "label": "HTTPS"}, {"from": "api", "to": "db"}]},
             {"title": "How it works", "type": "flow",
              "nodes": [{"id": "s1", "label": "Cart"}, {"id": "s2", "label": "Payment"}, {"id": "s3", "label": "Confirms"}],
              "edges": [{"from": "s1", "to": "s2"}, {"from": "s2", "to": "s3"}, {"from": "s3", "to": "s2", "label": "retries"}]}],
    "sources": [{"source": "Jira PROJ", "type": "Management", "scope": "epics and backlog", "status": "read"},
                {"source": "Figma", "type": "Design", "status": "not_accessible", "reason": "figma connector not active"}],
    "modules": [{"name": "Checkout", "description": "Card payment", "status": "In development",
                 "progress": {"done": 6, "total": 8}, "source": "PROJ-3"}],
    "actors": [{"role": "Buyer", "can": "buy", "source": "PROJ-3"}],
    "flows": [{"name": "Buy", "steps": "Cart → Payment", "items": "PROJ-12", "source": "PROJ-3"}],
    "integrations": [{"system": "Stripe", "purpose": "charges", "type": "REST API", "source": "wiki/Integrations"}],
    "environments": [{"name": "QA", "url": "https://qa.store.com", "purpose": "testing", "source": "wiki/Environments"}],
    "backlog": {"by_status": {"To do": 40, "Done": 300}, "bugs_by_severity": {"Critical": 2, "Low": 4},
                "current_sprint": {"name": "Sprint 14", "start": "2026-10-13", "end": "2026-10-24", "items": 18},
                "releases": [{"name": "2.4", "date": "2026-11-05", "status": "Planned", "source": "Jira"}]},
    "ambiguities": [{"id": "AMB-01", "type": "Contradiction", "what": "Immediate refund vs. 48 business hours",
                     "sources": ["PROJ-45", "Confluence 'Payment rules'"], "impact": "High", "question": "Q-01"}],
    "questions": [{"id": "Q-01", "question": "Is the refund immediate or does it take 48 h?", "to_whom": "PO", "priority": "Critical",
                   "why": "blocks the refund cases", "related": "AMB-01"}],
    "startup_questions": ["How do you request test data in QA?"],
    "risks": [{"risk": "No payments sandbox", "level": "High", "reason": "there is no environment", "mitigation": "request it"}],
    "glossary": [{"term": "SKU", "definition": "product code", "source": "wiki/Glossary"}],
    "next_steps": [{"step": "Onboarding", "agent": "onboarding-guide", "request": "Build Ann's onboarding"}],
    "missing": ["There is no Figma connector."],
}


def _write(folder, data):
    folder.mkdir(parents=True, exist_ok=True)
    file = folder / "research.json"
    file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return file


def test_html_and_md(tmp_path):
    file = _write(tmp_path / "proj", SURVEY)
    assert inv.main([str(file)]) == 0
    html = (tmp_path / "proj" / "research-report.html").read_text(encoding="utf-8")
    assert "Survey of Online store" in html
    assert "AMB-01" in html and "Q-01" in html and "Immediate refund" in html
    assert "PROJ-45 <b>vs.</b> Confluence" in html  # the two sources of the contradiction, together
    assert "Not accessible" in html and "1/2" in html and "6/8 · 75%" in html
    assert "Changes since the previous survey" not in html  # it is the first one
    # Board walkthrough: epics/stories/tasks, with clickable links
    assert "Epics, stories and tasks" in html and "Reference links" in html
    assert "Backlog walked" in html and "Surveyed from the board" in html
    assert 'href="https://x/PROJ-12"' in html and "Payment rules" in html and "up to 12 installments" in html
    md = (tmp_path / "proj" / "research-report.md").read_text(encoding="utf-8")
    assert "Online store" in md and "PROJ-45 vs. Confluence" in md and "> There is no Figma connector." in md
    assert "## Epics, stories and tasks" in md and "## Reference links" in md
    assert "[Payment rules](https://x/wiki/payments)" in md and "Board walkthrough: 2 epic" in md
    assert len(list((tmp_path / "proj" / "history").iterdir())) == 1
    # Concept maps (SVG) in the report
    assert html.count('class="map"') == 2 and "<svg viewBox" in html and "Architecture" in html and "How it works" in html
    assert "back" in html  # the return edge (retries) is dashed
    # Short summary
    summary = (tmp_path / "proj" / "summary.md").read_text(encoding="utf-8")
    assert "# Online store — summary" in summary and "The 3 most urgent questions" in summary and "refund" in summary.lower()
    # Self-contained presentation
    pres = (tmp_path / "proj" / "research-presentation.html").read_text(encoding="utf-8")
    assert pres.startswith("<!doctype html>") and "At a glance" in pres and "Architecture" in pres
    assert pres.count('<section class="s"') >= 5 and "print to PDF" in pres


def test_compares_with_previous_survey(tmp_path):
    folder = tmp_path / "proj"
    assert inv.main([str(_write(folder, SURVEY))]) == 0
    new = json.loads(json.dumps(SURVEY))
    new["ambiguities"] = [{"id": "AMB-01", "type": "Gap", "what": "There are no criteria for the coupon", "impact": "Medium"}]
    new["questions"] = [{"id": "Q-01", "question": "Does the coupon stack with other promos?", "priority": "High"}]
    import time
    time.sleep(1.1)  # the history is named by the second
    assert inv.main([str(_write(folder, new))]) == 0
    html = (folder / "research-report.html").read_text(encoding="utf-8")
    assert "Changes since the previous survey" in html
    assert "There are no criteria for the coupon" in html and "Immediate refund vs. 48 business hours" in html  # new and resolved
    assert "Resolved" in html and "New" in html


def test_warns_about_inconsistencies(capsys):
    d = {"project": "X",
         "ambiguities": [{"id": "AMB-01", "type": "Contradiction", "what": "a", "sources": ["only one"], "question": "Q-09"},
                         {"id": "AMB-01", "type": "Odd", "what": "b", "impact": "Highest"}],
         "questions": [{"id": "Q-01", "question": "?", "priority": "Urgent"}],
         "sources": [{"source": "Jira", "status": "done"}]}
    warnings = inv.validate(d)
    text = " ".join(warnings)
    assert "repeated IDs AMB-01" in text and "two sources" in text and "Q-09" in text
    assert "'Odd'" in text and "'Highest'" in text and "'Urgent'" in text and "'done'" in text
    assert "[warning]" in capsys.readouterr().err


def test_requires_project(tmp_path):
    file = tmp_path / "x.json"
    file.write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit):
        inv.main([str(file)])


def test_history_is_pruned(tmp_path):
    for i in range(7):
        (tmp_path / "history" / f"2026-10-0{i + 1}-000000").mkdir(parents=True)
    inv.save_history(tmp_path, [], maximum=5)
    assert len(list((tmp_path / "history").iterdir())) == 5
