"""Report of the wallets and payments tester (wallet-tester agent)."""
import json

import pytest

import generate_wallets_report as gi

ANALYSIS = {
    "title": "Wallet — US-010", "story": "US-010", "environment": "sandbox", "generated": "2026-10-19T11:00:00",
    "payment_provider": "Mercado Pago (sandbox)", "verdict": "1 high finding", "verdict_tone": "warn",
    "summary": "I tested P2P, idempotency and concurrency.",
    "tests": [{"id": "TC-API-003", "category": "Idempotency", "case": "Retry same key", "result": "Passed",
               "expected": "one movement", "actual": "one movement"},
              {"id": "TC-API-004", "category": "Concurrency", "case": "Two parallel withdrawals", "result": "Failed",
               "expected": "one succeeds", "actual": "negative balance"}],
    "conservation": [{"scenario": "P2P A→B 500", "before": 10000, "after": 10000, "balances": True, "detail": "total"},
                     {"scenario": "Double withdrawal", "before": 500, "after": -100, "balances": False, "detail": "went negative"}],
    "findings": [{"id": "H-01", "severity": "High", "category": "Concurrency", "text": "Double spending",
                  "impact": "negative balance", "how_to_reproduce": "2 POST /withdrawal at the same time", "recommendation": "lock per account"}],
    "reconciliation": {"wallet_movements": 42, "provider_movements": 42, "differences": 0,
                       "detail": [{"concept": "Fees", "wallet": 120.5, "provider": 120.5, "difference": 0}]},
    "recommendations": [{"priority": "High", "action": "Serialize per account", "reason": "prevents double spending"}],
    "missing_info": [{"id": "MI-01", "what_is_missing": "daily limit", "question": "daily withdrawal cap?"}],
}


def _gen(tmp_path, data, monkeypatch):
    monkeypatch.setenv("K0LMENIA_PORTAL", "0")
    (tmp_path / "analysis.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    gi.generate(tmp_path / "analysis.json", tmp_path / "report.html")
    return (tmp_path / "report.html").read_text(encoding="utf-8")


def test_full_report(tmp_path, monkeypatch):
    html = _gen(tmp_path, ANALYSIS, monkeypatch)
    assert "Wallet — US-010" in html
    assert "Double spending" in html and "TC-API-004" in html and "MI-01" in html
    assert "Balance conservation" in html and "Reconciliation with the payment provider" in html
    assert "2 POST /withdrawal at the same time" in html  # the "How to reproduce" section
    assert "Test environment" in html  # the sandbox banner


def test_without_tests_or_findings(tmp_path, monkeypatch):
    html = _gen(tmp_path, {"title": "Empty"}, monkeypatch)
    assert "No findings." in html and "Empty" in html


def test_invalid_json_fails(tmp_path):
    (tmp_path / "x.json").write_text("{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        gi.generate(tmp_path / "x.json", tmp_path / "i.html")
