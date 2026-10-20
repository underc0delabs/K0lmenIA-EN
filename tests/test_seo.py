"""SEO/GEO tool: on-page extraction and AI crawler access (pure helpers)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "seo"))

import seo  # noqa: E402

HTML = """<html><head>
<title>My page</title>
<meta name="description" content="A test description">
<link rel="canonical" href="https://site.com/page">
<meta name="robots" content="noindex, follow">
<meta property="og:title" content="OG title">
<link rel="alternate" hreflang="es" href="https://site.com/es">
<link rel="alternate" hreflang="en" href="https://site.com/en">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","offers":{"@type":"Offer","price":"10"}}</script>
</head><body><h1>Main title</h1></body></html>"""


def test_extract_seo():
    s = seo.extract_seo(HTML)
    assert s["title"] == "My page"
    assert s["meta_description"] == "A test description"
    assert s["canonical"] == "https://site.com/page"
    assert s["meta_robots"] == "noindex, follow"
    assert s["og_title"] == "OG title"
    assert s["h1"] == ["Main title"]
    assert "Product" in s["jsonld_types"] and "Offer" in s["jsonld_types"]
    assert set(s["hreflang"]) == {"es", "en"}


def test_ai_crawlers():
    robots = ("User-agent: *\nDisallow: /private\n\n"
              "User-agent: GPTBot\nDisallow: /\n\n"
              "User-agent: PerplexityBot\nDisallow: /private\n")
    r = seo.ai_crawlers(robots)
    assert r["GPTBot"] == "blocked (Disallow: /)"
    assert r["PerplexityBot"] == "allowed"
    assert "no rule of its own" in r["ClaudeBot"]


def test_extract_seo_empty():
    s = seo.extract_seo("")
    assert s["title"] is None and s["h1"] == [] and s["jsonld_types"] == []
