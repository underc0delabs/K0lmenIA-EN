"""Tiempo estimado de ejecución manual, revisor de casos, charters, análisis de logs y los informes de UX y formularios."""
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import analizar_logs
import estimacion
import generar_charters
import generar_informe_formularios
import generar_informe_logs
import generar_informe_revision
import generar_informe_ux
import revisar_casos

RAIZ = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ estimación
def _caso_login():
    return {"id": "CP-1", "titulo": "Inicio de sesión con contraseña incorrecta", "precondiciones": "Usuario registrado", "pasos": [
        {"accion": "Ir a la página de login", "datos": "", "resultado": ""},
        {"accion": "Completar el email y la contraseña", "datos": "Email: ana@test.com\nContraseña: Mala123", "resultado": ""},
        {"accion": "Hacer clic en Ingresar", "datos": "", "resultado": "Se muestra el mensaje de error y el usuario sigue en el login"}]}


def test_formula_por_paso_y_por_caso():
    r = estimacion.estimar_caso(_caso_login())
    assert [p["categoria"] for p in r["pasos"]] == ["Navegar", "Completar campos", "Clic o seleccionar"]
    assert r["pasos"][1]["accion"] == 0.6                      # 2 campos × 0,3
    assert r["factor"] == 1.1 and r["minutos"] == 5.5 and r["texto"] == "5,5 min"
    assert estimacion.estimar_paso("Esperar el correo de confirmación")["minutos"] == 2.0
    assert estimacion.formatear(75) == "1 h 15 min" and estimacion.jira_duracion(6.5) == "7m" and estimacion.hhmm(75) == "01:15"


def test_etiquetas_como_texto_activan_el_factor_de_negativos():
    # En el JSON de generar_casos.py las etiquetas son un texto ("@login @negativo"), no una lista.
    base = {"id": "CP-3", "titulo": "Ingreso al sistema", "pasos": "1. Ir al login\n2. Hacer clic en Ingresar", "resultado": "Ve un aviso"}
    assert estimacion.estimar_caso(dict(base, etiquetas="@login @negativo"))["factor"] == 1.1
    assert estimacion.estimar_caso(dict(base, etiquetas=["login", "borde"]))["factor"] == 1.1
    assert estimacion.estimar_caso(dict(base, etiquetas="@login"))["factor"] == 1.0


def test_tiempo_manual_manda_y_bdd():
    c = dict(_caso_login(), tiempo_min="12")
    r = estimacion.estimar_caso(c)
    assert r["minutos"] == 12 and r["fuente"] == "planilla" and abs(sum(p["minutos"] for p in r["pasos"]) - 12) > 0  # los pasos se reparten
    bdd = {"id": "CP-2", "titulo": "Agregar al carrito", "gherkin": "Scenario: x\n  Given el usuario está en el catálogo\n  When agrega un producto\n  Then el carrito muestra 1 producto\n  And el total es 1500"}
    r = estimacion.estimar_caso(bdd)
    assert len(r["pasos"]) == 4 and r["pasos"][2]["verificacion"] == 0.5 and r["minutos"] >= 1


def test_planilla_con_columna_de_tiempo_y_total(tmp_path):
    from openpyxl import load_workbook
    entrada = tmp_path / "c.json"
    entrada.write_text(json.dumps({"modulo": "HU-9", "casos": [
        {"id": "CP-001", "titulo": "Ingreso válido", "pasos": "1. Ir al login\n2. Completar el email\n3. Hacer clic en Ingresar", "resultado": "Ve el inicio", "prioridad": "Alta"},
        {"id": "CP-002", "titulo": "Recuperar contraseña", "pasos": "1. Ir al login", "resultado": "Llega el correo", "prioridad": "Alta", "tiempo_min": 12}]}), encoding="utf-8")
    salida = tmp_path / "casos-HU-9.xlsx"
    r = subprocess.run([sys.executable, str(RAIZ / "scripts" / "generar_casos.py"), str(entrada), str(salida)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    ws = load_workbook(salida).active
    encabezados = [c.value for c in ws[3]]
    col = encabezados.index("Tiempo estimado (min)") + 1
    assert ws.cell(row=5, column=col).value == 12 and str(ws.cell(row=6, column=col).value).startswith("=SUM(")
    md = salida.with_suffix(".md").read_text(encoding="utf-8")
    assert "Tiempo estimado de ejecución manual" in md and "12 min" in md
    sys.path.insert(0, str(RAIZ / "scripts" / "gestion"))
    from lectores import leer_casos
    casos = leer_casos(salida)
    assert {c["id"]: c["estimacion"]["minutos"] for c in casos}["CP-002"] == 12


def test_gestion_agrega_el_tiempo_y_reintenta_sin_campo():
    sys.path.insert(0, str(RAIZ / "scripts" / "gestion"))
    from adaptadores.base import con_tiempo, intentar_con_tiempo
    from comun import ErrorGestion
    caso = {"estimacion": {"texto": "5,5 min", "minutos": 5.5}}
    assert con_tiempo("Descripción", caso).endswith("Tiempo estimado de ejecución manual: 5,5 min (k0lmenIA)")
    llamadas = []

    def crear(cuerpo):
        llamadas.append(cuerpo)
        if "timetracking" in cuerpo:
            raise ErrorGestion("Field 'timetracking' cannot be set")
        return {"key": "PROJ-1"}

    assert intentar_con_tiempo(crear, {"a": 1, "timetracking": {}}, {"a": 1}) == {"key": "PROJ-1"}
    assert len(llamadas) == 2 and "timetracking" not in llamadas[1]


# ------------------------------------------------------------------ revisor de casos
def test_revisor_detecta_problemas_y_duplicados():
    c1 = {"id": "CP-001", "titulo": "Carrito", "tipo": "manual", "prioridad": "Alta", "precondiciones": "",
          "pasos": [{"accion": "Ir al catálogo", "datos": "", "resultado": ""}, {"accion": "Verificar que funcione con ana@test.com", "datos": "", "resultado": "Funciona correctamente"}]}
    tipos = [h["tipo"] for h in revisar_casos.revisar_manual(c1)]
    assert "Título" in tipos and "Resultado esperado" in tipos and "Paso vago" in tipos and "Datos de prueba" in tipos
    bdd = {"id": "Pagar", "tipo": "cucumber", "gherkin": "Scenario: Pagar\n  Given el usuario hace clic en el botón #pagar\n  When paga"}
    tipos = [h["tipo"] for h in revisar_casos.revisar_bdd(bdd)]
    assert "Then" in tipos and "Estilo" in tipos and "Trazabilidad" in tipos
    a = {"id": "CP-1", "titulo": "Agregar dos productos al carrito actualiza el total", "pasos": [{"accion": "Agregar el producto Mate al carrito"}, {"accion": "Agregar el producto Termo al carrito"}]}
    b = dict(a, id="CP-2", titulo="Agregar dos productos al carrito actualiza el total final")
    assert revisar_casos.duplicados([a, b])[0][2] >= 85


# ------------------------------------------------------------------ charters
def test_notas_de_sesion(tmp_path):
    f = tmp_path / "CH-01.md"
    f.write_text("Charter: CH-01\nTester: Ana\nDuración: 60\nTiempo: preparación 10, prueba 35, bugs 15\n"
                 "BUG: El total no suma el envío [Alta]\nBUG: Mensaje técnico\nPREGUNTA: ¿Cupón antes o después?\nCUBIERTO: Tarjeta\nSIN CUBRIR: Mensajes\n# comentario\n", encoding="utf-8")
    s = generar_charters.leer_notas(f)
    assert s["charter"] == "CH-01" and s["duracion"] == 60 and (s["t_preparacion"], s["t_prueba"], s["t_bugs"]) == (10, 35, 15)
    assert [b["severidad"] for b in s["bugs"]] == ["Alta", "Media"] and s["cubierto"] == ["Tarjeta"] and s["sin_cubrir"] == ["Mensajes"]
    datos = {"historia": "HU-1", "charters": [{"id": "CH-01", "mision": "Explorar el pago", "areas": ["Tarjeta", "Mensajes"], "duracion_min": 60},
                                              {"id": "CH-02", "mision": "Explorar mobile", "areas": ["Botón"], "duracion_min": 45}]}
    assert "Hojas de sesión" in generar_charters.hojas_html(datos) and "## CH-02" in generar_charters.hojas_md(datos)
    html = generar_charters.informe_html(datos, [s])
    assert "1 de 2 sesión(es) hechas" in html and "El total no suma el envío" in html and "Pendiente" in html


# ------------------------------------------------------------------ logs
def test_logs_fechas_firmas_y_stack(tmp_path):
    z = dt.timezone(dt.timedelta(hours=-3))
    assert analizar_logs.fecha_de("2026-10-11 10:22:33,123 ERROR x", z)[0] == dt.datetime(2026, 10, 11, 10, 22, 33, 123000, tzinfo=z)
    assert analizar_logs.fecha_de('1.2.3.4 - - [11/Oct/2026:10:22:33 -0300] "GET / HTTP/1.1" 200', None)[0].utcoffset() == dt.timedelta(hours=-3)
    assert analizar_logs.firma("Fallo id=123 para ana@test.com en 8f2c1a9e-77aa-4c1d-9a2b-3f4e5d6c7b8a") == "Fallo id=<n> para <email> en <uuid>"
    log = tmp_path / "app.log"
    log.write_text("2026-10-11 10:00:00,000 INFO [main] arranca\n"
                   "2026-10-11 10:00:05,000 ERROR [exec-1] c.t.Login - No encontré la plantilla 7\n"
                   "java.lang.IllegalStateException: Template not found\n\tat com.t.Login.mostrar(Login.java:42)\n"
                   "2026-10-11 10:00:09,000 ERROR [exec-2] c.t.Login - No encontré la plantilla 8\n", encoding="utf-8")
    acceso = tmp_path / "access.log"
    acceso.write_text('1.2.3.4 - - [11/Oct/2026:10:00:06 -0300] "GET /ingresar HTTP/1.1" 500 10 "-" "x"\n', encoding="utf-8")
    ents, fuentes = analizar_logs.entradas([log, acceso], z)
    assert len(ents) == 4 and ents[1]["stack"][0].startswith("java.lang.IllegalStateException") and ents[1]["mensaje"].startswith("c.t.Login")
    esc = [{"escenario": "Ingresar", "uri": "f", "linea": 1, "historia": "HU-1", "caso": "CP-002", "estado": "Fallido", "error": "x",
            "inicio": dt.datetime(2026, 10, 11, 10, 0, 4, tzinfo=z), "fin": dt.datetime(2026, 10, 11, 10, 0, 6, tzinfo=z)}]
    _, firmas, tiempo, cruces = analizar_logs.analizar(ents, esc, None, None, 1)
    login = next(f for f in firmas if "plantilla" in f["ejemplo"])
    assert login["cuenta"] == 2 and login["stack"] and login["excepcion"].endswith("IllegalStateException")
    assert {x["firma"] for x in cruces[0]["errores"]} == {login["id"], next(f["id"] for f in firmas if "→ 500" in f["ejemplo"])}
    html = generar_informe_logs.build_html({"resumen": {"errores": 3, "firmas_error": 2, "fallidos": 1, "fallidos_con_errores": 1, "escenarios": 1},
                                            "firmas": firmas, "linea_tiempo": tiempo, "escenarios": cruces, "fuentes": fuentes, "ventana": {}}, {})
    assert "coinciden con errores del servidor" in html and "stack trace" in html


# ------------------------------------------------------------------ informes
def test_informes_de_revision_ux_y_formularios():
    caso = {"historia": "HU-1", "id": "CP-001", "titulo": "Carrito", "tipo": "manual", "puntaje": 61, "tiempo": "4 min", "tiempo_min": 4, "archivo": "x.xlsx",
            "hallazgos": [{"severidad": "Media", "tipo": "Título", "titulo": "Título poco descriptivo", "sugerencia": "..."}]}
    html = generar_informe_revision.build_html({"casos": [caso], "por_historia": [{"historia": "HU-1", "casos": 1, "negativos": 0, "puntaje_prom": 61, "tiempo_min": 4, "hallazgos": []}],
                                                "resumen": {"casos": 1, "puntaje_prom": 61, "a_mejorar": 1, "tiempo_total": "4 min"}},
                                               {"propuestas": {"HU-1:CP-001": {"titulo": "Agregar un producto actualiza el carrito"}}})
    assert "Versión propuesta" in html and "Agregar un producto actualiza el carrito" in html and "Muchos casos a mejorar" in html
    heur = {f"H{i}": f"Heurística {i}" for i in range(1, 11)}
    ux = {"heuristicas": heur, "resumen": {"paginas": 1}, "resoluciones": ["1366x768"], "pantallas": [],
          "hallazgos": [{"id": "U-01", "heuristica": "H9", "severidad": "Alta", "titulo": "La página de error es técnica", "detalle": "nginx", "donde": [{"url": "https://x.com/"}]}],
          "pagina_404": {"url": "https://x.com/z", "status": 404, "links": 0, "tecnico": True, "texto": "404 Not Found nginx"}}
    html = generar_informe_ux.build_html(ux, {"hallazgos_manuales": [{"heuristica": "H1", "severidad": "Alta", "titulo": "Sin confirmación al pagar"}]})
    assert "Puntaje por heurística" in html and "revisión manual" in html and "Página de error 404" in html
    form = {"id": "F-01", "nombre": "registro", "url": "https://x.com/r", "metodo": "POST", "accion": "/r", "hallazgos": [],
            "campos": [{"nombre": "email", "etiqueta": "Email", "tipo": "text", "requerido": True,
                        "pruebas": [{"regla": "Email sin @", "valor": "ana", "esperado": "rechaza", "resultado": "acepta", "ok": False, "mensaje": "", "fuente": None}]}]}
    html = generar_informe_formularios.build_html({"formularios": [form], "hallazgos": [{"id": "V-01", "severidad": "Alta", "tipo": "Acepta un valor inválido",
                                                                                          "titulo": "“Email” acepta: Email sin @", "formulario": "F-01"}],
                                                   "resumen": {"formularios": 1, "campos": 1, "pruebas": 1, "pruebas_fallan": 1, "acepta_invalidos": 1}}, {})
    assert "acepta datos inválidos" in html and "Email sin @" in html
