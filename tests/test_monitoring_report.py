"""Synthetic monitoring report (scripts/generate_monitoring_report.py)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_monitoring_report as rep  # noqa: E402


def _run(date, login_state, ms=400):
    res = [{"id": "GET a.com/", "name": "Home", "type": "URL", "url": "https://a.com/", "status": 200, "ms": ms, "state": "OK", "reason": ""},
           {"id": "GET a.com/login", "name": "/login", "type": "URL", "url": "https://a.com/login", "status": 502 if login_state == "Down" else 200,
            "ms": 90, "state": login_state, "reason": "HTTP 502" if login_state == "Down" else ""},
           {"id": "TLS a.com", "name": "Certificate for a.com", "type": "TLS", "url": "https://a.com", "expires": "2026-11-01T00:00:00Z",
            "remaining_days": 10, "state": "Expiring", "reason": "Expires in 10 day(s)"}]
    return {"name": "prod", "date": date, "state": "Down" if login_state == "Down" else "Degraded", "results": res,
            "changes": {"previous": None, "broke": [], "recovered": []}}


def test_report_with_history(tmp_path):
    for i, st in enumerate(["OK", "Down"]):
        d = tmp_path / "history" / f"2026-10-1{i}T10-00-00"
        d.mkdir(parents=True)
        (d / "monitoring.json").write_text(json.dumps(_run(f"2026-10-1{i}T10:00:00", st)), encoding="utf-8")
        (d / "monitoring-report.html").write_text("x", encoding="utf-8")
    current = _run("2026-10-14T10:00:00", "OK")
    current["changes"] = {"previous": "Down", "broke": [], "recovered": ["GET a.com/login"]}
    items = rep.runs(tmp_path, current)
    assert len(items) == 3 and items[-1][0] == "current"
    assert rep.availability(items) == 66.7
    assert rep.availability(items, "GET a.com/login") == 66.7
    assert rep.availability(items, "GET a.com/") == 100.0
    html = rep.build_html(current, items)
    assert "recovered: GET a.com/login" in html and "(before: Down)" in html
    assert "Availability per check" in html and "history/2026-10-10T10-00-00/monitoring-report.html" in html
    assert "Expires in 10 day(s)" in html


def test_report_first_run(tmp_path):
    data = _run("2026-10-14T10:00:00", "Down")
    html = rep.build_html(data, rep.runs(tmp_path, data))
    assert "There are failing checks" in html and "first run" in html
    assert "Availability per check" not in html  # with a single run there is no evolution
