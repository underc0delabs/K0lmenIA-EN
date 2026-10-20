"""Agent evals (scripts/evaluate_agents.py): the verifiers with good and bad synthetic outputs.
They never call claude."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import evaluate_agents as ev  # noqa: E402
import generate_cases  # noqa: E402

CASES = {c["id"]: c for c in ev.load_cases()}


def _write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _failed(res):
    return {x["id"] for x in res["checks"] if not x["ok"]}


# ------------------------------------------------------------------ case catalog
def test_all_cases_are_valid():
    types = {"exists", "contains", "not_contains", "count", "order", "normalized_tables", "xlsx_columns", "xlsx_cases",
             "xlsx_types", "xlsx_missing_info", "xlsx_filter", "gherkin"}
    assert len(CASES) >= 6
    for c in CASES.values():
        assert c["agent"] and c["prompt"] and c["checks"], c["id"]
        ids = [ch["id"] for ch in c["checks"]]
        assert len(ids) == len(set(ids)), c["id"]
        for ch in c["checks"]:
            assert ch["type"] in types, (c["id"], ch["id"])
        for inp in c.get("inputs", []):
            assert ev._source(inp["from"], c).exists(), (c["id"], inp["from"])
        if not c.get("requires"):
            assert (ROOT / ".claude" / "agents" / f"{c['agent']}.md").exists(), c["id"]


def test_case_requiring_nonexistent_agent_is_skipped(tmp_path):
    assert ev.missing({"requires": [".claude/agents/does-not-exist.md"]}) == [".claude/agents/does-not-exist.md"]
    assert ev.missing({"requires": ["CLAUDE.md"]}) == []


# ------------------------------------------------------------------ workspace and command
def test_prepare_builds_isolated_workspace(tmp_path):
    ws = ev.prepare(CASES["project-documenter-local-repo"], tmp_path / "ws")
    assert (ws / "CLAUDE.md").exists() and (ws / ".claude" / "agents" / "project-documenter.md").exists()
    assert (ws / "scripts" / "format_tables.py").exists() and (ws / "templates").is_dir()
    assert (ws / "demo-repo" / "src" / "i18n" / "en.json").exists()
    assert (ws / "output" / "test-cases").is_dir() and not any((ws / "input" / "stories").iterdir())
    assert not (ws / "tools").exists() and not (ws / ".mcp.json").exists()
    env = (ws / ".env").read_text(encoding="utf-8")
    assert f"REPO_LOCAL_PATH={(ws / 'demo-repo').as_posix()}" in env
    assert (ws / "_eval" / "prompt.txt").read_text(encoding="utf-8") == CASES["project-documenter-local-repo"]["prompt"]


def test_headless_claude_command_with_scoped_permissions():
    cmd = ev.claude_command(CASES["story-analyst-signup-story"], model="claude-sonnet-5-5", max_turns=12)
    assert cmd[:3] == ["claude", "-p", CASES["story-analyst-signup-story"]["prompt"]]
    assert cmd[cmd.index("--output-format") + 1] == "json"
    assert cmd[cmd.index("--max-turns") + 1] == "12" and cmd[cmd.index("--model") + 1] == "claude-sonnet-5-5"
    assert cmd[cmd.index("--max-budget-usd") + 1] == "1.5"
    no_turns = ev.claude_command(CASES["story-analyst-signup-story"], budget_usd=0.5)
    assert "--max-turns" not in no_turns and no_turns[no_turns.index("--max-budget-usd") + 1] == "0.5"
    allowed = cmd[cmd.index("--allowedTools") + 1]
    assert "Write" in allowed and "Bash(python:*)" in allowed and "Bash(rm" not in allowed
    assert "--strict-mcp-config" in cmd


# ------------------------------------------------------------------ analyst
GOOD_ANALYSIS = """# Analysis US-901
## Summary
Account signup.
## Evaluation of acceptance criteria
```
+----+----+
| ID | ok |
+====+====+
```
## Ambiguities and assumptions
- AC3: the password has to be "secure", but the rules are not defined.
- Contradiction: the description says 18 years and AC4 says over 16. (MI-01)
- AC2: an already registered email shows an error, but the message text is not given. (MI-02)
- Unanswered comment: is the email case-sensitive (uppercase)? (MI-03)
## Scenarios not covered
- Username with 21 characters.
## Risks
- Minors signing up.
## Refinement questions
1. What is the minimum age, 16 or 18?
2. What text does the duplicate email error show?
3. What rules does a secure password have?
4. Is the email case-sensitive?
## Recommendations
- Unify the age.
"""


def test_good_analyst_passes(tmp_path):
    _write(tmp_path, "output/story-analysis/analysis-US-901.md", GOOD_ANALYSIS)
    res = ev.verify_case(CASES["story-analyst-signup-story"], tmp_path)
    assert res["status"] == "Passed" and res["score"] == 100, _failed(res)


def test_bad_analyst_fails_where_expected(tmp_path):
    bad = ("## Summary\nAll clear.\n## Questions\n1. Ok?\n"
           "| ID | Criterion |\n|----|----|\n| AC2 | the message \"The email is already registered\" is shown |\n"
           "The app shows \"The email is already registered\".\n")
    _write(tmp_path, "output/story-analysis/analysis-US-901.md", bad)
    res = ev.verify_case(CASES["story-analyst-signup-story"], tmp_path)
    assert res["status"] == "Failed"
    assert {"sections", "age-contradiction", "missing-info", "tables", "no-invented-message"} <= _failed(res)


def test_without_output_everything_fails(tmp_path):
    res = ev.verify_case(CASES["story-analyst-signup-story"], tmp_path)
    assert res["score"] == 0 and all(not x["ok"] for x in res["checks"])


# ------------------------------------------------------------------ manual cases (real spreadsheet from generate_cases.py)
def _case(n, title, prio="High", result="The account is created", tags="@signup", mi=None, **extra):
    c = {"id": f"TC-{n:03d}", "title": title, "description": title, "preconditions": "On the signup form", "data": extra.get("data", ""),
         "steps": "1. Fill in\n2. Submit", "result": result, "status": "Pending", "priority": prio, "tags": tags}
    if mi:
        c["missing_info"] = mi
    return c


def _good_cases():
    cases = [
        _case(1, "Signup with valid data", "Critical", 'The message "Account created! Check your email to activate it." is shown'),
        _case(2, "Email already registered", "Critical", "An error message is shown and the account is not created", mi=["MI-01"]),
        _case(3, "Username with 3 characters (lower limit - 1)", "High", 'The message "Username must be between 4 and 20 characters" is shown', tags="@negative"),
        _case(4, "Username with 4 characters (minimum limit)", "High"),
        _case(5, "Username with 20 characters (maximum limit)", "High"),
        _case(6, "Username with 21 characters", "High", 'The message "Username must be between 4 and 20 characters" is shown'),
        _case(7, "Minimum age: 17-year-old person", "High", "Depends on the minimum age the PO defines", mi=["MI-02"]),
        _case(8, "Email with an invalid format", "Medium", "The account is not created"),
        _case(9, "Empty name", "Medium", "The account is not created"),
        _case(10, "Weak password", "Medium", "The account is not created", mi=["MI-03"]),
        _case(11, "Name with 50 characters (maximum)", "Low"),
    ]
    return {"project": "Store", "module": "US-901 — Signup", "cases": cases,
            "missing_info": [{"id": f"MI-0{i}", "what_is_missing": "x", "question": "?"} for i in (1, 2, 3)]}


def _spreadsheet(tmp_path, data):
    folder = tmp_path / "output/test-cases/manual"
    folder.mkdir(parents=True, exist_ok=True)
    generate_cases.prepare_missing_info(data)
    generate_cases.prepare_times(data)
    generate_cases.to_xlsx(data, str(folder / "cases-US-901.xlsx"))
    _write(folder, "cases-US-901.md", "cases")
    _write(folder, "cases-US-901-coverage.md", "AC1 AC2 AC3 AC4 AC5\n## Missing information\nMI-01\n")


def test_good_manual_cases_pass(tmp_path):
    _spreadsheet(tmp_path, _good_cases())
    res = ev.verify_case(CASES["manual-cases-signup-story"], tmp_path)
    assert res["score"] == 100, [(x["id"], x["detail"]) for x in res["checks"] if not x["ok"]]


def test_bad_manual_cases_detect_each_issue(tmp_path):
    data = {"project": "Store", "module": "US-901", "cases": [
        _case(1, "Successful signup", "Medium"),
        _case(3, "Email already registered", "High", 'The message "The email is already registered" is shown'),
        _case(4, "Person under 18 years old", "Urgent", "The signup is rejected"),
    ]}
    _spreadsheet(tmp_path, data)
    res = ev.verify_case(CASES["manual-cases-signup-story"], tmp_path)
    detail = {x["id"]: x["detail"] for x in res["checks"] if not x["ok"]}
    assert {"valid-cases", "types", "user-limits", "missing-info", "duplicate-not-invented", "age-not-decided"} <= set(detail)
    assert "consecutive" in detail["valid-cases"] and "Urgent" in detail["valid-cases"]
    assert "invents" in detail["duplicate-not-invented"]


# ------------------------------------------------------------------ BDD
GOOD_FEATURE = """@US-901
Feature: Account signup

  Background:
    Given the person is on the signup form

  @TC-001 @smoke
  Scenario: Signup with valid data
    When they complete all the valid data
    Then they see the message "Account created! Check your email to activate it."

  @TC-002
  Scenario Outline: Username length out of range
    When they enter a username with <length> characters
    Then they see the message "Username must be between 4 and 20 characters"

    Examples:
      | length |
      | 3      |
      | 21     |

  # MISSING INFO (MI-01): text of the duplicate email error
  @TC-003 @missing-info @MI-01
  Scenario: Email already registered
    When they sign up with an email that is already registered
    Then they see an error message
    And the account is not created

  # MISSING INFO (MI-02): minimum age (16 or 18)
  @TC-004 @missing-info @MI-02
  Scenario: 17-year-old person
    When they enter a date of birth from 17 years ago
    Then the result depends on the minimum age the PO confirms

  @TC-005
  Scenario: Invalid email
    When they enter the email "ana@"
    Then the account is not created

  @TC-006
  Scenario: Name with accents
    When they enter the name "O'Connor Peña"
    Then the name is accepted
"""


def test_good_bdd_passes(tmp_path):
    _write(tmp_path, "output/test-cases/bdd/US-901-signup.feature", GOOD_FEATURE)
    _write(tmp_path, "output/test-cases/bdd/US-901-coverage.md", "AC1 AC2 AC3 AC4 AC5")
    res = ev.verify_case(CASES["bdd-signup-story"], tmp_path)
    assert res["score"] == 100, [(x["id"], x["detail"]) for x in res["checks"] if not x["ok"]]


def test_invalid_and_spanish_gherkin_fails(tmp_path):
    bad = "Característica: Registro\n  Escenario: algo\n    Dado que estoy\n    Entonces veo\n"
    _write(tmp_path, "output/test-cases/bdd/US-901-signup.feature", bad)
    res = ev.verify_case(CASES["bdd-signup-story"], tmp_path)
    assert {"gherkin", "keywords-english", "content-english", "outline-boundaries"} <= _failed(res)


def test_parse_gherkin_detects_structure_errors():
    g = ev.parse_gherkin("@US-1\nFeature: X\n  @TC-001\n  Scenario: no then\n    Given something\n"
                         "  @TC-001\n  Scenario Outline: no examples\n    When something\n    Then other\n")
    assert g["feature_tags"] == ["@US-1"] and len(g["scenarios"]) == 2
    assert any("has no Then" in x for x in g["errors"]) and any("Examples" in x for x in g["errors"])


# ------------------------------------------------------------------ API, bug, consultant and documenter
def test_api_good_and_bad(tmp_path):
    good = "\n".join(f"### TC-API-{i:03d}" for i in range(1, 9)) + """
POST /auth/login → 200, 400, 401 and 423 (lockout after 3 failed attempts).
POST /auth/forgot-password: same response for a nonexistent email (does not reveal whether it exists).
```json
{"email": "a@b.com"}
```
```json
{"error": "Invalid credentials"}
```
```json
{"token": "x"}
```
"""
    _write(tmp_path, "output/api-cases/api-cases-auth.md", good)
    assert ev.verify_case(CASES["api-cases-auth"], tmp_path)["score"] == 100
    _write(tmp_path, "output/api-cases/api-cases-auth.md", "TC-API-001 POST /auth/login 200\n| a | b |\n|---|---|\n")
    assert {"ids", "codes", "json", "tables"} <= _failed(ev.verify_case(CASES["api-cases-auth"], tmp_path))


GOOD_BUG = """**ID:** `BUG-001`
**Title:** [Cart] The SAVE10 coupon is applied more than once
**Story:** No story
**Status:** `Open`
**Description:** Clicking Apply several times stacks the discount.
**Preconditions:** A $100.00 product in the cart.
**Test Data:**
- User: ana.qa@test.com
- Password: (not provided in the observation)
**Steps to Reproduce:**
1. Apply SAVE10. 2. Click Apply again.
**Actual Result:** The total ends up at $70.00 (30% discount).
**Expected Result:** The coupon is applied only once (10%).
**Evidence:** None attached.
**Criticality / Severity:** `High`
**Priority:** `High`
**Associated Test Case:** —
**Version:** —
**Browser:** Chrome (version not reported)
**Environment:** staging

## ⚠️ Missing information
- App and browser version, evidence and password.
"""


def test_good_bug_report_and_one_that_invents(tmp_path):
    _write(tmp_path, "output/bug-reports/BUG-001.md", GOOD_BUG)
    res = ev.verify_case(CASES["bug-report-coupon"], tmp_path)
    assert res["score"] == 100, [(x["id"], x["detail"]) for x in res["checks"] if not x["ok"]]
    invented = (GOOD_BUG.replace("Password: (not provided in the observation)", "Password: Qa12345!")
                .replace("Chrome (version not reported)", "Chrome 128.0").replace("## ⚠️ Missing information", "## Notes"))
    _write(tmp_path, "output/bug-reports/BUG-001.md", invented)
    assert {"no-invented-password", "no-invented-version", "missing"} <= _failed(ev.verify_case(CASES["bug-report-coupon"], tmp_path))


def test_consultant_on_chat_response(tmp_path):
    _write(tmp_path, "_eval/response.txt",
           "1) The username has between 4 and 20 characters (src/signup/validations.ts:12).\n"
           "2) Only one coupon is allowed per purchase (PROJ-40).\n"
           "3) The locked user case is not documented in input/documentation/.")
    assert ev.verify_case(CASES["project-consultant-questions"], tmp_path)["score"] == 100
    _write(tmp_path, "_eval/response.txt", "A locked user cannot pay and sees an error.")
    assert {"username", "cites-source", "undocumented"} <= _failed(ev.verify_case(CASES["project-consultant-questions"], tmp_path))


def test_documenter_detects_copied_secrets(tmp_path):
    rules = ("---\ntitle: Business rules\ntype: project\nsources: github demo/store\nupdated: 2026-10-14\n---\n"
             "# Rules\nObserved in the code (works today, not a requirement):\n- Username between 4 and 20 characters (`src/signup/validations.ts:13`).\n"
             "- Name between 2 and 50.\n- Minimum age 18.\n- Only one coupon per purchase (`src/payments/coupons.ts:3`).\n")
    messages = ("---\ntitle: Messages\ntype: project\nupdated: 2026-10-14\n---\n- \"Username must be between 4 and 20 characters\" (en.json)\n"
                "- \"You already applied a coupon to this purchase\" (en.json)\n")
    _write(tmp_path, "input/documentation/INDEX.md", "# Index")
    _write(tmp_path, "input/documentation/project/business-rules.md", rules)
    _write(tmp_path, "input/documentation/project/messages.md", messages)
    assert ev.verify_case(CASES["project-documenter-local-repo"], tmp_path)["score"] == 100
    _write(tmp_path, "input/documentation/project/repository.md", "PAYMENTS_API_KEY=FAKE_PASSWORD_EVAL_DO_NOT_COPY_7Q2X")
    res = ev.verify_case(CASES["project-documenter-local-repo"], tmp_path)
    assert "no-secrets" in _failed(res) and res["status"] == "Failed"


# ------------------------------------------------------------------ results, comparison and report
def test_comparison_with_previous_run_and_report(tmp_path):
    def run(name, ok):
        data = {"date": name, "cases": [{"id": "c1", "agent": "story-analyst", "description": "", "score": 100 if ok else 50,
                                         "status": "Passed" if ok else "Failed", "metrics": {"cost_usd": 0.42, "turns": 9, "duration_s": 80},
                                         "checks": [{"id": "a", "description": "A", "ok": True, "detail": "", "weight": 1},
                                                    {"id": "b", "description": "B", "ok": ok, "detail": "", "weight": 1}]},
                                        {"id": "c2", "agent": "project-consultant", "description": "", "score": 0, "status": "N/A",
                                         "checks": [], "reason": "Skipped"}]}
        return ev.save(data, tmp_path / name)

    run("20261001-100000", True)
    dest = run("20261014-100000", False)
    data = json.loads((dest / "results.json").read_text(encoding="utf-8"))
    assert data["comparison"]["regressions"] == 1 and data["comparison"]["cases"]["c1"]["regressions"] == ["b"]
    assert data["by_agent"] == {"story-analyst": {"cases": 1, "passed": 0, "score": 50}}
    html = (dest / "evals-report.html").read_text(encoding="utf-8")
    assert "Agent evals" in html and "Comparison with the previous run" in html and "Skipped" in html


def test_verify_only_via_command_line(tmp_path, capsys):
    _write(tmp_path, "output/story-analysis/analysis-US-901.md", GOOD_ANALYSIS)
    code = ev.main(["--verify-only", str(tmp_path), "--case", "story-analyst-signup-story", "--results", str(tmp_path / "res")])
    assert code == 0
    out = capsys.readouterr().out
    assert "Passed" in out and list((tmp_path / "res").glob("*/evals-report.html"))


@pytest.mark.parametrize("case", sorted(CASES))
def test_each_case_fails_without_outputs(case, tmp_path):
    # An empty workspace can never pass: the checks are not met "by default".
    assert ev.verify_case(CASES[case], tmp_path)["status"] == "Failed"
