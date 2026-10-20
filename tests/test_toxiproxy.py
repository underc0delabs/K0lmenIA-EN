"""Caos server-side (Toxiproxy): helpers puros de la herramienta."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "herramientas" / "resiliencia"))

import toxiproxy  # noqa: E402


def test_toxic_payload_latencia():
    p = toxiproxy.toxic_payload("latency", "downstream", {"latency": 2000, "jitter": 500})
    assert p["type"] == "latency" and p["stream"] == "downstream"
    assert p["attributes"] == {"latency": 2000, "jitter": 500}
    assert p["toxicity"] == 1.0 and p["name"] == "latency_downstream"


def test_toxic_payload_nombre_y_toxicity():
    p = toxiproxy.toxic_payload("bandwidth", "upstream", {"rate": 10}, toxicity=0.5, nombre="lento")
    assert p["name"] == "lento" and p["toxicity"] == 0.5 and p["attributes"]["rate"] == 10


def test_resumen_proxies():
    proxies = [{"name": "db", "enabled": True, "listen": "127.0.0.1:5433", "upstream": "db:5432",
                "toxics": [{"type": "latency"}]},
               {"name": "api", "enabled": False, "listen": "127.0.0.1:8081", "upstream": "api:8080", "toxics": []}]
    r = toxiproxy.resumen_proxies(proxies)
    assert r[0] == {"nombre": "db", "habilitado": True, "listen": "127.0.0.1:5433", "upstream": "db:5432", "toxics": 1}
    assert r[1]["habilitado"] is False and r[1]["toxics"] == 0


def test_resumen_proxies_vacio():
    assert toxiproxy.resumen_proxies(None) == []
