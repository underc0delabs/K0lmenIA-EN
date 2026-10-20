"""Run history (last 5, with the comparison) and the emails and translations reports."""
import json

import _history
import generate_emails_report
import generate_translation_report


def _run(folder, stamp, findings):
    (folder / "exploration.json").write_text(json.dumps({"stamp": stamp, "summary": {"findings": len(findings), "broken_links": len(findings)},
                                                         "findings": findings}), encoding="utf-8")
    (folder / "exploratory-report.html").write_text("<html></html>", encoding="utf-8")


def test_archive_keeps_last_5(tmp_path):
    for i in range(7):
        _run(tmp_path, f"2026101{i}-120000", [])
        target = _history.archive(tmp_path, ["exploration.json", "exploratory-report.html"], "exploration.json")
        assert (target / "exploration.json").exists() and not (tmp_path / "exploration.json").exists()
    saved = sorted(d.name for d in (tmp_path / "history").iterdir())
    assert len(saved) == 4 and saved[0] == "20261013-120000"
    assert _history.archive(tmp_path, ["exploration.json"], "exploration.json") is None  # there is no current run


def test_comparison_new_resolved_and_section(tmp_path):
    a = {"category": "Broken link", "title": "Broken link to /old (404)", "page": "/"}
    b = {"category": "Broken image", "title": "Image that does not load", "page": "/"}
    c = {"category": "JavaScript error", "title": "x is not defined", "page": "/x"}
    _run(tmp_path, "20261010-100000", [a, b])
    _history.archive(tmp_path, ["exploration.json", "exploratory-report.html"], "exploration.json")
    current = {"stamp": "20261011-100000", "summary": {"findings": 2, "broken_links": 1}, "findings": [dict(a, title="Broken link to /old (500)"), c]}
    cmp = _history.compare("exploratory", current, json.loads((next((tmp_path / "history").iterdir()) / "exploration.json").read_text(encoding="utf-8")))
    assert [x["title"] for x in cmp["new"]] == ["x is not defined"]
    assert [x["title"] for x in cmp["resolved"]] == ["Image that does not load"]
    assert len(cmp["persisting"]) == 1   # the same link even if the code changes (numbers do not count)
    html = _history.section("exploratory", tmp_path, current)
    assert "Run history" in html and "open report" in html and "x is not defined" in html and "Image that does not load" in html
    assert "first run" in _history.section("exploratory", tmp_path / "empty", current)


def test_emails_report():
    data = {"mailpit": "http://localhost:8025", "filter": 'to:"ann@test.com"',
            "summary": {"emails": 1, "expectations": 2, "met": 1, "not_received": 1, "findings": 2, "links": 2, "problem_links": 1,
                        "unreplaced_variables": 1, "compatibility_avg": 88},
            "expectations": [{"id": "E-01", "case": "TC-001", "subject": "Welcome", "to": "ann@test.com", "status": "Met", "email": "M-01",
                              "checks": [{"name": "Contains “Hello”", "ok": True}]},
                             {"id": "E-02", "case": "TC-007", "subject": "Recover", "to": "ann@test.com", "status": "Not received", "checks": []}],
            "findings": [{"id": "C-01", "type": "Expectation", "severity": "Critical", "title": "The expected email «Recover» did not arrive", "email": None},
                         {"id": "C-02", "type": "Unreplaced variable", "severity": "High", "title": "{{n}} in the subject", "email": "M-01", "detail": "x"}],
            "emails": [{"id": "M-01", "subject": "Order {{n}}", "from": "a@b.com", "to": ["ann@test.com"], "cc": [], "reply_to": [], "date": "2026-10-11T10:00:00",
                        "size_kb": 1, "html_kb": 1, "has_text": False, "attachments": [{"name": "invoice.pdf", "kb": 40}],
                        "links": [{"url": "http://localhost/x", "text": "View", "problem": {"severity": "High", "text": "points to a local environment"}}],
                        "compatibility": {"pct": 88, "problems": [{"title": "border-radius", "clients": ["Outlook (windows)"]}]},
                        "desktop_screenshot": "screenshots/a-desktop.png", "mobile_screenshot": "screenshots/a-mobile.png", "eml": "eml/a.eml", "view_in_mailpit": "http://x/view/a"}]}
    html = generate_emails_report.build_html(data, {"findings": {"C-02": {"note": "Everyone sees it"}}})
    assert "expected email(s) did not arrive" in html and "What had to arrive" in html and "invoice.pdf (40 KB)" in html
    assert "points to a local environment" in html and "Everyone sees it" in html and "Mobile (375 px)" in html


def test_translator_report():
    data = {"host": "x.com", "languages": ["es", "en"], "reference": "es",
            "summary": {"pages": 1, "screens": 2, "untranslated": 1, "keys": 0, "truncated": 0, "formats": 0,
                        "by_language": {"es": {"translated_pct": 100, "findings": 0, "method": "reference"}, "en": {"translated_pct": 92.5, "findings": 1, "method": "hreflang"}}},
            "screens": [{"page": "01-home", "url": "https://x.com/", "resolution": "1366x768", "language": i, "screenshot": f"screenshots/{i}.png", "findings": n, "lang": i}
                        for i, n in (("es", 0), ("en", 1))],
            "findings": [{"id": "T-01", "type": "Untranslated", "severity": "High", "language": "en", "title": "“Agregar al carrito” is in es", "detail": "x",
                          "where": [{"url": "https://x.com/en/", "resolution": "1366x768", "crop": "crops/1.png"}]}]}
    html = generate_translation_report.build_html(data, {"findings": {"T-01": {"suggestion": "Add to cart"}}})
    assert "Translated by language" in html and "Suggestion: Add to cart" in html and "Each page in every language" in html and "92.5" in html
