"""Reading of cases (.feature and .xlsx) and conversion for Azure Test Plans."""
from pathlib import Path

import readers
import to_azure_devops

ROOT = Path(__file__).resolve().parents[1]

FEATURE = """@US-001
Feature: Login
  Background:
    Given I am on the login page

  @TC-001 @smoke
  Scenario: Valid login
    When I enter credentials
    Then I get in

  @TC-002
  Scenario Outline: Invalid data
    When I enter "<email>"
    Then I see "<msg>"

    @negative
    Examples: Format
      | email | msg     |
      | x     | invalid |

    @edge
    Examples: Empty
      | email | msg      |
      |       | required |

  Rule: Lockout
    Background:
      Given I failed 2 times

    @TC-003
    Example: Third attempt
      When I fail again
      Then the account gets locked
"""


def test_read_full_feature(tmp_path):
    file = tmp_path / "US-001.feature"
    file.write_text(FEATURE, encoding="utf-8")
    cases = {c["id"]: c for c in readers.read_feature(file)}
    assert list(cases) == ["TC-001", "TC-002", "TC-003"]
    assert cases["TC-001"]["priority"] == "High"  # @smoke, lowercase
    assert "US-001" in cases["TC-001"]["tags"]
    # An explicit priority tag wins over @smoke
    assert readers.priority_from_tags(["smoke", "critical"]) == "Critical"
    assert readers.priority_from_tags(["high"]) == "High"
    assert readers.priority_from_tags(["US-001"]) == "Medium"  # no tag and no smoke
    # The two Examples with tags stay inside the Scenario Outline
    assert cases["TC-002"]["gherkin"].count("Examples:") == 2
    # The scenario inside the Rule inherits the feature's Background and the rule's
    assert cases["TC-003"]["gherkin"].count("Given I") == 2


def test_read_template_xlsx():
    cases = readers.read_cases(ROOT / "templates" / "test-cases-template.xlsx")
    assert cases and all(c["id"].startswith("TC-") for c in cases)
    assert all(c["steps"] for c in cases)


def test_azure_devops_conversion(tmp_path):
    file = tmp_path / "US-001.feature"
    file.write_text(FEATURE, encoding="utf-8")
    converted = [to_azure_devops.convert(c) for c in readers.read_feature(file)]
    login = converted[0]
    assert login["title"].startswith("TC-001 - ")
    assert login["priority"] == 2
    # Every step has an expected result: "-" if it has none (otherwise the server would make one up)
    for line in login["steps"].splitlines():
        assert "|" in line and line.split("|", 1)[1].strip()
    assert "Then I get in" in login["steps"]


def test_newman_respects_collection_base_url(tmp_path):
    import run_newman
    collection = ROOT / "input" / "api" / "demo.postman_collection.json"
    environment = ROOT / "input" / "api" / "demo.postman_environment.json"
    assert "jsonplaceholder" in run_newman.own_base_url(collection, str(environment))
    empty = tmp_path / "c.json"
    empty.write_text('{"info": {"name": "x"}, "item": []}', encoding="utf-8")
    assert run_newman.own_base_url(empty, None) is None  # then API_BASEURL from the .env is used
