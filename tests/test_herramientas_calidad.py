"""Helpers puros de las herramientas de observabilidad, documentos y contenido."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
for sub in ("observabilidad", "documentos", "contenido"):
    sys.path.insert(0, str(RAIZ / "herramientas" / sub))

import contenido  # noqa: E402
import documentos  # noqa: E402
import observabilidad  # noqa: E402


# ---------------- observabilidad ----------------
METRICS = """# HELP http_requests_total Total de requests
# TYPE http_requests_total counter
http_requests_total{method="GET",code="200"} 1027
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{le="0.1"} 900
http_request_duration_seconds_sum 42.0
http_request_duration_seconds_count 1027
process_cpu_seconds_total 1.5
"""


def test_parse_prometheus():
    m = observabilidad.parse_prometheus(METRICS)
    assert "http_requests_total" in m and m["http_requests_total"]["type"] == "counter"
    assert m["http_requests_total"]["help"] == "Total de requests"
    assert "http_request_duration_seconds" in m  # base del histograma (bucket/sum/count)
    assert "process_cpu_seconds_total" in m


def test_faltantes():
    m = observabilidad.parse_prometheus(METRICS)
    assert observabilidad.faltantes(m, ["http_requests_total", "no_existe"]) == ["no_existe"]
    assert observabilidad.faltantes(m, ["http_requests_total"]) == []


# ---------------- documentos ----------------
def test_buscar_placeholders():
    texto = "Hola {{nombre}}, su total es ${monto}. Lorem ipsum dolor. TODO revisar."
    tipos = {t for t, _ in documentos.buscar_placeholders(texto)}
    assert "Variable de plantilla" in tipos
    assert "Lorem ipsum" in tipos
    assert "Marcador pendiente" in tipos


def test_buscar_placeholders_limpio():
    assert documentos.buscar_placeholders("Factura 001 — Total: $1.250,00 — Cliente: Acme SA") == []


# ---------------- contenido ----------------
def test_revisar_contenido():
    texto = "Bienvenido {{user}}\nEl el carrito está vacío\nhome.cart.empty\nLorem ipsum dolor"
    tipos = {t for t, _, _ in contenido.revisar(texto)}
    assert "Placeholder sin reemplazar" in tipos
    assert "Palabra duplicada" in tipos
    assert "Clave de i18n a la vista" in tipos
    assert "Lorem ipsum" in tipos


def test_revisar_contenido_limpio():
    assert contenido.revisar("Bienvenido a la tienda. Tu carrito está vacío.") == []
