"""E-commerce testers (Shopify, WordPress / WooCommerce, PrestaShop and VTEX): authorization, catalog, findings, suggestions and report."""
import datetime
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "ecommerce"))

import _common as c  # noqa: E402
import generate_ecommerce_report as gi  # noqa: E402
import prestashop  # noqa: E402
import shopify  # noqa: E402
import vtex  # noqa: E402
import wordpress  # noqa: E402


def test_authorization_by_host_and_path():
    entries = c.authorized_list({"ECOMMERCE_AUTHORIZED_URLS": "https://store-qa.example.com, staging.example.com/shop"})
    assert c.is_authorized("https://store-qa.example.com/products/x", entries)
    assert c.is_authorized("https://staging.example.com/shop/cart", entries)
    assert not c.is_authorized("https://staging.example.com/other", entries)
    assert not c.is_authorized("https://store-qa.example.com.evil.com", entries)
    assert not c.is_authorized("https://staging.example.com/shopping", entries)  # the whole path segment has to match


def test_without_authorized_stops():
    with pytest.raises(SystemExit):
        c.authorize("https://x.example.com", {})


def test_robots_blocks_everything():
    assert c.robots_blocks_all("User-agent: *\nDisallow: /\n")
    assert not c.robots_blocks_all("User-agent: *\nDisallow: /checkout\n\nUser-agent: BadBot\nDisallow: /\n")


def test_errors_in_html_ignores_scripts():
    html = "<script>var x='Liquid error';</script><p>Liquid error: Could not find asset</p>"
    assert c.html_errors(html, shopify.ERROR_PATTERNS)[0][0] == "Liquid error"
    assert not c.html_errors("<script>Liquid error</script><p>ok</p>", shopify.ERROR_PATTERNS)


def test_jsonld_product_with_offers():
    html = '<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","offers":{"@type":"Offer","price":"10"}}</script>'
    assert {"Product", "Offer"} <= c.jsonld_types(html)


def test_catalog_aggregates_issues():
    prods = [{"title": "Free", "active": True, "prices": [0.0], "image": True},
             {"title": "No photo", "active": True, "prices": [10.0], "image": False},
             {"title": "Pre-order", "active": True, "prices": [5.0], "tracks_stock": True, "stock": 0, "keeps_selling": True},
             {"title": "Bad strikethrough", "active": True, "prices": [10.0], "compare_at": [8.0]},
             {"title": "Draft", "active": False, "prices": [0.0]}]
    h, rows, n = c.analyze_catalog(prods)
    assert n == 4  # the draft does not count
    texts = " ".join(x["text"] for x in h)
    assert "price 0" in texts and "without an image" in texts and "overselling" in texts and "strikethrough" in texts
    assert h[0]["severity"] == "High"


def test_shopify_normalizes_and_detects():
    p = shopify.normalize_admin({"title": "T-shirt", "handle": "t-shirt", "status": "ACTIVE", "totalInventory": 0, "tracksInventory": True,
                                 "onlineStoreUrl": None, "featuredMedia": None, "seo": {"description": ""},
                                 "variants": {"nodes": [{"sku": "", "price": "0.00", "compareAtPrice": None, "inventoryPolicy": "CONTINUE"}]}})
    assert set(c.product_issues(p)) >= {"zero_price", "oversell", "no_image", "no_sku", "unpublished", "no_seo"}


def test_shopify_findings_and_suggestions():
    inv = {"store": {"plan": {"partnerDevelopment": False, "publicDisplayName": "Basic"}, "enabledPresentmentCurrencies": ["USD", "CAD"]},
           "policies": {"refund-policy": 404, "privacy-policy": 200, "terms-of-service": 200, "shipping-policy": 200},
           "webhooks": [{"topic": "ORDERS_CREATE", "uri": "http://receiver.example.com/hook"}],
           "discounts": [{"codeDiscount": {"title": "WELCOME", "status": "ACTIVE"}}],
           "shipping": [{"name": "General", "default": True, "activeMethodDefinitionsCount": 0}],
           "scopes": ["read_products", "write_orders"], "products_norm": []}
    h, s = shopify.findings_and_suggestions(inv)
    texts = " ".join(x["text"] for x in h)
    assert "This is not a development store" in texts and "refund" in texts and "without HTTPS" in texts
    assert "has no active methods" in texts and "write_orders" in texts
    assert any(x["element"] == "WELCOME" for x in s) and any(x["area"] == "Markets" for x in s)
    assert any("Bogus Gateway" in x["test"] for x in s)


def test_shopify_rejects_mutations():
    with pytest.raises(ValueError):
        shopify.graphql("x.myshopify.com", "t", "2026-07", "mutation { productDelete(input:{id:\"1\"}) { deletedProductId } }")


def test_shopify_public_theme():
    html = '<script>Shopify.theme = {"name":"Dawn","id":1,"schema_version":"15.0.0","role":"main"};</script>'
    assert shopify.public_theme(html)["schema_version"] == "15.0.0"


def test_woocommerce_test_mode():
    assert wordpress.in_test_mode({"settings": {"testmode": {"value": "yes"}}}) is True
    assert wordpress.in_test_mode({"settings": {"environment": {"value": "live"}}}) is False
    assert wordpress.in_test_mode({"settings": {}}) is None


def test_store_api_price_in_minor_units():
    p = wordpress.normalize_store({"name": "Mug", "slug": "mug", "prices": {"price": "1599", "regular_price": "1999", "currency_minor_unit": 2},
                                   "on_sale": True, "images": [], "type": "simple"})
    assert p["prices"] == [15.99] and p["compare_at"] == [19.99] and p["image"] is False


def test_wordpress_findings_and_suggestions():
    now = datetime.datetime(2026, 10, 19, 12, tzinfo=datetime.timezone.utc)
    inv = {"woocommerce": True,
           "system_status": {"environment": {"version": "9.3.1", "wp_cron": False, "remote_post_successful": False, "php_version": "7.4"},
                             "database": {"wc_database_version": "8.9.0"},
                             "active_plugins": [{"plugin": "woocommerce-gateway-stripe/x.php", "name": "Stripe", "version": "8.0.0", "version_latest": "9.1.0"}],
                             "theme": {"name": "Store", "has_outdated_templates": True, "has_woocommerce_support": True,
                                       "overrides": [{"file": "woocommerce/checkout/form-checkout.php", "version": "3.5.0", "core_version": "9.4.0"}]},
                             "pages": [{"page_name": "Checkout", "page_set": True, "page_exists": True, "page_visible": True,
                                        "shortcode_required": True, "shortcode_present": False, "block_present": False}]},
           "gateways": [{"id": "stripe", "title": "Card", "enabled": True, "settings": {"testmode": {"value": "no"}}}],
           "zones": [{"name": "Alaska", "methods": []}],
           "coupons": [{"code": "OLD", "date_expires": "2025-01-01T00:00:00"}, {"code": "TODAY10", "minimum_amount": "5000"}],
           "webhooks": [{"name": "ERP", "topic": "order.created", "status": "disabled"}],
           "cli_cron": [{"hook": "woocommerce_cancel_unpaid_orders", "next_run_gmt": "2026-10-19 08:00:00"}],
           "products_norm": []}
    h, s = wordpress.findings_and_suggestions(inv, now)
    texts = " ".join(x["text"] for x in h)
    for expected in ("the database update still needs to run", "WP-Cron", "remote_post", "Stripe 8.0.0", "outdated",
                     "is missing the WooCommerce shortcode", "LIVE mode", "Alaska", "OLD", "disabled", "cron event(s) overdue"):
        assert expected in texts, expected
    assert any(x["element"] == "TODAY10" and "5000" in x["test"] for x in s)
    assert any(x["area"] == "Payments" for x in s)


def test_wordpress_action_scheduler_and_automatic_updates():
    inv = {"woocommerce": True, "cli_failed_actions": 7,
           "cli_plugins": [{"name": "woocommerce", "status": "active", "auto_update": "on"},
                           {"name": "old", "status": "inactive", "auto_update": "on"}]}
    h, _ = wordpress.findings_and_suggestions(inv)
    texts = " ".join(x["text"] for x in h)
    assert "7 failed scheduled action(s)" in texts
    assert "1 active plugin(s) with automatic updates (woocommerce)" in texts  # the inactive one does not count


def test_wordpress_table_shows_hpos():
    inv = {"system_status": {"settings": {"HPOS_enabled": True, "HPOS_sync_enabled": True}}, "products_norm": []}
    _, tables, _ = wordpress.tables_and_indicators(inv, "https://qa.example.com")
    assert ["Order storage", "HPOS (dedicated tables) with sync"] in tables[0]["rows"]


def test_prestashop_multilanguage():
    assert prestashop.ml([{"id": "1", "value": "T-shirt"}, {"id": "2", "value": "Remera"}]) == "T-shirt"
    assert prestashop.ml({"language": [{"id": "1", "value": "Hello"}]}) == "Hello"
    assert prestashop.ml("text") == "text"
    assert prestashop.ml([]) is None


def test_prestashop_normalizes_and_detects():
    p = prestashop.normalize_product(
        {"id": "5", "name": [{"id": "1", "value": "T-shirt"}], "reference": "", "price": "0.000000", "active": "1",
         "available_for_order": "0", "id_tax_rules_group": "0", "meta_description": [{"id": "1", "value": ""}],
         "id_default_image": "0", "out_of_stock": "1", "associations": {}},
        {"5": 0}, {"PS_TAX": "1", "PS_ORDER_OUT_OF_STOCK": "0"}, "https://qa.example.com")
    assert set(c.product_issues(p)) >= {"zero_price", "oversell", "no_image", "no_sku", "unpublished", "no_seo"}
    assert p["url"].endswith("id_product=5")


def test_prestashop_total_stock_per_product():
    m = prestashop.stock_map([{"id_product": "7", "id_product_attribute": "0", "quantity": "12"},
                              {"id_product": "7", "id_product_attribute": "3", "quantity": "4"}])
    assert m == {"7": 12}  # the row with attribute 0 is the product total


def test_prestashop_findings_and_suggestions():
    now = datetime.datetime(2026, 10, 19, 12, tzinfo=datetime.timezone.utc)
    inv = {"webservice": True,
           "config": {"PS_SHOP_ENABLE": "0", "PS_CATALOG_MODE": "1", "PS_SSL_ENABLED": "0", "PS_SMARTY_FORCE_COMPILE": "2",
                      "PS_CCCCSS": "0", "PS_CCCJS": "0", "PS_GUEST_CHECKOUT_ENABLED": "1", "PS_ORDER_PROCESS_TYPE": "1",
                      "PS_MULTISHOP_FEATURE_ACTIVE": "0"},
           "carriers": [{"id": "1", "name": [{"id": "1", "value": "Post"}], "active": "0", "deleted": "0", "is_free": "0"}],
           "currencies": [{"iso_code": "USD", "active": "1"}, {"iso_code": "EUR", "active": "1"}],
           "languages": [{"iso_code": "en", "active": "1"}, {"iso_code": "es", "active": "1"}],
           "cart_rules": [{"id": "1", "code": "OLD", "active": "1", "date_to": "2025-01-01 00:00:00", "quantity": "5"},
                          {"id": "2", "code": "TODAY10", "active": "1", "date_to": "0000-00-00 00:00:00", "quantity": "10"}],
           "shops": [{"id": "1"}], "ps_mode_dev": True, "products_norm": []}
    h, s = prestashop.findings_and_suggestions(inv, now)
    texts = " ".join(x["text"] for x in h)
    for expected in ("maintenance mode", "Catalog mode", "HTTPS", "Smarty recompiles", "not combined or compressed",
                     "no active carrier", "OLD", "Developer mode"):
        assert expected in texts, expected
    assert any(x["element"] == "TODAY10" for x in s)
    assert any(x["area"] == "Currencies" for x in s) and any(x["area"] == "Languages" for x in s)
    assert any(x["element"] == "Guest checkout" for x in s)


def test_vtex_items_normalizes_list_or_paginated():
    assert vtex._items([{"a": 1}]) == [{"a": 1}]
    assert vtex._items({"items": [1, 2]}) == [1, 2]
    assert vtex._items(None) == []


def test_vtex_normalizes_and_detects():
    p = {"productName": "T-shirt", "productId": "10", "productReference": "", "linkText": "t-shirt",
         "link": "https://t/t-shirt/p", "metaTagDescription": "",
         "items": [{"itemId": "1", "referenceId": [{"Key": "RefId", "Value": ""}], "images": [],
                    "sellers": [{"sellerId": "1", "commertialOffer": {"Price": 0.0, "ListPrice": 0.0, "AvailableQuantity": 0, "IsAvailable": False}}]}]}
    n = vtex.normalize(p, "https://t")
    assert set(c.product_issues(n)) >= {"zero_price", "no_image", "no_sku", "unpublished", "no_seo"}
    assert n["url"] == "https://t/t-shirt/p"


def test_vtex_findings_and_suggestions():
    now = datetime.datetime(2026, 10, 19, 12, tzinfo=datetime.timezone.utc)
    inv = {"public_api": True, "workspace": "master",
           "saleschannels": [{"Id": "1", "Name": "Main", "IsActive": True, "CurrencyCode": "BRL"}],
           "shipping": {"items": []},
           "promotions": {"items": [{"name": "BLACK", "isActive": True, "endDateUtc": "2025-01-01T00:00:00Z"},
                                    {"name": "CHRISTMAS", "isActive": True, "endDateUtc": "2027-01-01T00:00:00Z"}]},
           "products_norm": []}
    h, s = vtex.findings_and_suggestions(inv, now)
    texts = " ".join(x["text"] for x in h)
    assert "master workspace" in texts
    assert "shipping policy" in texts
    assert "BLACK" in texts
    assert any(x["element"] == "CHRISTMAS" for x in s)
    assert any(x["area"] == "Sales channels" for x in s)


def test_html_report_with_analysis_and_history(tmp_path, monkeypatch):
    monkeypatch.setenv("K0LMENIA_PORTAL", "0")
    data = {"generated": "2026-10-19T10:00:00", "story": "US-020", "platform": "wordpress",
            "store": {"url": "https://qa.example.com", "name": "QA", "version": "WordPress 6.8 · WooCommerce 9.4", "environment": "—"},
            "storefront": {"checks": [{"check": "Home page", "status": "ok", "detail": "HTTP 200"}]},
            "indicators": [{"label": "Products with issues", "value": 2, "tone": "bad", "detail": "price"}],
            "tables": [{"title": "Payment gateways", "columns": ["Gateway", "Mode"], "rows": [["Card", "Test"]]}],
            "findings": [{"severity": "High", "area": "Payments", "text": "Gateway in LIVE mode"},
                         {"severity": "Low", "area": "SEO", "text": "No sitemap"}],
            "suggestions": [{"area": "Payments", "element": "Card", "test": "Pay approved and declined"}],
            "summary": {"findings": 2, "critical": 1, "products_with_issues": 2, "suggestions": 1}, "errors": {"coupons": "HTTP 403"}}
    (tmp_path / "wordpress.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    analysis = {"verdict": "Ready with 1 risk", "verdict_tone": "warn", "discarded": [{"text": "No sitemap", "reason": "staging"}],
                "tests": [{"id": "TC-001", "area": "Payments", "case": "Payment declined", "result": "Passed"}],
                "missing_info": [{"id": "MI-01", "what_is_missing": "minimum amount for free shipping", "question": "What is it?"}]}
    (tmp_path / "analysis.json").write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
    gi.generate(tmp_path / "wordpress.json", tmp_path / "wordpress-report.html", tmp_path / "analysis.json")
    html = (tmp_path / "wordpress-report.html").read_text(encoding="utf-8")
    for expected in ("WordPress / WooCommerce", "Ready with 1 risk", "Gateway in LIVE mode", "Payment declined", "Payment gateways",
                     "MI-01", "HTTP 403", "Run history", "Storefront checks"):
        assert expected in html, expected
    assert "No sitemap" not in html  # discarded by the agent


def test_save_archives_previous_run(tmp_path, monkeypatch):
    monkeypatch.setenv("K0LMENIA_PORTAL", "0")
    base = {"platform": "shopify", "store": {"url": "https://x.myshopify.com"}, "findings": [{"severity": "Medium", "area": "Legal", "text": "a"}],
            "suggestions": [], "tables": [], "indicators": []}
    c.save("shopify", dict(base, generated="2026-10-18T10:00:00"), tmp_path)
    c.save("shopify", dict(base, generated="2026-10-19T10:00:00"), tmp_path)
    assert (tmp_path / "shopify.json").exists() and (tmp_path / "shopify-report.html").exists()
    assert len(list((tmp_path / "history").glob("*/shopify.json"))) == 1
    assert json.loads((tmp_path / "shopify.json").read_text(encoding="utf-8"))["summary"]["by_severity"]["Medium"] == 1
