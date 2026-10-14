"""Informe de monitoreo sintético (scripts/generar_informe_monitoreo.py)."""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

import generar_informe_monitoreo as inf  # noqa: E402


def _corrida(fecha, estado_login, ms=400):
    res = [{"id": "GET a.com/", "nombre": "Home", "tipo": "URL", "url": "https://a.com/", "status": 200, "ms": ms, "estado": "OK", "motivo": ""},
           {"id": "GET a.com/login", "nombre": "/login", "tipo": "URL", "url": "https://a.com/login", "status": 502 if estado_login == "Caído" else 200,
            "ms": 90, "estado": estado_login, "motivo": "HTTP 502" if estado_login == "Caído" else ""},
           {"id": "TLS a.com", "nombre": "Certificado de a.com", "tipo": "TLS", "url": "https://a.com", "vence": "2026-11-01T00:00:00Z",
            "dias_restantes": 10, "estado": "Por vencer", "motivo": "Vence en 10 día(s)"}]
    return {"nombre": "prod", "fecha": fecha, "estado": "Caído" if estado_login == "Caído" else "Degradado", "resultados": res,
            "cambios": {"anterior": None, "rompio": [], "recupero": []}}


def test_informe_con_historial(tmp_path):
    for i, est in enumerate(["OK", "Caído"]):
        d = tmp_path / "historial" / f"2026-10-1{i}T10-00-00"
        d.mkdir(parents=True)
        (d / "monitoreo.json").write_text(json.dumps(_corrida(f"2026-10-1{i}T10:00:00", est)), encoding="utf-8")
        (d / "informe-monitoreo.html").write_text("x", encoding="utf-8")
    actual = _corrida("2026-10-14T10:00:00", "OK")
    actual["cambios"] = {"anterior": "Caído", "rompio": [], "recupero": ["GET a.com/login"]}
    lista = inf.corridas(tmp_path, actual)
    assert len(lista) == 3 and lista[-1][0] == "actual"
    assert inf.disponibilidad(lista) == 66.7
    assert inf.disponibilidad(lista, "GET a.com/login") == 66.7
    assert inf.disponibilidad(lista, "GET a.com/") == 100.0
    html = inf.build_html(actual, lista)
    assert "se recuperó: GET a.com/login" in html and "(antes: Caído)" in html
    assert "Disponibilidad por check" in html and "historial/2026-10-10T10-00-00/informe-monitoreo.html" in html
    assert "Vence en 10 día(s)" in html


def test_informe_primera_corrida(tmp_path):
    datos = _corrida("2026-10-14T10:00:00", "Caído")
    html = inf.build_html(datos, inf.corridas(tmp_path, datos))
    assert "Hay checks que fallan" in html and "primera corrida" in html
    assert "Disponibilidad por check" not in html  # con una sola corrida no hay evolución
