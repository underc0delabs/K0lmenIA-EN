"""Server-side chaos (Toxiproxy): pure helpers of the tool."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "resilience"))

import toxiproxy  # noqa: E402


def test_toxic_payload_latency():
    p = toxiproxy.toxic_payload("latency", "downstream", {"latency": 2000, "jitter": 500})
    assert p["type"] == "latency" and p["stream"] == "downstream"
    assert p["attributes"] == {"latency": 2000, "jitter": 500}
    assert p["toxicity"] == 1.0 and p["name"] == "latency_downstream"


def test_toxic_payload_name_and_toxicity():
    p = toxiproxy.toxic_payload("bandwidth", "upstream", {"rate": 10}, toxicity=0.5, name="slow")
    assert p["name"] == "slow" and p["toxicity"] == 0.5 and p["attributes"]["rate"] == 10


def test_proxies_summary():
    proxies = [{"name": "db", "enabled": True, "listen": "127.0.0.1:5433", "upstream": "db:5432",
                "toxics": [{"type": "latency"}]},
               {"name": "api", "enabled": False, "listen": "127.0.0.1:8081", "upstream": "api:8080", "toxics": []}]
    r = toxiproxy.proxies_summary(proxies)
    assert r[0] == {"name": "db", "enabled": True, "listen": "127.0.0.1:5433", "upstream": "db:5432", "toxics": 1}
    assert r[1]["enabled"] is False and r[1]["toxics"] == 0


def test_proxies_summary_empty():
    assert toxiproxy.proxies_summary(None) == []
