"""Pure helpers of the observability, documents and content tools."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for sub in ("observability", "documents", "content"):
    sys.path.insert(0, str(ROOT / "tools" / sub))

import content  # noqa: E402
import documents  # noqa: E402
import observability  # noqa: E402


# ---------------- observability ----------------
METRICS = """# HELP http_requests_total Total requests
# TYPE http_requests_total counter
http_requests_total{method="GET",code="200"} 1027
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{le="0.1"} 900
http_request_duration_seconds_sum 42.0
http_request_duration_seconds_count 1027
process_cpu_seconds_total 1.5
"""


def test_parse_prometheus():
    m = observability.parse_prometheus(METRICS)
    assert "http_requests_total" in m and m["http_requests_total"]["type"] == "counter"
    assert m["http_requests_total"]["help"] == "Total requests"
    assert "http_request_duration_seconds" in m  # histogram base (bucket/sum/count)
    assert "process_cpu_seconds_total" in m


def test_missing():
    m = observability.parse_prometheus(METRICS)
    assert observability.missing(m, ["http_requests_total", "does_not_exist"]) == ["does_not_exist"]
    assert observability.missing(m, ["http_requests_total"]) == []


# ---------------- documents ----------------
def test_find_placeholders():
    text = "Hello {{name}}, your total is ${amount}. Lorem ipsum dolor. TODO review."
    kinds = {t for t, _ in documents.find_placeholders(text)}
    assert "Template variable" in kinds
    assert "Lorem ipsum" in kinds
    assert "Pending marker" in kinds


def test_find_placeholders_clean():
    assert documents.find_placeholders("Invoice 001 — Total: $1,250.00 — Customer: Acme Inc.") == []


# ---------------- content ----------------
def test_check_content():
    text = "Welcome {{user}}\nThe the cart is empty\nhome.cart.empty\nLorem ipsum dolor"
    kinds = {t for t, _, _ in content.check(text)}
    assert "Unreplaced placeholder" in kinds
    assert "Duplicated word" in kinds
    assert "Visible i18n key" in kinds
    assert "Lorem ipsum" in kinds


def test_check_clean_content():
    assert content.check("Welcome to the store. Your cart is empty.") == []
