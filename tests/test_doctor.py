"""npm run doctor: chequeos del .env y de las integraciones, sin red ni Docker."""
import json

import doctor


def correr(tmp_path, monkeypatch, capsys, contenido, *args):
    env = tmp_path / ".env"
    env.write_text(contenido, encoding="utf-8")
    monkeypatch.setenv("K0LMENA_ENV_FILE", str(env))
    for k in ("APP_URL", "BASEURL", "REPO_PROVEEDOR", "SLACK_WEBHOOK_URL", "PERMISOS_ROLES", "MONITOREO_URLS"):
        monkeypatch.delenv(k, raising=False)
    codigo = doctor.main(["--json", "--rapido", *args])
    salida = json.loads(capsys.readouterr().out)
    return codigo, salida["resultados"]


def textos(resultados, estado):
    return [r["texto"] for r in resultados if r["estado"] == estado]


def test_env_valido_y_urls(tmp_path, monkeypatch, capsys):
    codigo, res = correr(tmp_path, monkeypatch, capsys, "APP_URL=https://app.test\nBASEURL=ftp://mal\n", "--seccion", "env")
    assert codigo == 1
    assert "APP_URL definida" in textos(res, "ok")
    assert any("BASEURL no es una URL válida" in t for t in textos(res, "falta"))
    assert all(r["seccion"] == "env" for r in res)


def test_url_en_un_solo_lugar(tmp_path, monkeypatch, capsys):
    _, res = correr(tmp_path, monkeypatch, capsys, "APP_URL=https://app.test\nBASEURL=https://otra.test\n", "--seccion", "env")
    assert any("BASEURL y APP_URL son distintas" in t for t in textos(res, "aviso"))
    _, res = correr(tmp_path, monkeypatch, capsys, "BASEURL=https://vieja.test\n", "--seccion", "env")
    assert any("nombre viejo" in t for t in textos(res, "aviso"))
    _, res = correr(tmp_path, monkeypatch, capsys, "APP_URL=https://app.test\n", "--seccion", "env")
    assert not any("BASEURL" in t for t in textos(res, "aviso") + textos(res, "falta"))


def test_integraciones_coherentes(tmp_path, monkeypatch, capsys):
    contenido = ("REPO_PROVEEDOR=bitbucket\nREPO_NOMBRE=ws/app\nATLASSIAN_MCP_AUTENTICACION=oauth\n"
                 "PERMISOS_ROLES=admin,Operador Senior\nPERMISOS_ADMIN_USUARIO=a\nPERMISOS_ADMIN_CLAVE=b\n"
                 "SLACK_WEBHOOK_URL=https://otra.cosa/x\nTEAMS_WEBHOOK_URL=https://prod.workflows/x\n"
                 "MONITOREO_URLS=https://app.test,no-es-url\n")
    codigo, res = correr(tmp_path, monkeypatch, capsys, contenido, "--seccion", "integraciones")
    faltas = " | ".join(textos(res, "falta"))
    assert codigo == 1
    assert "Bitbucket necesita ATLASSIAN_MCP_AUTENTICACION=token" in faltas
    assert "Rol Operador Senior: faltan PERMISOS_OPERADOR_SENIOR_USUARIO" in faltas
    assert "SLACK_WEBHOOK_URL no tiene el formato esperado" in faltas
    assert "MONITOREO_URLS tiene 1 URL(s) inválida(s)" in faltas
    assert "Avisos a Teams (Workflows)" in textos(res, "ok")
    # nunca se muestran valores
    assert "otra.cosa" not in json.dumps(res) and "prod.workflows" not in json.dumps(res)


def test_proveedor_invalido_y_db(tmp_path, monkeypatch, capsys):
    contenido = "APP_URL=https://a.b\nREPO_PROVEEDOR=svn\nDB_CONEXIONES=principal\nDB_PRINCIPAL_MOTOR=oracle\n"
    _, res = correr(tmp_path, monkeypatch, capsys, contenido, "--seccion", "env,integraciones")
    faltas = " | ".join(textos(res, "falta"))
    assert "REPO_PROVEEDOR=svn no es válido" in faltas and "Base principal: DB_PRINCIPAL_MOTOR inválido" in faltas


def test_seccion_desconocida(capsys):
    import pytest
    with pytest.raises(SystemExit):
        doctor.main(["--seccion", "nada"])
