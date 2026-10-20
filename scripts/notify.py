#!/usr/bin/env python3
"""
Notifications to Slack and Microsoft Teams through an incoming webhook (npm test results, monitoring, closure, failures…).

Usage (from the repo root):
    python scripts/notify.py --title "Sprint 5 regression" --text "48 of 50 passed"
                             [--level ok|warning|error] [--link URL] [--fields "Suite=web,Environment=staging"]
                             [--channel slack|teams|all] [--test] [--strict]
    python scripts/notify.py --from-cucumber tools/k0lmena/reports/web/cucumber-report.json [--link URL]

Configuration in the root .env (or in the environment, which takes precedence):
    SLACK_WEBHOOK_URL   Incoming Webhook of a Slack app (https://hooks.slack.com/services/...).
                        A Block Kit message is sent.
    TEAMS_WEBHOOK_URL   Webhook of a Teams Workflows (Power Automate) flow: template "Post to a
                        channel when a webhook request is received". An Adaptive Card (1.4) is sent,
                        wrapped in a "message" with "attachments". The Office 365 connector
                        "Incoming Webhooks" are retired: they are not used.

--channel all (the default) sends to whichever are configured. With no webhook configured it warns and
exits with 0 without sending anything (with --strict, it exits with 2). --test shows the JSON that would be
sent, without sending it. The webhook URL is never shown: it is a secret (whoever has it can post to the channel).

--from-cucumber summarizes a Cucumber JSON report (npm test): passed, failed and the first
scenarios that failed, with their @US/@TC. --title, --text and --level, if given, override the summary.

Exit codes: 0 sent (or nothing to send), 1 sending failed, 2 missing configuration with --strict
or invalid arguments.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402

LEVELS = {
    "ok": {"emoji": ":white_check_mark:", "teams": "Good", "label": "OK"},
    "warning": {"emoji": ":warning:", "teams": "Warning", "label": "Warning"},
    "error": {"emoji": ":rotating_light:", "teams": "Attention", "label": "Error"},
}
VARIABLES = {"slack": "SLACK_WEBHOOK_URL", "teams": "TEAMS_WEBHOOK_URL"}


def parse_fields(text):
    """'Suite=web,Environment=staging' -> [('Suite', 'web'), ('Environment', 'staging')]."""
    fields = []
    for part in (text or "").split(","):
        if not part.strip():
            continue
        if "=" not in part:
            raise ValueError(f'field without "=": "{part.strip()}" (format Key=Value,Key=Value)')
        key, value = part.split("=", 1)
        fields.append((key.strip(), value.strip()))
    return fields


def payload_slack(title, text, level="ok", link=None, fields=()):
    n = LEVELS[level]
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"{title}"[:150], "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"{n['emoji']} {text}"[:3000]}},
    ]
    if fields:
        blocks.append({"type": "section", "fields": [{"type": "mrkdwn", "text": f"*{k}*\n{v}"[:2000]} for k, v in list(fields)[:10]]})
    if link:
        blocks.append({"type": "actions", "elements": [{"type": "button", "text": {"type": "plain_text", "text": "View details"}, "url": link}]})
    return {"text": f"[{n['label']}] {title}: {text}"[:3000], "blocks": blocks}


def payload_teams(title, text, level="ok", link=None, fields=()):
    n = LEVELS[level]
    body = [
        {"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium", "color": n["teams"], "wrap": True},
        {"type": "TextBlock", "text": text, "wrap": True},
    ]
    if fields:
        body.append({"type": "FactSet", "facts": [{"title": k, "value": v} for k, v in fields]})
    card = {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard", "version": "1.4", "body": body}
    if link:
        card["actions"] = [{"type": "Action.OpenUrl", "title": "View details", "url": link}]
    return {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None, "content": card}]}


def cucumber_summary(report):
    """Summary of a Cucumber JSON report: {total, passed, failed, others, failed_detail}."""
    total = passed = failed = 0
    detail = []
    for feature in report or []:
        for sc in feature.get("elements") or []:
            if sc.get("type") == "background":
                continue
            total += 1
            statuses = [((p.get("result") or {}).get("status") or "undefined") for p in sc.get("steps") or []]
            if "failed" in statuses:
                failed += 1
                tags = [t.get("name", "") for t in sc.get("tags") or []]
                ids = " ".join(t for t in tags if t.startswith(("@US-", "@TC-")))
                detail.append(f"{ids} {sc.get('name', '')}".strip())
            elif statuses and all(s == "passed" for s in statuses):
                passed += 1
    return {"total": total, "passed": passed, "failed": failed, "others": total - passed - failed, "failed_detail": detail}


def notification_from_cucumber(report, name="npm test"):
    r = cucumber_summary(report)
    if not r["total"]:
        return f"{name}: no scenarios", "The report has no scenarios.", "warning", []
    level = "error" if r["failed"] else ("warning" if r["others"] else "ok")
    text = f"{r['passed']} of {r['total']} scenario(s) passed"
    if r["failed"]:
        text += f" · {r['failed']} failed: " + "; ".join(r["failed_detail"][:5])
        if len(r["failed_detail"]) > 5:
            text += f" and {len(r['failed_detail']) - 5} more"
    fields = [("Passed", str(r["passed"])), ("Failed", str(r["failed"]))]
    if r["others"]:
        fields.append(("Incomplete", str(r["others"])))
    return f"{name}: {'failed' if r['failed'] else 'OK'}", text, level, fields


def send(url, payload, timeout=15):
    """POST the JSON. Returns (ok, detail) without ever including the URL."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 300, f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:200]
        return False, f"HTTP {e.code} {body}".strip()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        return False, f"no response ({type(reason).__name__})"


def main(argv=None, environment=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Notifications to Slack and Teams through a webhook")
    ap.add_argument("--title")
    ap.add_argument("--text")
    ap.add_argument("--level", choices=list(LEVELS))
    ap.add_argument("--link")
    ap.add_argument("--fields", default="")
    ap.add_argument("--channel", choices=["slack", "teams", "all"], default="all")
    ap.add_argument("--from-cucumber", help="Cucumber JSON report (npm test) to summarize")
    ap.add_argument("--name", default="npm test", help="name of the run in the --from-cucumber notification")
    ap.add_argument("--test", action="store_true", help="shows the JSON without sending it")
    ap.add_argument("--strict", action="store_true", help="exits with 2 if no webhook is configured")
    a = ap.parse_args(argv)

    try:
        fields = parse_fields(a.fields)
    except ValueError as e:
        print(f"notify: {e}", file=sys.stderr)
        return 2
    title, text, level = a.title, a.text, a.level or "ok"
    if a.from_cucumber:
        try:
            report = json.loads(Path(a.from_cucumber).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"notify: could not read the Cucumber report ({e})", file=sys.stderr)
            return 2
        t, x, n, c = notification_from_cucumber(report, a.name)
        title, text, level, fields = a.title or t, a.text or x, a.level or n, c + fields
    if not title or not text:
        print("notify: --title and --text are missing (or --from-cucumber)", file=sys.stderr)
        return 2

    if environment is None:
        _env.load_env()
        import os
        environment = os.environ
    channels = ["slack", "teams"] if a.channel == "all" else [a.channel]
    targets = [(c, (environment.get(VARIABLES[c]) or "").strip()) for c in channels]
    builders = {"slack": payload_slack, "teams": payload_teams}

    if a.test:
        for c, _ in targets:
            print(f"--- {c} ---")
            print(json.dumps(builders[c](title, text, level, a.link, fields), ensure_ascii=False, indent=2))
        return 0

    configured = [(c, u) for c, u in targets if u]
    for c, u in targets:
        if not u:
            print(f"notify: {c} is not configured ({VARIABLES[c]} in the .env); not sending.")
    if not configured:
        return 2 if a.strict else 0
    error = False
    for c, url in configured:
        if not url.startswith("https://"):
            print(f"notify: {VARIABLES[c]} must start with https://; not sending to {c}.", file=sys.stderr)
            error = True
            continue
        ok, detail = send(url, builders[c](title, text, level, a.link, fields))
        print(f"notify: {c} {'OK' if ok else 'failed'} ({detail})")
        error |= not ok
    return 1 if error else 0


if __name__ == "__main__":
    sys.exit(main())
