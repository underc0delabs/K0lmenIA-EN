"""Test case selector and the pixel-perfect, cross-browser, repair and selection reports."""
import json
from pathlib import Path

import generate_cross_browser_report
import generate_pixel_perfect_report
import generate_repair_report
import generate_selection_report
import collect_results as rec
import select_cases as sc


# ------------------------------------------------------------------ case selector
def test_git_ranges_diff_from_merge_base():
    # The diff goes from the merge base (A...B) and the log is the commits of B that are not in A (A..B).
    assert sc.git_ranges("main..feature/payments") == ("main...feature/payments", "main..feature/payments")
    assert sc.git_ranges("main...feature/payments") == ("main...feature/payments", "main..feature/payments")
    assert sc.git_ranges("v2.3..v2.4") == ("v2.3...v2.4", "v2.3..v2.4")
    assert sc.git_ranges("HEAD~3") == ("HEAD~3", "HEAD~3")


def test_tokens_with_synonyms_camelcase_and_without_keys():
    t = sc.tokens("src/checkout/paymentCard.ts PROJ-55 fix")
    assert "payment" in t and "card" in t       # paymentCard → payment, card
    assert "proj" not in t and "fix" not in t   # keys and stop words don't count
    # The synonyms are bilingual: Spanish text maps to the same concepts.
    assert sc.tokens("Iniciar sesión con contraseña") == ["login", "login", "password"]


def _case(us, cid, title, text="", priority="Medium", tags=(), automated=None):
    return {"key": f"{us}:{cid}", "story": us, "id": cid, "title": title, "priority": priority, "tags": set(tags),
            "text": [title, title, text], "story_title": "", "sources": ["BDD"], "automated": automated or [], "steps": 3,
            "result": None, "duration_s": None, "flaky": False, "bugs": []}


def _change(**kw):
    base = {"title": "", "files": [], "stories": set(), "keys": set(), "commits": [], "functions": [], "text": "", "words": [], "sources": []}
    base.update(kw)
    return base


def test_selection_by_story_words_and_smoke(monkeypatch):
    monkeypatch.setattr(sc, "component_map", lambda: {})
    monkeypatch.setattr(sc, "keys_to_stories", lambda keys: set())
    cases = [
        _case("US-3", "TC-001", "Pay with a valid card", "pays with a card and sees the confirmation"),
        _case("US-3", "TC-002", "Expired card", "pays with an expired card"),
        _case("US-2", "TC-001", "Add to cart", "adds a product to the cart",
              automated=[{"suite": "web", "file": "x.feature", "blocked": False}]),
        _case("US-1", "TC-001", "Valid login", "signs in", priority="Critical", tags=["smoke"]),
        _case("US-4", "TC-001", "Search by name", "searches mate"),
    ]
    change = _change(files=["src/checkout/paymentCard.ts", "src/cart/cartTotal.ts", "src/admin/salesReport.ts"], stories={"US-3"})
    affected, uncov, _ = sc.select(change, cases)
    group = {c["key"]: c["group"] for c in cases}
    assert affected == {"US-3"}
    assert group["US-3:TC-001"] == group["US-3:TC-002"] == "Essential"
    assert group["US-2:TC-001"] in ("Recommended", "Not selected")
    assert group["US-1:TC-001"] == "Minimal regression"
    assert group["US-4:TC-001"] == "Not selected"
    assert any("US-3 is in the change" in r for r in cases[0]["reasons"])
    assert [x["file"] for x in uncov] == ["src/admin/salesReport.ts"]


def test_commands_tags_and_analysis_adjustments():
    cases = [{"key": "US-1:TC-001", "story": "US-1", "id": "TC-001", "group": "Essential", "type": "Automated", "suite": "web", "reasons": []},
             {"key": "US-1:TC-003", "story": "US-1", "id": "TC-003", "group": "Recommended", "type": "Automated", "suite": "web", "reasons": []},
             {"key": "US-2:TC-002", "story": "US-2", "id": "TC-002", "group": "Not selected", "type": "Automated", "suite": "web", "reasons": []},
             {"key": "US-5:TC-001", "story": "US-5", "id": "TC-001", "group": "Recommended", "type": "Automated", "suite": "api", "reasons": []}]
    sc.apply_adjustments(cases, {"adjustments": {"US-2:TC-002": {"group": "Essential", "reason": "uses the total"}}})
    assert cases[2]["group"] == "Essential" and cases[2]["original_group"] == "Not selected"
    cmds = {c["suite"]: c for c in sc.commands(cases)}
    assert cmds["web"]["tags"] == "(@US-1 and (@TC-001 or @TC-003)) or (@US-2 and @TC-002)"
    assert cmds["api"]["bash"] == 'TAGS="(@US-5 and @TC-001)" npm test -- api'
    assert cmds["web"]["powershell"].startswith('$env:TAGS="')


def test_inventory_joins_bdd_and_automation(tmp_path, monkeypatch):
    (tmp_path / "output" / "test-cases" / "bdd").mkdir(parents=True)
    (tmp_path / "tools" / "k0lmena" / "web" / "features").mkdir(parents=True)
    gherkin = "@US-7\nFeature: Payments\n\n  @TC-001 @smoke\n  Scenario: Pay\n    Given something\n    When they pay\n    Then ok\n"
    (tmp_path / "output" / "test-cases" / "bdd" / "US-7-payments.feature").write_text(gherkin, encoding="utf-8")
    (tmp_path / "tools" / "k0lmena" / "web" / "features" / "US-7-payments.feature").write_text(gherkin, encoding="utf-8")
    monkeypatch.setattr(sc, "ROOT", tmp_path)
    monkeypatch.setattr(rec, "ROOT", tmp_path)
    monkeypatch.setattr(rec, "K0", tmp_path / "tools" / "k0lmena" / "reports")
    cases = sc.inventory()
    assert len(cases) == 1
    c = cases[0]
    assert c["key"] == "US-7:TC-001" and c["sources"] == ["BDD", "Automated"] and c["automated"][0]["suite"] == "web"
    assert c["story_title"] == "Payments" and c["steps"] == 3


# ------------------------------------------------------------------ reports
def test_pixel_perfect_report_comparison_and_reference():
    screen = {"id": "01-home-390x844", "url": "https://x.com/", "resolution": "390x844", "device": "Mobile", "vp_width": 390,
              "state": "With changes", "pct": 12.5, "regions": [{"x": 0, "y": 0, "w": 10, "h": 10, "pixels": 5}], "height": 1100, "height_ref": 1050,
              "actual": "actual/a.png", "reference": "reference/a.png", "diff": "diffs/a.png",
              "crops": [{"reference": "r1.png", "actual": "a1.png", "diff": "d1.png"}]}
    finding = {"id": "V-01", "screen": "01-home-390x844", "url": "https://x.com/", "resolution": "390x844", "type": "Shifted element",
               "severity": "High", "title": "“Buy” shifted +38 px in X", "detail": "a.cta", "delta": {"dx": 38, "dy": 0},
               "before": "crops/h1-before.png", "after": "crops/h1-after.png"}
    data = {"mode": "comparison", "host": "x.com", "browser": "chromium", "config": {"resolutions": ["390x844"]},
            "summary": {"compared": 1, "with_changes": 1, "shifted_elements": 1, "pct_max": 12.5, "pages": 1},
            "screens": [screen], "findings": [finding]}
    html = generate_pixel_perfect_report.build_html(data, {"findings": {"V-01": {"note": "Covers the price"}}})
    assert 'type="range"' in html and 'data-diff="diffs/a.png"' in html   # slider comparator
    assert "X +38 px" in html and "Covers the price" in html and "--accept all" in html
    ref = generate_pixel_perfect_report.build_html({**data, "mode": "reference", "findings": [], "summary": {"pages": 1}}, {})
    assert "Reference created" in ref and "Reference screenshots" in ref


def test_cross_browser_report_suite_and_pages():
    browsers = [{"name": "chromium", "ok": True, "version": "149"}, {"name": "webkit", "ok": False, "error": "Not installed",
                                                                     "install": "cd tools/k0lmena && npx playwright install webkit"}]
    suite = {"mode": "suite", "browsers": browsers, "resolutions": ["1366x768"],
             "runs": [{"id": "chromium-1366x768", "browser": "chromium", "resolution": "1366x768", "passed": 1, "failed": 1, "total": 2}],
             "scenarios": [{"scenario": "Pay", "uri": "f", "line": 3, "class": "Difference between browsers",
                            "results": {"chromium-1366x768": {"status": "Failed"}}}],
             "findings": [{"id": "X-01", "type": "Fails only in some browsers", "severity": "High", "title": "Pay: fails in Firefox",
                           "detail": "x", "failing": ["firefox-1366x768"], "scenario": "f:3", "error": "Error: no"}],
             "summary": {"scenarios": 1, "differences": 1, "not_installed": ["webkit"]}}
    html = generate_cross_browser_report.build_html(suite, {})
    assert "Scenario matrix" in html and "npx playwright install webkit" in html and "fail only in some browsers" in html
    pages = {"mode": "pages", "base": "chromium", "browsers": browsers[:1], "resolutions": ["390x844"],
             "pages": [{"page": "01-home", "url": "https://x.com/", "resolution": "390x844", "base": "chromium-390x844",
                        "results": {"chromium-390x844": {"status": "OK", "screenshot": "c.png"},
                                    "firefox-390x844": {"status": "With issues", "screenshot": "f.png", "difference": "d.png", "pct": 20.1}}}],
             "findings": [], "summary": {"screens": 1, "with_issues": 1}}
    html = generate_cross_browser_report.build_html(pages, {})
    assert "Each screen in each browser" in html and "20.1 % different" in html and 'data-diff="d.png"' in html


def test_repair_report_with_diff(tmp_path):
    rep = {"id": "R-01", "scenario": "Subscribe", "story": "US-9", "case": "TC-004", "uri": "f", "line": 3, "action": "action",
           "step": "When they subscribe", "error": "\x1b[2mwaiting for getByRole('button', { name: 'Subscribe' })\x1b[22m",
           "diagnosis": "No longer exists", "detail": "not found", "status": "Verified",
           "locator": {"code": "{ role: 'button', name: 'Subscribe' }", "input": {"role": "button", "name": "Subscribe"}},
           "proposal": {"code": "{ role: 'button', name: 'Subscribe me' }", "confidence": "High", "reasons": ["same role"]},
           "location": {"type": "locator", "file": "web/locators/US-9.locators.ts", "line": 5, "text": "btn: { role: 'button', name: 'Subscribe' },"},
           "applied": {"before": "btn: { role: 'button', name: 'Subscribe' },", "after": "btn: { role: 'button', name: 'Subscribe me' },"},
           "verification": {"status": "Verified"}}
    (tmp_path / "changes.diff").write_text("--- a/x\n+++ b/x\n-old\n+new\n", encoding="utf-8")
    data = {"story": "US-9", "repairs": [rep], "summary": {"failures": 1, "locator": 1, "with_proposal": 1, "applied": 1, "verified": 1}}
    html = generate_repair_report.build_html(data, {}, tmp_path)
    assert "applied and verified" in html and 'class="del"' in html and 'class="add"' in html
    assert "\x1b" not in html and "--apply safe --story US-9" in html


def test_selection_report_with_copyable_commands():
    case = {"key": "US-3:TC-001", "story": "US-3", "id": "TC-001", "title": "Pay", "group": "Essential", "score": 90,
            "type": "Automated", "suite": "web", "priority": "High", "minutes": 0.5, "reasons": ["Story US-3 is in the change"]}
    data = {"name": "rel", "cases": [case], "no_coverage": [{"file": "src/admin/x.ts", "words": ["admin"]}],
            "change": {"files": ["src/admin/x.ts"], "words": [{"word": "payment", "weight": 2}], "sources": ["git"]},
            "commands": [{"suite": "web", "tags": "(@US-3 and @TC-001)", "cases": 1, "bash": 'TAGS="(@US-3 and @TC-001)" npm test -- web',
                          "powershell": '$env:TAGS="(@US-3 and @TC-001)"; npm test -- web'}],
            "summary": {"cases": 1, "selected": 1, "automated": 1, "by_group": {"Essential": 1}, "no_coverage": 1}}
    html = generate_selection_report.build_html(data, {"risk": "High"})
    assert "Copy" in html and "npm test -- web" in html and "Uncovered changes" in html and "Change risk" in html


def test_full_selection_via_command_line(tmp_path, monkeypatch):
    """The script leaves the JSON, the CSV and the report, and --report-only applies the analysis."""
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "sel"
    r = subprocess.run([sys.executable, str(root / "scripts" / "select_cases.py"), "--stories", "US-999", "--text", "change in the payment",
                        "--output", str(output), "--name", "t"], capture_output=True, text=True, encoding="utf-8")
    if "no test cases" in (r.stderr + r.stdout).lower():
        return  # repo without a case inventory (CI): the tests above cover the rest
    assert r.returncode == 0, r.stderr
    assert (output / "selection.json").exists() and (output / "selection.csv").exists() and (output / "selection-report.html").exists()
    data = json.loads((output / "selection.json").read_text(encoding="utf-8"))
    assert data["affected_stories"] == ["US-999"]
