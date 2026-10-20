"""permissions-tester report: comparison against what is expected and HTML report."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_permissions_report as gp  # noqa: E402

DATA = {
    "url": "https://a.com/", "host": "a.com", "date": "2026-10-14T10:00:00Z", "stamp": "20261014-100000",
    "roles": [{"id": "anonymous", "name": "Anonymous", "authenticated": False},
              {"id": "admin", "name": "admin", "authenticated": True, "login_ok": True},
              {"id": "operator", "name": "operator", "authenticated": True, "login_ok": True}],
    "paths": [{"url": "https://a.com/admin", "path": "/admin", "discovered_by": ["admin"]},
              {"url": "https://a.com/reports/month", "path": "/reports/month", "discovered_by": ["admin", "operator"]}],
    "matrix": [
        {"role": "anonymous", "url": "https://a.com/admin", "access": "requires-login", "status": 200},
        {"role": "admin", "url": "https://a.com/admin", "access": "allowed", "status": 200, "menus": ["Users"], "buttons": ["New"]},
        {"role": "operator", "url": "https://a.com/admin", "access": "allowed", "status": 200},
        {"role": "anonymous", "url": "https://a.com/reports/month", "access": "requires-login", "status": 200},
        {"role": "admin", "url": "https://a.com/reports/month", "access": "allowed", "status": 200},
        {"role": "operator", "url": "https://a.com/reports/month", "access": "denied", "status": 403},
    ],
    "endpoints": [{"method": "GET", "path": "/api/x", "url": "https://a.com/api/x", "results": {"anonymous": {"status": 401}, "admin": {"status": 200, "with_token": True}}}],
    "findings": [{"id": "P-01", "severity": "Medium", "type": "Option without permission", "title": "t", "detail": "d", "role": "operator", "url": "https://a.com/reports/month"}],
    "summary": {"roles": 3, "paths": 2, "visits": 6, "allowed": 3, "denied": 1, "require_login": 2, "findings": 1, "by_severity": {"Critical": 0, "High": 0, "Medium": 1, "Low": 0}},
}
EXPECTED = {"operator": {"/admin": "denied", "/reports*": "allowed"}, "admin": {"/admin": "allowed"}}


def test_expected_by_exact_path_and_prefix():
    assert gp.expected_for(EXPECTED, "operator", "https://a.com/admin/") == "denied"
    assert gp.expected_for(EXPECTED, "operator", "https://a.com/reports/month") == "allowed"
    assert gp.expected_for(EXPECTED, "operator", "https://a.com/other") is None
    assert gp.expected_for(EXPECTED, "anonymous", "https://a.com/admin") is None


def test_differences_against_expected():
    d = gp.differences(DATA, EXPECTED)
    assert [(x["id"], x["severity"], x["role"], gp.path_of(x["url"])) for x in d] == [
        ("E-01", "Critical", "operator", "/admin"), ("E-02", "High", "operator", "/reports/month")]


def test_report_with_matrix_differences_and_missing_info():
    html = gp.build_html(DATA, {"expected": EXPECTED, "discarded": [{"id": "P-01", "reason": "it is expected"}]})
    assert "Access matrix by role" in html and "Endpoints by role" in html and "What each role sees" in html
    assert "gets into something it should not" in html and "Discarded: it is expected" in html
    without = gp.build_html(DATA, {})
    assert "Missing information" in without and "permissions matrix by role" in without


def test_command_line_with_history(tmp_path):
    folder = tmp_path / "a.com"
    folder.mkdir()
    (folder / "permissions.json").write_text(json.dumps(DATA), encoding="utf-8")
    old = folder / "history" / "20261013-100000"
    old.mkdir(parents=True)
    (old / "permissions.json").write_text(json.dumps(dict(DATA, findings=[], stamp="20261013-100000")), encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_permissions_report.py"), str(folder / "permissions.json"), str(folder / "permissions-report.html")],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    html = (folder / "permissions-report.html").read_text(encoding="utf-8")
    assert "Run history" in html and "Saved runs" in html
