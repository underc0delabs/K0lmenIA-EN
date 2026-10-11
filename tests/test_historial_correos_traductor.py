"""Historial de corridas (últimas 5, con la comparación) y los informes de correos y de traducciones."""
import json

import _historial
import generar_informe_correos
import generar_informe_traductor


def _corrida(carpeta, marca, hallazgos):
    (carpeta / "exploracion.json").write_text(json.dumps({"marca": marca, "resumen": {"hallazgos": len(hallazgos), "links_rotos": len(hallazgos)},
                                                          "hallazgos": hallazgos}), encoding="utf-8")
    (carpeta / "informe-exploratorio.html").write_text("<html></html>", encoding="utf-8")


def test_archivar_guarda_las_ultimas_5(tmp_path):
    for i in range(7):
        _corrida(tmp_path, f"2026101{i}-120000", [])
        destino = _historial.archivar(tmp_path, ["exploracion.json", "informe-exploratorio.html"], "exploracion.json")
        assert (destino / "exploracion.json").exists() and not (tmp_path / "exploracion.json").exists()
    guardadas = sorted(d.name for d in (tmp_path / "historial").iterdir())
    assert len(guardadas) == 4 and guardadas[0] == "20261013-120000"
    assert _historial.archivar(tmp_path, ["exploracion.json"], "exploracion.json") is None  # no hay corrida actual


def test_comparacion_nuevos_resueltos_y_seccion(tmp_path):
    a = {"categoria": "Link roto", "titulo": "Link roto a /viejo (404)", "pagina": "/"}
    b = {"categoria": "Imagen rota", "titulo": "Imagen que no carga", "pagina": "/"}
    c = {"categoria": "Error de JavaScript", "titulo": "x is not defined", "pagina": "/x"}
    _corrida(tmp_path, "20261010-100000", [a, b])
    _historial.archivar(tmp_path, ["exploracion.json", "informe-exploratorio.html"], "exploracion.json")
    actual = {"marca": "20261011-100000", "resumen": {"hallazgos": 2, "links_rotos": 1}, "hallazgos": [dict(a, titulo="Link roto a /viejo (500)"), c]}
    cmp = _historial.comparar("exploratorio", actual, json.loads((next((tmp_path / "historial").iterdir()) / "exploracion.json").read_text(encoding="utf-8")))
    assert [x["titulo"] for x in cmp["nuevos"]] == ["x is not defined"]
    assert [x["titulo"] for x in cmp["resueltos"]] == ["Imagen que no carga"]
    assert len(cmp["siguen"]) == 1   # el mismo link aunque cambie el código (los números no cuentan)
    html = _historial.seccion("exploratorio", tmp_path, actual)
    assert "Evolución de las corridas" in html and "abrir informe" in html and "x is not defined" in html and "Imagen que no carga" in html
    assert "primera corrida" in _historial.seccion("exploratorio", tmp_path / "vacia", actual)


def test_informe_correos():
    datos = {"mailpit": "http://localhost:8025", "filtro": 'to:"ana@test.com"',
             "resumen": {"correos": 1, "expectativas": 2, "cumplen": 1, "no_llegaron": 1, "hallazgos": 2, "links": 2, "links_con_problemas": 1,
                         "variables_sin_reemplazar": 1, "compatibilidad_prom": 88},
             "expectativas": [{"id": "E-01", "caso": "CP-001", "asunto": "Bienvenida", "para": "ana@test.com", "estado": "Cumple", "correo": "M-01",
                               "controles": [{"nombre": "Contiene “Hola”", "ok": True}]},
                              {"id": "E-02", "caso": "CP-007", "asunto": "Recuperá", "para": "ana@test.com", "estado": "No llegó", "controles": []}],
             "hallazgos": [{"id": "C-01", "tipo": "Expectativa", "severidad": "Crítica", "titulo": "No llegó el correo esperado «Recuperá»", "correo": None},
                           {"id": "C-02", "tipo": "Variable sin reemplazar", "severidad": "Alta", "titulo": "{{n}} en el asunto", "correo": "M-01", "detalle": "x"}],
             "correos": [{"id": "M-01", "asunto": "Pedido {{n}}", "de": "a@b.com", "para": ["ana@test.com"], "cc": [], "responder_a": [], "fecha": "2026-10-11T10:00:00",
                          "tamano_kb": 1, "html_kb": 1, "tiene_texto": False, "adjuntos": [{"nombre": "factura.pdf", "kb": 40}],
                          "links": [{"url": "http://localhost/x", "texto": "Ver", "problema": {"severidad": "Alta", "texto": "apunta a un ambiente local"}}],
                          "compatibilidad": {"pct": 88, "problemas": [{"titulo": "border-radius", "clientes": ["Outlook (windows)"]}]},
                          "captura_desktop": "capturas/a-desktop.png", "captura_mobile": "capturas/a-mobile.png", "eml": "eml/a.eml", "ver_en_mailpit": "http://x/view/a"}]}
    html = generar_informe_correos.build_html(datos, {"hallazgos": {"C-02": {"nota": "Lo ven todos"}}})
    assert "correo(s) esperados no llegaron" in html and "Lo que tenía que llegar" in html and "factura.pdf (40 KB)" in html
    assert "apunta a un ambiente local" in html and "Lo ven todos" in html and "Mobile (375 px)" in html


def test_informe_traductor():
    datos = {"host": "x.com", "idiomas": ["es", "en"], "referencia": "es",
             "resumen": {"paginas": 1, "pantallas": 2, "sin_traducir": 1, "claves": 0, "cortados": 0, "formatos": 0,
                         "por_idioma": {"es": {"traducido_pct": 100, "hallazgos": 0, "metodo": "referencia"}, "en": {"traducido_pct": 92.5, "hallazgos": 1, "metodo": "hreflang"}}},
             "pantallas": [{"pagina": "01-inicio", "url": "https://x.com/", "resolucion": "1366x768", "idioma": i, "captura": f"capturas/{i}.png", "hallazgos": n, "lang": i}
                           for i, n in (("es", 0), ("en", 1))],
             "hallazgos": [{"id": "T-01", "tipo": "Sin traducir", "severidad": "Alta", "idioma": "en", "titulo": "“Agregar al carrito” está en es", "detalle": "x",
                            "donde": [{"url": "https://x.com/en/", "resolucion": "1366x768", "recorte": "recortes/1.png"}]}]}
    html = generar_informe_traductor.build_html(datos, {"hallazgos": {"T-01": {"sugerencia": "Add to cart"}}})
    assert "Traducido por idioma" in html and "Sugerencia: Add to cart" in html and "Cada página en todos los idiomas" in html and "92.5 %" in html
