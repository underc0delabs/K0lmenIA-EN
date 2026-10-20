"""Quality of the reports of the exploration and audit agents: unified Missing information, analysis
warnings, fix of the manual findings, permissions evidence, resilience steps and ZAP secrets."""
import pytest

import _report_styles
import generate_accessibility_report
import generate_emails_report
import generate_exploratory_report
import generate_forms_report
import generate_logs_report
import generate_permissions_report
import generate_pixel_perfect_report
import generate_web_performance_report
import generate_resilience_report
import generate_security_report
import generate_translation_report
import generate_ux_report

MI = {"missing_info": [{"id": "MI-01", "what_is_missing": "The maximum length of the name", "question": "How many characters does it accept?"}]}
WITH_MI = [generate_exploratory_report, generate_accessibility_report, generate_web_performance_report, generate_pixel_perfect_report,
           generate_ux_report, generate_forms_report, generate_permissions_report, generate_resilience_report,
           generate_emails_report, generate_translation_report, generate_logs_report]


@pytest.mark.parametrize("module", WITH_MI, ids=lambda m: m.__name__.replace("generate_", "").replace("_report", ""))
def test_missing_info_in_each_report(module):
    html = module.build_html({}, MI)
    assert "Missing information" in html and "The maximum length of the name" in html and "How many characters does it accept?" in html


def test_missing_info_in_security():
    assert "The maximum length of the name" in generate_security_report.build_html({}, MI, None, None)


def test_missing_info_accepts_description_as_alias():
    html = _report_styles.missing_info([{"id": "MI-02", "description": "What happens offline"}])
    assert "MI-02" in html and "What happens offline" in html
    assert _report_styles.missing_info([]) == ""


def test_notify_analysis_nonexistent_ids_and_severities(capsys):
    analysis = {"notes": {"H-3": "x"}, "severities": {"H-01": "high"}, "discarded": [{"id": "H-02", "reason": "y"}],
                "findings": {"H-01": {"severity": "Medium"}}}
    warnings = _report_styles.warn_analysis(analysis, ["H-01", "H-02"])
    assert len(warnings) == 2
    err = capsys.readouterr().err
    assert "H-3 is not in the data" in err and "'high'" in err
    assert _report_styles.warn_analysis({"notes": {"H-01": "ok"}}, ["H-01"]) == []


def test_manual_findings_correction():
    m = {"id": "M-01", "title": "Unannounced error", "severity": "High", "fix": "Add aria-live to the message"}
    assert "Add aria-live to the message" in generate_accessibility_report.build_html({}, {"manual": [m]})
    ex = dict(m, id="EX-01", fix="Validate the length on the client")
    assert "Validate the length on the client" in generate_exploratory_report.build_html({}, {"exploratory": [ex]})


def test_manual_ux_with_url_and_correction():
    html = generate_ux_report.build_html({"heuristics": {"H1": "Visibility of system status"}}, {"manual_findings": [
        {"heuristic": "H1", "severity": "High", "title": "No confirmation when paying", "detail": "...",
         "fix": "Show the order number", "url": "https://app.test/checkout", "screenshot": "screenshots/manual-1.png"}]})
    assert "Show the order number" in html and "checkout" in html


def test_permissions_additional_with_its_screenshot():
    html = generate_permissions_report.build_html({}, {"additional": [
        {"severity": "Medium", "type": "Button", "title": "The guest sees Delete", "detail": "...", "role": "guest",
         "url": "https://app.test/orders", "screenshot": "screenshots/manual/pm-01.png", "fix": "Hide the button by role"}]})
    assert "screenshots/manual/pm-01.png" in html and "Hide the button by role" in html


def test_manual_resilience_with_list_steps_and_page():
    html = generate_resilience_report.build_html({}, {"manual": [
        {"id": "RM-01", "title": "Double submit", "severity": "Medium", "scenario": "slow", "page": "https://app.test/cart",
         "steps": ["Open the cart", "Press Pay twice"], "expected": "One order", "actual": "Two orders",
         "fix": "Disable the button while it waits"}]})
    assert "Open the cart → Press Pay twice" in html and "[&#x27;" not in html
    assert "https://app.test/cart" in html and "Disable the button while it waits" in html


def test_security_masks_secrets_in_evidence():
    token = "eyJhbGciOiJIUzI1NiJ9abc123DEF456"
    assert token not in generate_security_report.mask(f"Authorization: Bearer {token}")
    assert generate_security_report.mask("Content-Security-Policy-Report-Only") == "Content-Security-Policy-Report-Only"
    zap = {"site": [{"@name": "https://app.test", "alerts": [{"pluginid": "10105", "name": "Exposed token", "riskcode": "2",
                                                              "confidence": "2", "instances": [{"uri": "https://app.test", "evidence": f"Bearer {token}"}]}]}]}
    html = generate_security_report.build_html(zap, {}, "https://app.test", None)
    assert "Exposed token" in html and token not in html and "Bearer eyJh…" in html
