"""Calidad de los informes de los agentes de exploración y auditoría: Falta información unificada, avisos del
análisis, corrección de los hallazgos manuales, evidencia de permisos, pasos de resiliencia y secretos de ZAP."""
import pytest

import _estilos_reporte
import generar_informe_accesibilidad
import generar_informe_correos
import generar_informe_exploratorio
import generar_informe_formularios
import generar_informe_logs
import generar_informe_permisos
import generar_informe_pixel_perfect
import generar_informe_rendimiento
import generar_informe_resiliencia
import generar_informe_seguridad
import generar_informe_traductor
import generar_informe_ux

FI = {"falta_informacion": [{"id": "FI-01", "que_falta": "El largo máximo del nombre", "pregunta": "¿Cuántos caracteres acepta?"}]}
CON_FI = [generar_informe_exploratorio, generar_informe_accesibilidad, generar_informe_rendimiento, generar_informe_pixel_perfect,
          generar_informe_ux, generar_informe_formularios, generar_informe_permisos, generar_informe_resiliencia,
          generar_informe_correos, generar_informe_traductor, generar_informe_logs]


@pytest.mark.parametrize("modulo", CON_FI, ids=lambda m: m.__name__.replace("generar_informe_", ""))
def test_falta_informacion_en_cada_informe(modulo):
    html = modulo.build_html({}, FI)
    assert "Falta información" in html and "El largo máximo del nombre" in html and "¿Cuántos caracteres acepta?" in html


def test_falta_informacion_en_seguridad():
    assert "El largo máximo del nombre" in generar_informe_seguridad.build_html({}, FI, None, None)


def test_falta_informacion_acepta_descripcion_como_alias():
    html = _estilos_reporte.falta_informacion([{"id": "FI-02", "descripcion": "Qué pasa sin conexión"}])
    assert "FI-02" in html and "Qué pasa sin conexión" in html
    assert _estilos_reporte.falta_informacion([]) == ""


def test_avisar_analisis_ids_inexistentes_y_severidades(capsys):
    analisis = {"notas": {"H-3": "x"}, "severidades": {"H-01": "alta"}, "descartados": [{"id": "H-02", "motivo": "y"}],
                "hallazgos": {"H-01": {"severidad": "Media"}}}
    avisos = _estilos_reporte.avisar_analisis(analisis, ["H-01", "H-02"])
    assert len(avisos) == 2
    err = capsys.readouterr().err
    assert "H-3 no está en los datos" in err and "'alta'" in err
    assert _estilos_reporte.avisar_analisis({"notas": {"H-01": "ok"}}, ["H-01"]) == []


def test_correccion_de_los_hallazgos_manuales():
    m = {"id": "M-01", "titulo": "Error sin anunciar", "severidad": "Alta", "correccion": "Sumá aria-live al mensaje"}
    assert "Sumá aria-live al mensaje" in generar_informe_accesibilidad.build_html({}, {"manuales": [m]})
    ex = dict(m, id="EX-01", correccion="Validá el largo en el cliente")
    assert "Validá el largo en el cliente" in generar_informe_exploratorio.build_html({}, {"exploratorios": [ex]})


def test_ux_manual_con_url_y_correccion():
    html = generar_informe_ux.build_html({"heuristicas": {"H1": "Visibilidad del estado del sistema"}}, {"hallazgos_manuales": [
        {"heuristica": "H1", "severidad": "Alta", "titulo": "Sin confirmación al pagar", "detalle": "...",
         "correccion": "Mostrá el número de pedido", "url": "https://app.test/checkout", "captura": "capturas/manual-1.png"}]})
    assert "Mostrá el número de pedido" in html and "checkout" in html


def test_permisos_adicional_con_su_captura():
    html = generar_informe_permisos.build_html({}, {"adicionales": [
        {"severidad": "Media", "tipo": "Botón", "titulo": "El invitado ve Eliminar", "detalle": "...", "rol": "invitado",
         "url": "https://app.test/pedidos", "captura": "capturas/manual/pm-01.png", "correccion": "Ocultá el botón por rol"}]})
    assert "capturas/manual/pm-01.png" in html and "Ocultá el botón por rol" in html


def test_resiliencia_manual_con_pasos_en_lista_y_pagina():
    html = generar_informe_resiliencia.build_html({}, {"manuales": [
        {"id": "RM-01", "titulo": "Doble envío", "severidad": "Media", "escenario": "lenta", "pagina": "https://app.test/carrito",
         "pasos": ["Abrir el carrito", "Apretar Pagar dos veces"], "esperado": "Un pedido", "obtenido": "Dos pedidos",
         "correccion": "Deshabilitá el botón mientras espera"}]})
    assert "Abrir el carrito → Apretar Pagar dos veces" in html and "[&#x27;" not in html
    assert "https://app.test/carrito" in html and "Deshabilitá el botón mientras espera" in html


def test_seguridad_enmascara_secretos_en_la_evidencia():
    token = "eyJhbGciOiJIUzI1NiJ9abc123DEF456"
    assert token not in generar_informe_seguridad.enmascarar(f"Authorization: Bearer {token}")
    assert generar_informe_seguridad.enmascarar("Content-Security-Policy-Report-Only") == "Content-Security-Policy-Report-Only"
    zap = {"site": [{"@name": "https://app.test", "alerts": [{"pluginid": "10105", "name": "Token expuesto", "riskcode": "2",
                                                              "confidence": "2", "instances": [{"uri": "https://app.test", "evidence": f"Bearer {token}"}]}]}]}
    html = generar_informe_seguridad.build_html(zap, {}, "https://app.test", None)
    assert "Token expuesto" in html and token not in html and "Bearer eyJh…" in html
