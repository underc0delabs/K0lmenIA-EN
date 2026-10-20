"""Herramienta de SEO/GEO: extracción on-page y acceso de crawlers de IA (helpers puros)."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "herramientas" / "seo"))

import seo  # noqa: E402

HTML = """<html><head>
<title>Mi página</title>
<meta name="description" content="Una descripción de prueba">
<link rel="canonical" href="https://sitio.com/pagina">
<meta name="robots" content="noindex, follow">
<meta property="og:title" content="OG título">
<link rel="alternate" hreflang="es" href="https://sitio.com/es">
<link rel="alternate" hreflang="en" href="https://sitio.com/en">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","offers":{"@type":"Offer","price":"10"}}</script>
</head><body><h1>Título principal</h1></body></html>"""


def test_extraer_seo():
    s = seo.extraer_seo(HTML)
    assert s["title"] == "Mi página"
    assert s["meta_description"] == "Una descripción de prueba"
    assert s["canonical"] == "https://sitio.com/pagina"
    assert s["meta_robots"] == "noindex, follow"
    assert s["og_title"] == "OG título"
    assert s["h1"] == ["Título principal"]
    assert "Product" in s["jsonld_tipos"] and "Offer" in s["jsonld_tipos"]
    assert set(s["hreflang"]) == {"es", "en"}


def test_crawlers_ia():
    robots = ("User-agent: *\nDisallow: /privado\n\n"
              "User-agent: GPTBot\nDisallow: /\n\n"
              "User-agent: PerplexityBot\nDisallow: /privado\n")
    r = seo.crawlers_ia(robots)
    assert r["GPTBot"] == "bloqueado (Disallow: /)"
    assert r["PerplexityBot"] == "permitido"
    assert "sin regla propia" in r["ClaudeBot"]


def test_extraer_seo_vacio():
    s = seo.extraer_seo("")
    assert s["title"] is None and s["h1"] == [] and s["jsonld_tipos"] == []
