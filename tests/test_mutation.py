"""Mutation testing: Stryker report parser (pure helpers)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "mutation"))

import mutation  # noqa: E402

REPORT = {
    "schemaVersion": "1.0",
    "files": {
        "src/price.js": {"mutants": [
            {"id": "1", "mutatorName": "ArithmeticOperator", "status": "Killed", "location": {"start": {"line": 10}}},
            {"id": "2", "mutatorName": "EqualityOperator", "status": "Survived", "location": {"start": {"line": 12}}},
            {"id": "3", "mutatorName": "BooleanLiteral", "status": "Killed", "location": {"start": {"line": 14}}},
        ]},
        "src/util.js": {"mutants": [
            {"id": "4", "mutatorName": "ConditionalExpression", "status": "NoCoverage", "location": {"start": {"line": 3}}},
            {"id": "5", "mutatorName": "StringLiteral", "status": "Killed", "location": {"start": {"line": 5}}},
        ]},
    },
}


def test_parse_stryker_score_and_survivors():
    r = mutation.parse_stryker(REPORT)
    assert r["total"] == 5
    assert r["by_status"] == {"Killed": 3, "Survived": 1, "NoCoverage": 1}
    # global score = detected(3 killed) / valid(5) * 100 = 60.0
    assert r["score"] == 60.0
    # survivors: the Survived and the NoCoverage
    assert len(r["survived"]) == 2
    files = {s["file"] for s in r["survived"]}
    assert files == {"src/price.js", "src/util.js"}
    # score per file: price.js 2/3 killed = 66.7 ; util.js 1/2 = 50.0
    assert r["by_file"]["src/price.js"]["score"] == 66.7
    assert r["by_file"]["src/util.js"]["score"] == 50.0


def test_below_threshold():
    r = mutation.parse_stryker(REPORT)
    assert mutation.below_threshold(r["by_file"], 70) == ["src/util.js", "src/price.js"]
    assert mutation.below_threshold(r["by_file"], 55) == ["src/util.js"]


def test_empty_report():
    r = mutation.parse_stryker({"files": {}})
    assert r["score"] is None and r["total"] == 0 and r["survived"] == []
