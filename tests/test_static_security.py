"""Static security: SCA (dependencies) and SAST/secrets (sast) tools and their reports."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tools" / "security"))

import dependencies  # noqa: E402
import generate_dependencies_report as gid  # noqa: E402
import generate_sast_report as gis  # noqa: E402
import sast  # noqa: E402


# ---------------- SCA ----------------
def test_parse_npm_audit_and_count():
    data = {"vulnerabilities": {
        "lodash": {"severity": "high", "range": "<4.17.21", "fixAvailable": True},
        "minimist": {"severity": "critical", "range": "<1.2.6", "fixAvailable": {"name": "minimist"}}},
        "metadata": {"vulnerabilities": {"high": 1, "critical": 1, "total": 2}}}
    vulns, meta = dependencies.parse_npm_audit(data)
    sev = {v["package"]: v["severity"] for v in vulns}
    assert sev == {"lodash": "High", "minimist": "Critical"}
    assert all(v["fix"] for v in vulns)  # a fixAvailable dict also counts as True
    assert dependencies.count(vulns)["Critical"] == 1 and dependencies.count(vulns)["High"] == 1
    assert meta.get("total") == 2


def test_parse_pip_audit():
    data = [{"name": "jinja2", "version": "2.11.0", "vulns": [{"id": "PYSEC-2021-1", "fix_versions": ["2.11.3"]}]}]
    v = dependencies.parse_pip_audit(data)
    assert v[0]["id"] == "PYSEC-2021-1" and v[0]["ecosystem"] == "Python" and v[0]["fix"] is True


# ---------------- SAST / secrets ----------------
def test_find_secrets_detects_and_redacts():
    text = 'const k = "AKIAIOSFODNN7EXAMPLE";\npassword = "supersecret123"\nnothing = "hello world text"'
    res = sast.find_secrets(text)
    kinds = {t for t, _, _ in res}
    assert "AWS access key" in kinds and "Credential in assignment" in kinds
    assert all("supersecret123" not in frag for _, _, frag in res)  # the value is redacted


def test_parse_semgrep():
    data = {"results": [{"check_id": "rule.sql", "path": "src/db.js", "start": {"line": 42},
                         "extra": {"severity": "ERROR", "message": "SQL injection"}}]}
    out = sast.parse_semgrep(data)
    assert out[0]["severity"] == "High" and out[0]["file"] == "src/db.js" and out[0]["line"] == 42


# ---------------- Reports ----------------
def _gen(mod, tmp_path, data, monkeypatch):
    monkeypatch.setenv("K0LMENIA_PORTAL", "0")
    (tmp_path / "analysis.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    mod.generate(tmp_path / "analysis.json", tmp_path / "report.html")
    return (tmp_path / "report.html").read_text(encoding="utf-8")


def test_dependencies_report(tmp_path, monkeypatch):
    data = {"title": "SCA — my-app", "project": {"path": "/x", "ecosystems": ["Node"]}, "scanners": ["npm audit"],
            "verdict": "2 critical with a fix", "verdict_tone": "bad",
            "vulnerabilities": [{"package": "lodash 4.17.4", "severity": "Critical", "id": "CVE-2021-23337",
                                 "ecosystem": "Node", "fix": True, "recommendation": "upgrade to 4.17.21"}],
            "missing_info": [{"id": "MI-01", "what_is_missing": "licenses", "question": "are they reviewed?"}]}
    html = _gen(gid, tmp_path, data, monkeypatch)
    assert "SCA — my-app" in html and "CVE-2021-23337" in html and "MI-01" in html


def test_sast_report(tmp_path, monkeypatch):
    data = {"title": "SAST — my-app", "project": {"path": "/x"}, "scanners": ["secrets (built-in)"],
            "verdict": "1 exposed secret", "verdict_tone": "bad",
            "secrets": [{"type": "AWS access key", "file": ".env", "line": 3, "severity": "High", "status": "confirmed"}],
            "findings": [{"id": "F-01", "severity": "High", "category": "SQL injection", "file": "db.js", "line": 42,
                          "text": "concatenated query", "recommendation": "parameterize"}]}
    html = _gen(gis, tmp_path, data, monkeypatch)
    assert "SAST — my-app" in html and "AWS access key" in html and "SQL injection" in html
    assert "rotate the exposed credentials" in html  # secrets banner


def test_invalid_json_fails(tmp_path):
    (tmp_path / "x.json").write_text("{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        gid.generate(tmp_path / "x.json", tmp_path / "i.html")
