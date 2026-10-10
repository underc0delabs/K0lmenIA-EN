"""Los generadores de reportes HTML y el recolector de resultados del informe de cierre."""
import json

import formatear_tablas
import generar_informe_cierre
import generar_informe_exploratorio
import generar_informe_seguridad
import generar_plan
import generar_reporte
import recolectar_resultados


def test_reporte_de_ejecucion():
    html = generar_reporte.build_html({
        "titulo": "Registro", "historia": "HU-001",
        "casos": [{"id": "CP-001", "titulo": "OK", "prioridad": "Alta", "estado": "Aprobado", "duracion_s": 2.5},
                  {"id": "CP-002", "titulo": "Falla", "prioridad": "Media", "estado": "Fallido", "falta_info": ["FI-01"]}],
    })
    assert "<!doctype html>" in html and "Registro" in html
    assert "50%" in html and "FI-01" in html and "data-tip" in html


def test_plan_y_cierre():
    assert "Plan" in generar_plan.build_html({"titulo": "Plan", "objetivos": ["a"], "riesgos": [{"nivel": "Alto", "descripcion": "x"}]})
    html = generar_informe_cierre.build_html({"titulo": "Cierre", "recomendacion": "Apto",
                                               "resultados": {"aprobado": 3, "fallido": 1, "bloqueado": 0}})
    assert "75%" in html and "Apto" in html


def test_seguridad():
    zap = {"site": [{"@name": "https://x", "alerts": [
        {"pluginid": "10038", "name": "CSP Header Not Set", "riskcode": "2", "confidence": "3",
         "desc": "<p>d</p>", "solution": "<p>s</p>", "instances": [{"uri": "https://x/", "method": "GET"}], "count": "1"},
        {"pluginid": "10027", "name": "Comentarios", "riskcode": "0", "confidence": "1", "instances": [], "count": "1"}]}]}
    html = generar_informe_seguridad.build_html(zap, {"falsos_positivos": [{"pluginid": "10027", "motivo": "tercero"}]}, "https://x", "HU-001")
    assert "CSP Header Not Set" in html and "Descartados como falsos positivos" in html


def test_exploratorio():
    datos = {"url": "https://x.com/", "host": "x.com", "config": {"resoluciones": ["360x740", "1366x768"], "max_paginas": 5},
             "resumen": {"paginas": 2, "links": 3, "links_no_verificables": 1},
             "hallazgos": [{"id": "H-01", "categoria": "Link roto", "severidad": "Alta", "pagina": "https://x.com/", "titulo": "Link interno roto (404)", "detalle": "https://x.com/no"},
                           {"id": "H-02", "categoria": "Error de consola", "severidad": "Media", "pagina": "https://x.com/", "titulo": "Error en consola", "detalle": "tercero"}],
             "links": [{"url": "https://x.com/no", "interno": True, "status": 404, "resultado": "roto", "origenes": ["https://x.com/"]},
                       {"url": "https://y.com/", "interno": False, "status": 403, "resultado": "no_verificable", "origenes": ["https://x.com/"]}],
             "responsive": [{"url": "https://x.com/", "resolucion": "360x740", "nombre": "Mobile", "desborde_horizontal": True, "captura": "capturas/inicio-360x740.png"},
                            {"url": "https://x.com/", "resolucion": "1366x768", "nombre": "Desktop", "desborde_horizontal": False}],
             "paginas": [{"url": "https://x.com/", "status": 200, "titulo": "Inicio"}]}
    analisis = {"descartados": [{"id": "H-02", "motivo": "script de terceros"}], "severidades": {"H-01": "Crítica"},
                "exploratorios": [{"id": "EX-01", "titulo": "El menú no cierra", "severidad": "Media", "pasos": ["Abrir menú"]}]}
    html = generar_informe_exploratorio.build_html(datos, analisis)
    assert "Link interno roto (404)" in html and "EX-01" in html and "capturas/inicio-360x740.png" in html
    assert "Descartados" in html and "script de terceros" in html and "Links que no se pudieron verificar" in html
    assert "problemas críticos" in html  # la severidad ajustada a Crítica cambia el veredicto


def test_exploratorio_completo():
    datos = {"url": "https://x.com/", "host": "x.com", "config": {"resoluciones": ["360x740"], "lenta_ms": 3000},
             "resumen": {"paginas": 1, "carga_promedio_ms": 4200, "carga_max_ms": 4200, "carga_p90_ms": 4200},
             "hallazgos": [{"id": "H-01", "categoria": "Recurso que falla", "severidad": "Alta", "pagina": "https://x.com/",
                            "paginas": ["https://x.com/", "https://x.com/b"], "titulo": "stylesheet que no carga (404)",
                            "detalle": "https://x.com/e.css", "evidencia": "capturas/paginas/01-inicio.jpg"}],
             "paginas": [{"url": "https://x.com/", "status": 200, "tiempo_ms": 4200, "captura": "capturas/paginas/01-inicio.jpg",
                          "errores_js": ["boom is not defined"], "metricas": {"ttfb_ms": 120, "dom_ms": 900, "requests": 14, "peso_kb": 512}}],
             "videos": [{"titulo": "Recorrido", "archivo": "videos/recorrido.webm"}]}
    html = generar_informe_exploratorio.build_html(datos, {})
    assert 'src="videos/recorrido.webm#t=1"' in html and 'class="lb thumb' in html  # video embebido y captura ampliable
    assert "y 1 página(s) más" in html and "boom is not defined" in html and "512 KB" in html
    assert "Tiempo de carga por página" in html and "4.2 s" in html


def test_formatear_tablas_es_idempotente(tmp_path):
    import subprocess
    import sys
    archivo = tmp_path / "a.md"
    archivo.write_text("# T\n\n| A | B |\n|---|---|\n| 1 | 2 |\n", encoding="utf-8")
    subprocess.run([sys.executable, formatear_tablas.__file__, str(archivo)], check=True, capture_output=True)
    una_vez = archivo.read_text(encoding="utf-8")
    subprocess.run([sys.executable, formatear_tablas.__file__, str(archivo)], check=True, capture_output=True)
    assert archivo.read_text(encoding="utf-8") == una_vez  # correrlo dos veces no cambia nada
    assert una_vez.count("```") == 2 and "+=====+=====+" in una_vez


def test_recolectar_resultados(tmp_path, monkeypatch):
    raiz = tmp_path
    (raiz / "output" / "ejecuciones").mkdir(parents=True)
    (raiz / "output" / "reportes-bug").mkdir(parents=True)
    k0 = raiz / "herramientas" / "k0lmena" / "reports"
    (k0 / "web").mkdir(parents=True)
    (raiz / "output" / "ejecuciones" / "_resultados-HU-001-a.json").write_text(json.dumps(
        {"historia": "HU-001", "casos": [{"id": "CP-001", "estado": "Fallido"}, {"id": "CP-002", "estado": "Aprobado"}]}), encoding="utf-8")
    (raiz / "output" / "ejecuciones" / "_resultados-HU-002-a.json").write_text(json.dumps(
        {"historia": "HU-002", "casos": [{"id": "CP-001", "estado": "Fallido"}]}), encoding="utf-8")
    # npm test más reciente: CP-001 pasa; un escenario de otra historia no cuenta
    import os, time
    reporte = [{"name": "F", "tags": [{"name": "@HU-001"}], "elements": [
        {"type": "scenario", "name": "uno", "tags": [{"name": "@CP-001"}], "steps": [{"result": {"status": "passed"}}]}]},
        {"name": "G", "tags": [{"name": "@HU-002"}], "elements": [
        {"type": "scenario", "name": "dos", "tags": [{"name": "@CP-009"}], "steps": [{"result": {"status": "failed"}}]}]}]
    (k0 / "web" / "cucumber-report.json").write_text(json.dumps(reporte), encoding="utf-8")
    futuro = time.time() + 60
    os.utime(k0 / "web" / "cucumber-report.json", (futuro, futuro))
    (raiz / "output" / "reportes-bug" / "BUG-001.md").write_text(
        "**ID:** `BUG-001`\n**Título:** x\n**Historia:** HU-001\n**Estado:** Abierto\n**Criticidad / Severidad:** Alta (y)\n", encoding="utf-8")
    monkeypatch.setattr(recolectar_resultados, "RAIZ", raiz)
    monkeypatch.setattr(recolectar_resultados, "K0", k0)
    datos = recolectar_resultados.recolectar("HU-001")
    assert datos["resultados"] == {"aprobado": 2, "fallido": 0, "bloqueado": 0}
    assert datos["bugs"]["por_severidad"]["Alta"] == 1
    assert [b["id"] for b in datos["bugs"]["criticos_abiertos"]] == ["BUG-001"]
