"""npm run doctor: .env and integration checks, without network or Docker."""
import json

import doctor


def run(tmp_path, monkeypatch, capsys, content, *args):
    env = tmp_path / ".env"
    env.write_text(content, encoding="utf-8")
    monkeypatch.setenv("K0LMENA_ENV_FILE", str(env))
    for k in ("APP_URL", "BASEURL", "REPO_PROVIDER", "SLACK_WEBHOOK_URL", "PERMISSIONS_ROLES", "MONITORING_URLS"):
        monkeypatch.delenv(k, raising=False)
    code = doctor.main(["--json", "--quick", *args])
    output = json.loads(capsys.readouterr().out)
    return code, output["results"]


def texts(results, status):
    return [r["text"] for r in results if r["status"] == status]


def test_valid_env_and_urls(tmp_path, monkeypatch, capsys):
    code, res = run(tmp_path, monkeypatch, capsys, "APP_URL=https://app.test\nBASEURL=ftp://bad\n", "--section", "env")
    assert code == 1
    assert "APP_URL defined" in texts(res, "ok")
    assert any("BASEURL is not a valid URL" in t for t in texts(res, "missing"))
    assert all(r["section"] == "env" for r in res)


def test_url_in_a_single_place(tmp_path, monkeypatch, capsys):
    _, res = run(tmp_path, monkeypatch, capsys, "APP_URL=https://app.test\nBASEURL=https://other.test\n", "--section", "env")
    assert any("BASEURL and APP_URL are different" in t for t in texts(res, "warning"))
    _, res = run(tmp_path, monkeypatch, capsys, "BASEURL=https://old.test\n", "--section", "env")
    assert any("old name" in t for t in texts(res, "warning"))
    _, res = run(tmp_path, monkeypatch, capsys, "APP_URL=https://app.test\n", "--section", "env")
    assert not any("BASEURL" in t for t in texts(res, "warning") + texts(res, "missing"))


def test_consistent_integrations(tmp_path, monkeypatch, capsys):
    content = ("REPO_PROVIDER=bitbucket\nREPO_NAME=ws/app\nATLASSIAN_MCP_AUTHENTICATION=oauth\n"
               "PERMISSIONS_ROLES=admin,Senior Operator\nPERMISSIONS_ADMIN_USER=a\nPERMISSIONS_ADMIN_PASSWORD=b\n"
               "SLACK_WEBHOOK_URL=https://other.thing/x\nTEAMS_WEBHOOK_URL=https://prod.workflows/x\n"
               "MONITORING_URLS=https://app.test,not-a-url\n")
    code, res = run(tmp_path, monkeypatch, capsys, content, "--section", "integrations")
    missing = " | ".join(texts(res, "missing"))
    assert code == 1
    assert "Bitbucket needs ATLASSIAN_MCP_AUTHENTICATION=token" in missing
    assert "Role Senior Operator: missing PERMISSIONS_SENIOR_OPERATOR_USER" in missing
    assert "SLACK_WEBHOOK_URL does not have the expected" in missing
    assert "MONITORING_URLS has 1 invalid URL(s)" in missing
    assert "Notifications to Teams (Workflows)" in texts(res, "ok")
    # values are never shown
    assert "other.thing" not in json.dumps(res) and "prod.workflows" not in json.dumps(res)


def test_invalid_provider_and_db(tmp_path, monkeypatch, capsys):
    content = "APP_URL=https://a.b\nREPO_PROVIDER=svn\nDB_CONNECTIONS=main\nDB_MAIN_ENGINE=oracle\n"
    _, res = run(tmp_path, monkeypatch, capsys, content, "--section", "env,integrations")
    missing = " | ".join(texts(res, "missing"))
    assert "REPO_PROVIDER=svn is not valid" in missing and "Database main: DB_MAIN_ENGINE invalid" in missing


def test_unknown_section(capsys):
    import pytest
    with pytest.raises(SystemExit):
        doctor.main(["--section", "nothing"])
