"""Notifications to Slack and Teams (scripts/notify.py): payloads, Cucumber summary and configuration, no network."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import notify  # noqa: E402


def test_fields():
    assert notify.parse_fields("Suite=web, Environment = staging,Url=https://a.com/?x=1") == [
        ("Suite", "web"), ("Environment", "staging"), ("Url", "https://a.com/?x=1")]
    assert notify.parse_fields("") == []
    with pytest.raises(ValueError):
        notify.parse_fields("no-equals")


def test_slack_block_kit_payload():
    p = notify.payload_slack("Regression", "48 of 50 passed", "error", "https://ci/1", [("Suite", "web")])
    assert p["text"].startswith("[Error] Regression")
    types = [b["type"] for b in p["blocks"]]
    assert types == ["header", "section", "section", "actions"]
    assert p["blocks"][1]["text"]["text"].startswith(":rotating_light:")
    assert p["blocks"][2]["fields"][0]["text"] == "*Suite*\nweb"
    assert p["blocks"][3]["elements"][0]["url"] == "https://ci/1"
    no_extras = notify.payload_slack("T" * 300, "x", "ok")
    assert len(no_extras["blocks"]) == 2 and len(no_extras["blocks"][0]["text"]["text"]) == 150


def test_teams_adaptive_card_payload():
    p = notify.payload_teams("Monitoring", "/login went down", "warning", "https://x", [("URL", "/login")])
    assert p["type"] == "message"
    att = p["attachments"][0]
    assert att["contentType"] == "application/vnd.microsoft.card.adaptive"
    card = att["content"]
    assert card["type"] == "AdaptiveCard" and card["version"] == "1.4"
    assert card["body"][0]["color"] == "Warning"
    assert card["body"][2] == {"type": "FactSet", "facts": [{"title": "URL", "value": "/login"}]}
    assert card["actions"][0]["type"] == "Action.OpenUrl"
    assert "actions" not in notify.payload_teams("T", "x")["attachments"][0]["content"]


def _sc(name, statuses, tags=()):
    return {"type": "scenario", "name": name, "tags": [{"name": t} for t in tags],
            "steps": [{"result": {"status": s}} for s in statuses]}


def test_cucumber_summary():
    report = [{"elements": [
        {"type": "background", "steps": [{"result": {"status": "passed"}}]},
        _sc("Login ok", ["passed", "passed"], ["@US-001", "@TC-001", "@smoke"]),
        _sc("Invalid login", ["passed", "failed", "skipped"], ["@US-001", "@TC-002"]),
        _sc("Pending", ["undefined"]),
    ]}]
    r = notify.cucumber_summary(report)
    assert (r["total"], r["passed"], r["failed"], r["others"]) == (3, 1, 1, 1)
    assert r["failed_detail"] == ["@US-001 @TC-002 Invalid login"]
    title, text, level, fields = notify.notification_from_cucumber(report, "Regression")
    assert title == "Regression: failed" and level == "error"
    assert text.startswith("1 of 3 scenario(s) passed · 1 failed: @US-001 @TC-002")
    assert ("Incomplete", "1") in fields
    assert notify.notification_from_cucumber([])[2] == "warning"


def test_without_webhook_does_not_send_and_strict_exits_with_2(capsys):
    assert notify.main(["--title", "T", "--text", "x"], environment={}) == 0
    output = capsys.readouterr().out
    assert "SLACK_WEBHOOK_URL" in output and "TEAMS_WEBHOOK_URL" in output
    assert notify.main(["--title", "T", "--text", "x", "--strict"], environment={}) == 2
    assert notify.main(["--text", "x"], environment={}) == 2


def test_test_mode_shows_json_and_never_url(capsys, monkeypatch):
    secret = "https://hooks.slack.com/services/T000/B000/SECRET"
    calls = []
    monkeypatch.setattr(notify, "send", lambda url, payload, timeout=15: calls.append(payload) or (True, "HTTP 200"))
    assert notify.main(["--title", "T", "--text", "x", "--channel", "slack", "--test"], environment={"SLACK_WEBHOOK_URL": secret}) == 0
    output = capsys.readouterr().out
    assert '"blocks"' in output and secret not in output and not calls
    assert notify.main(["--title", "T", "--text", "x", "--fields", "A=1"], environment={"SLACK_WEBHOOK_URL": secret, "TEAMS_WEBHOOK_URL": "https://x.logic.azure.com/w"}) == 0
    assert len(calls) == 2 and calls[1]["type"] == "message"
    assert secret not in capsys.readouterr().out


def test_send_failure_and_url_without_https(monkeypatch, capsys):
    monkeypatch.setattr(notify, "send", lambda url, payload, timeout=15: (False, "HTTP 404 no_service"))
    assert notify.main(["--title", "T", "--text", "x", "--channel", "slack"], environment={"SLACK_WEBHOOK_URL": "https://hooks.slack.com/x"}) == 1
    assert notify.main(["--title", "T", "--text", "x", "--channel", "teams"], environment={"TEAMS_WEBHOOK_URL": "http://insecure"}) == 1


def test_from_cucumber_via_command_line(tmp_path, capsys):
    report = tmp_path / "cucumber-report.json"
    report.write_text(json.dumps([{"elements": [_sc("A", ["passed"])]}]), encoding="utf-8")
    assert notify.main(["--from-cucumber", str(report), "--channel", "teams", "--test"], environment={}) == 0
    assert "1 of 1 scenario(s) passed" in capsys.readouterr().out
