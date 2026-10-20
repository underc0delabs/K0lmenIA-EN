#!/usr/bin/env python3
"""Converts k0lmenIA cases (manual .xlsx or BDD .feature) to the format required by the
`testplan_test_case_write` tool of the azure-devops MCP connector (see CONNECTORS.md).

Usage:
    python scripts/management/to_azure_devops.py <cases.xlsx|.feature> [--ids TC-001,TC-003]

Prints a JSON with one element per case: id (TC-XXX), title, priority (1 to 4, the Azure
DevOps scale), steps ("1. action|expected result" per line) and tags (includes the
MI-XX of missing information). This way the test-manager agent does not build the steps by hand.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ManagementError  # noqa: E402
from readers import read_cases  # noqa: E402

PRIORITY_ADO = {"Critical": 1, "High": 2, "Medium": 3, "Low": 4}


def _clean(text):
    """A single line and without '|', which the server uses as the action/result separator."""
    return re.sub(r"\s+", " ", str(text or "").replace("|", "/")).strip()


def _manual_steps(case):
    steps = []
    for p in case["steps"]:
        action = _clean(p["action"])
        if p.get("data"):
            action += f" (data: {_clean(p['data'])})"
        steps.append((action, _clean(p.get("result"))))
    if case.get("preconditions"):
        steps.insert(0, (f"Preconditions: {_clean(case['preconditions'])}", ""))
    return steps


def _gherkin_steps(case):
    """Given/When/And are actions; each Then (and its And/But) is the expected result of the
    last action step. The keyword of each line is kept."""
    steps, in_then = [], False
    for line in case["gherkin"].splitlines():
        l = line.strip()
        m = re.match(r"^(Given|When|Then|And|But|\*)\s+(.*)$", l)
        if not m:
            continue
        word, text = m.group(1), _clean(l)
        if word == "Then" or (in_then and word in ("And", "But")):
            in_then = True
            if not steps:
                steps.append(("(no previous steps)", ""))
            action, result = steps[-1]
            steps[-1] = (action, f"{result}; {text}" if result else text)
        else:
            in_then = False
            steps.append((text, ""))
    return steps


def convert(case):
    steps = _gherkin_steps(case) if case["type"] == "cucumber" else _manual_steps(case)
    # A step without an expected result gets "-": if it is left empty, the server fills in a
    # generic one ("Verify step completes successfully") that does not come from the case.
    lines = [f"{i}. {action}|{result or '-'}" for i, (action, result) in enumerate(steps, 1)]
    title = case["title"] if case["id"] == case["title"] else f"{case['id']} - {case['title']}"
    return {
        "id": case["id"],
        "title": title,
        "priority": PRIORITY_ADO.get(case["priority"], 3),
        "steps": "\n".join(lines),
        "tags": case["tags"] + ([f"estimated-time-{case['estimate']['minutes']:g}min"] if case.get("estimate") else []),
        "estimated_time_min": case["estimate"]["minutes"] if case.get("estimate") else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help=".xlsx spreadsheet of manual cases or .feature file")
    parser.add_argument("--ids", help="Only these cases, comma-separated (e.g. TC-001,TC-003)")
    args = parser.parse_args()
    ids = [i.strip() for i in args.ids.split(",") if i.strip()] if args.ids else None
    try:
        cases = read_cases(args.source, ids)
    except ManagementError as e:
        sys.exit(f"[!] {e}")
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps([convert(c) for c in cases], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
