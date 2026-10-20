"""Messaging/event tester: pure checks of the tool and HTML report."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tools" / "messaging"))

import generate_messaging_report as gi  # noqa: E402
import messaging  # noqa: E402


def test_verify_order():
    ok, _ = messaging.verify_order(["a", "b", "c"], ["x", "a", "y", "b", "z", "c"])
    assert ok is True
    ok2, _ = messaging.verify_order(["a", "b"], ["b", "a"])  # b arrives before a
    assert ok2 is False


def test_detect_duplicates():
    assert messaging.detect_duplicates([{"id": 1}, {"id": 1}, {"id": 2}], key="id") == [1]
    assert messaging.detect_duplicates([{"id": 1}, {"id": 2}], key="id") == []


def test_validate_schema():
    assert messaging.validate_schema({"id": 1}, ["id", "name"]) == ["name"]
    assert messaging.validate_schema({"id": 1, "name": "x"}, ["id", "name"]) == []
    assert messaging.validate_schema("not a dict", ["id"]) == ["id"]


def test_report(tmp_path, monkeypatch):
    monkeypatch.setenv("K0LMENIA_PORTAL", "0")
    data = {"title": "Events — US-010", "system": {"broker": "Kafka", "destination": "orders", "schema": "Avro"},
            "verdict": "It is not idempotent", "verdict_tone": "bad",
            "tests": [{"id": "TC-001", "category": "Idempotency", "case": "Resend event", "result": "Failed",
                       "expected": "one effect", "actual": "two effects"}],
            "findings": [{"id": "F-01", "severity": "High", "category": "Idempotency", "text": "Double processing",
                          "impact": "double charge", "how_to_reproduce": "publish the same event twice", "recommendation": "dedup by id"}],
            "missing_info": [{"id": "MI-01", "what_is_missing": "dedup key", "question": "which id does it deduplicate by?"}]}
    (tmp_path / "a.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    gi.generate(tmp_path / "a.json", tmp_path / "i.html")
    html = (tmp_path / "i.html").read_text(encoding="utf-8")
    assert "Events — US-010" in html and "Kafka" in html and "Double processing" in html and "MI-01" in html
    assert "publish the same event twice" in html


def test_invalid_json_fails(tmp_path):
    (tmp_path / "x.json").write_text("{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        gi.generate(tmp_path / "x.json", tmp_path / "i.html")
