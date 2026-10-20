#!/usr/bin/env python3
"""
Functional QA survey of an AUTHORIZED PrestaShop store (read-only).

Usage (from the repo root):
    python tools/ecommerce/prestashop.py --store https://my-store-qa.example.com [--story US-001]
        [--product https://.../product.html] [--max-products 300] [--local C:/www/mystore] [--confirm]

What it does:
- Checks that the store is in ECOMMERCE_AUTHORIZED_URLS in the .env.
- Public storefront: common checks (home and key pages, robots, sitemap, 404, visible PHP errors or
  PrestaShop exceptions —a sign that developer mode was left on—) and structured
  data of a product page.
- Webservice API (optional, with PRESTASHOP_WEBSERVICE_KEY of a READ-ONLY key): products with
  stock and combinations, carriers and whether any is active, zones and countries, currencies, cart rules
  (vouchers/coupons), shops (multistore), languages and the settings that matter most for QA and web performance
  (maintenance mode, catalog mode, HTTPS, Smarty/compilation, combine-compress-cache CSS and JS,
  guest checkout, rounding, taxes, mandatory terms).
- Local installation (optional, --local or PRESTASHOP_LOCAL_PATH): PrestaShop version and whether _PS_MODE_DEV_
  was left on (slow and leaks errors in production).
- Computes findings and test suggestions and leaves in output/prestashop/<story or host>/: prestashop.json
  and prestashop-report.html (the previous run moves to history/).

GET only (and reading local files). It does not create orders, customers or products or change settings. The
store's security is not reviewed here (security-analyst, web-pentester).
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as c  # noqa: E402

ERROR_PATTERNS = [("PHP error", r"(?:Fatal error|Parse error|Warning|Notice|Deprecated):\s.{0,200}? on line \d+"),
                  ("PrestaShop exception", r"PrestaShop(?:Database)?Exception|\[PrestaShop\][^<]{0,120}(?:error|exception)"),
                  ("Visible SQL error", r"(?:SQLSTATE\[|You have an error in your SQL syntax|Duplicate entry '[^']*' for key)"),
                  ("No database connection", r"Link to database cannot be established|Error establishing a database connection")]

# Settings we request from the Webservice (filtered by name) and what they mean for QA / web performance.
CONFIG_KEYS = ["PS_SHOP_ENABLE", "PS_MAINTENANCE_IP", "PS_CATALOG_MODE", "PS_SSL_ENABLED", "PS_SSL_ENABLED_EVERYWHERE",
               "PS_SMARTY_CACHE", "PS_SMARTY_FORCE_COMPILE", "PS_SMARTY_CONSOLE", "PS_CSS_THEME_CACHE", "PS_JS_THEME_CACHE",
               "PS_CCCCSS", "PS_CCCJS", "PS_HTML_THEME_COMPRESSION", "PS_CACHE_ENABLED", "PS_HTACCESS_CACHE_CONTROL",
               "PS_GUEST_CHECKOUT_ENABLED", "PS_ORDER_PROCESS_TYPE", "PS_CONDITIONS", "PS_REGISTRATION_PROCESS_TYPE",
               "PS_TAX", "PS_ROUND_TYPE", "PS_PRICE_ROUND_MODE", "PS_STOCK_MANAGEMENT", "PS_ORDER_OUT_OF_STOCK",
               "PS_TOKEN_ENABLE", "PS_MULTISHOP_FEATURE_ACTIVE", "PS_CURRENCY_DEFAULT", "PS_ALLOW_MULTISHIPPING"]


def ml(v):
    """A multi-language Webservice field may come as a string, {"value":..} or a list per language."""
    if isinstance(v, dict):
        if "language" in v:
            v = v["language"]
        else:
            return v.get("value")
    if isinstance(v, list):
        if not v:
            return None
        return v[0].get("value") if isinstance(v[0], dict) else v[0]
    return v


def ps(base, key, resource, params=""):
    """GET to the PrestaShop Webservice with the key as the user (no password). (data, error)."""
    sep = "&" if "?" in params else "?"
    url = f"{base}/api/{resource}{params}{sep}output_format=JSON" if params else f"{base}/api/{resource}?output_format=JSON"
    r = c.http(url, headers={"Accept": "application/json"}, user=key, password="", timeout=40)
    if r.error:
        return None, r.error
    if r.status in (401, 403):
        return None, f"HTTP {r.status}: the Webservice key is invalid or does not have read permission on “{resource}”"
    if r.status == 404:
        return None, f"HTTP 404: the resource “{resource}” is not enabled in the Webservice"
    if not r.ok:
        return None, f"HTTP {r.status}: {(r.text or '')[:160]}"
    d = r.json()
    return (d, None) if d is not None else (None, "non-JSON response (does the Webservice answer XML? JSON was requested)")


def _list(d, key):
    """The Webservice returns {"products": [...]}; sometimes a single object instead of a list."""
    if not isinstance(d, dict):
        return []
    v = d.get(key)
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _num(x):
    try:
        return float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


def stock_map(rows):
    """id_product -> total quantity (the row with id_product_attribute 0 is the product total)."""
    m = {}
    for s in rows:
        pid = str(s.get("id_product") or "")
        q = _num(s.get("quantity"))
        if not pid or q is None:
            continue
        if str(s.get("id_product_attribute") or "0") == "0" or pid not in m:
            m[pid] = int(q)
    return m


def normalize_product(p, stock, cfg, base):
    pid = str(p.get("id") or "")
    price = _num(p.get("price"))
    active = str(p.get("active")) == "1"
    associations = p.get("associations") or {}
    combinations = _list(associations, "combinations")
    images = _list(associations, "images")
    oos = str(p.get("out_of_stock") or "2")  # 0 deny, 1 allow, 2 per the store settings
    global_allowed = cfg.get("PS_ORDER_OUT_OF_STOCK") == "1"
    calculates = cfg.get("PS_TAX") != "0"
    return {"title": ml(p.get("name")), "ref": (p.get("reference") or "").strip() or pid, "active": active,
            "url": f"{base}/index.php?controller=product&id_product={pid}" if pid else None,
            "prices": [price] if not combinations else [],
            "compare_at": [None],
            "image": bool(images) or str(p.get("id_default_image") or "0") != "0",
            "stock": stock.get(pid), "tracks_stock": stock.get(pid) is not None,
            "keeps_selling": oos == "1" or (oos == "2" and global_allowed),
            "variants": len(combinations) or 1,
            "no_sku": 0 if (p.get("reference") or "").strip() else 1,
            "tax": (str(p.get("id_tax_rules_group") or "0") != "0") if calculates else None,
            "seo": bool(ml(p.get("meta_description"))),
            "published": str(p.get("available_for_order")) == "1",
            "type": "combinations" if combinations else "simple"}


def _date(s):
    s = (s or "").strip()
    if not s or s.startswith("0000"):
        return None
    try:
        return datetime.datetime.fromisoformat(s.replace("T", " ")).replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return None


def findings_and_suggestions(inv, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    h, s = [], []
    cfg = inv.get("config") or {}

    if inv.get("webservice") and cfg.get("PS_SHOP_ENABLE") == "0":
        h.append({"severity": "High", "area": "Store", "text": "The store is in maintenance mode (PS_SHOP_ENABLE = 0): visitors cannot see it. On staging it may be intentional; confirm it."})
    if cfg.get("PS_CATALOG_MODE") == "1":
        h.append({"severity": "High", "area": "Store", "text": "Catalog mode is active (PS_CATALOG_MODE = 1): there is no cart or checkout, only the storefront. If the store is expected to sell, it is a bug."})
    if cfg.get("PS_SSL_ENABLED") == "0":
        h.append({"severity": "High", "area": "Store", "text": "The store does not have HTTPS enabled (PS_SSL_ENABLED = 0): login and payment travel unencrypted."})
    elif cfg.get("PS_SSL_ENABLED") == "1" and cfg.get("PS_SSL_ENABLED_EVERYWHERE") == "0":
        h.append({"severity": "Low", "area": "Store", "text": "HTTPS is enabled but not on the whole store (PS_SSL_ENABLED_EVERYWHERE = 0): some pages are served over HTTP."})

    # Web performance (Advanced Parameters → Performance)
    if cfg.get("PS_SMARTY_FORCE_COMPILE") in ("1", "2"):
        h.append({"severity": "Medium", "area": "Web performance", "text": "Smarty recompiles templates on every load (PS_SMARTY_FORCE_COMPILE ≠ 0): in production it should compile only when the file changed. It slows down every page."})
    if cfg.get("PS_SMARTY_CACHE") == "0":
        h.append({"severity": "Medium", "area": "Web performance", "text": "The Smarty template cache is disabled (PS_SMARTY_CACHE = 0): every page is built from scratch."})
    if cfg.get("PS_CCCCSS") == "0" or cfg.get("PS_CCCJS") == "0":
        what = ", ".join(x for x, k in (("CSS", "PS_CCCCSS"), ("JS", "PS_CCCJS")) if cfg.get(k) == "0")
        h.append({"severity": "Low", "area": "Web performance", "text": f"The {what} files are not combined or compressed (CCC disabled): more requests and more bytes per page. Enable it in production and check that the theme does not break."})
    if cfg.get("PS_CACHE_ENABLED") == "0":
        h.append({"severity": "Low", "area": "Web performance", "text": "The PrestaShop cache is disabled (PS_CACHE_ENABLED = 0)."})

    # Checkout and prices
    if cfg.get("PS_TOKEN_ENABLE") == "0":
        h.append({"severity": "Medium", "area": "Checkout", "text": "Front-office security tokens are disabled (PS_TOKEN_ENABLE = 0): the cart and the checkout are left without CSRF protection."})
    if cfg.get("PS_GUEST_CHECKOUT_ENABLED") is not None:
        inv_guest = cfg.get("PS_GUEST_CHECKOUT_ENABLED") == "1"
        s.append({"area": "Checkout", "element": "Guest checkout", "test": f"Guest checkout is {'enabled' if inv_guest else 'disabled'}: {'buy without creating an account and check that the order is linked to the email' if inv_guest else 'check that it requires signing up / logging in before paying'}."})
    if cfg.get("PS_ORDER_PROCESS_TYPE") is not None:
        s.append({"area": "Checkout", "element": "Purchase process", "test": f"The checkout is {'one-page' if cfg.get('PS_ORDER_PROCESS_TYPE') == '1' else '5-step'}: go through address, carrier, payment and confirmation on mobile and desktop."})
    if cfg.get("PS_CONDITIONS") == "1":
        s.append({"area": "Checkout", "element": "Terms and conditions", "test": "The terms are mandatory: the order cannot be confirmed without ticking the checkbox and the link opens the terms page (CMS)."})
    if cfg.get("PS_ROUND_TYPE") or cfg.get("PS_PRICE_ROUND_MODE"):
        s.append({"area": "Checkout", "element": "Price rounding", "test": "Check the rounding (PS_ROUND_TYPE / PS_PRICE_ROUND_MODE): subtotal, taxes, shipping and total have to add up in the cart, the checkout, the order and the email, with quantities that produce decimals."})

    # Carriers
    carriers = [t for t in inv.get("carriers") or [] if str(t.get("active")) == "1" and str(t.get("deleted") or "0") == "0"]
    if inv.get("carriers") is not None and not carriers:
        h.append({"severity": "High", "area": "Shipping", "text": "There is no active carrier: a purchase with shipping cannot be completed."})
    for t in carriers[:6]:
        name = ml(t.get("name")) or t.get("id")
        s.append({"area": "Shipping", "element": name, "test": f"Checkout choosing “{name}”{' (free shipping)' if str(t.get('is_free')) == '1' else ''}: cost by zone and weight, price ranges, free-shipping minimum and recalculation when the address changes."})

    # Currencies
    currencies = [m for m in inv.get("currencies") or [] if str(m.get("active")) == "1" and str(m.get("deleted") or "0") == "0"]
    if len(currencies) > 1:
        s.append({"area": "Currencies", "element": ", ".join(m.get("iso_code") or "?" for m in currencies[:6]), "test": "Switch currency in the store: prices are converted with the expected rate, rounding is correct and the payment is charged in the currency shown."})

    # Languages
    languages = [i for i in inv.get("languages") or [] if str(i.get("active")) == "1"]
    if len(languages) > 1:
        s.append({"area": "Languages", "element": ", ".join(i.get("iso_code") or "?" for i in languages[:8]), "test": "With the translation-analyst: each page in each active language (untranslated text, visible keys, product pages, checkout and emails)."})

    # Vouchers / cart rules
    for cr in inv.get("cart_rules") or []:
        active = str(cr.get("active")) == "1"
        expires = _date(cr.get("date_to"))
        code = (cr.get("code") or "").strip() or ml(cr.get("name")) or cr.get("id")
        if active and expires and expires < now:
            h.append({"severity": "Low", "area": "Vouchers", "text": f"The voucher “{code}” is active but expired ({str(cr.get('date_to'))[:10]})."})
        elif active and _num(cr.get("quantity")) == 0:
            h.append({"severity": "Low", "area": "Vouchers", "text": f"The voucher “{code}” is active but has no uses left (quantity = 0)."})
        elif active:
            s.append({"area": "Vouchers", "element": code, "test": f"Apply “{code}” in the cart: right at the minimum and below it, combined with another voucher and on excluded products; check discount, taxes and shipping."})

    # Multistore
    shops = inv.get("shops") or []
    if cfg.get("PS_MULTISHOP_FEATURE_ACTIVE") == "1" or len(shops) > 1:
        h.append({"severity": "Medium", "area": "Multistore", "text": f"Multistore is active ({len(shops) or 'several'} shop(s)): each shop can have its own catalog, prices, carriers and themes. Each one has to be tested."})

    # Catalog (same rule as the other platforms)
    prods = inv.get("products_norm") or []
    hc, _, _ = c.analyze_catalog(prods)
    h += hc
    for p in c.sold_out(prods)[:3]:
        s.append({"area": "Catalog", "element": p.get("title"), "test": "Product out of stock with “deny orders”: it cannot be added to the cart or bought through a direct URL; the button shows sold out."})
    for p in [p for p in prods if "oversell" in c.product_issues(p)][:3]:
        s.append({"area": "Catalog", "element": p.get("title"), "test": "Buy with no stock with “allow orders”: availability notice to the buyer, order status and controlled negative stock."})
    for p in [p for p in prods if p.get("type") == "combinations"][:3]:
        s.append({"area": "Catalog", "element": p.get("title"), "test": "Product with combinations: each combination changes price, image, reference and stock; an out-of-stock or nonexistent combination cannot be added."})

    if inv.get("ps_mode_dev") is True:
        h.append({"severity": "Medium", "area": "Store", "text": "Developer mode is on (_PS_MODE_DEV_ = true): it shows errors and profiling, and it is slower. In production it has to be off."})

    if inv.get("webservice"):
        s += [{"area": "Checkout", "element": "Purchase flow", "test": "Buy as a guest and with an account, with the gateway in test mode; validations of each address field (form-tester) and that subtotal + shipping + taxes − discounts = total in cart, checkout, order and email."},
              {"area": "Emails", "element": "Transactional emails", "test": "With the email-verifier: order confirmation, payment accepted, processing, shipped and password change; unreplaced variables and links."},
              {"area": "Permissions", "element": "Roles", "test": "With the permissions-tester: customer, guest and anonymous on “My account”, other customers' orders and the back office (access through a direct URL)."},
              {"area": "Web performance", "element": "Product pages and listings", "test": "With the web-performance-auditor: home, a category with many products and a product page; measure with and without the cache and CSS/JS combining enabled."}]
    return c.sort_findings(h), s


def tables_and_indicators(inv, base):
    cfg = inv.get("config") or {}
    prods = inv.get("products_norm") or []
    _, rows_cat, n_prob = c.analyze_catalog(prods)
    active_carriers = [t for t in inv.get("carriers") or [] if str(t.get("active")) == "1" and str(t.get("deleted") or "0") == "0"]
    currencies = [m for m in inv.get("currencies") or [] if str(m.get("active")) == "1"]
    languages = [i for i in inv.get("languages") or [] if str(i.get("active")) == "1"]
    yes_no = {"1": "Yes", "0": "No"}
    data = [["URL", base], ["Name", inv.get("name") or "—"],
            ["Version", inv.get("version") or "—"],
            ["Developer mode", {True: "On", False: "Off"}.get(inv.get("ps_mode_dev"), "—")],
            ["Store enabled", yes_no.get(cfg.get("PS_SHOP_ENABLE"), "—")],
            ["Catalog mode", yes_no.get(cfg.get("PS_CATALOG_MODE"), "—")],
            ["HTTPS", yes_no.get(cfg.get("PS_SSL_ENABLED"), "—") + (" (on the whole site)" if cfg.get("PS_SSL_ENABLED_EVERYWHERE") == "1" else "")],
            ["Multistore", yes_no.get(cfg.get("PS_MULTISHOP_FEATURE_ACTIVE"), "Yes" if len(inv.get("shops") or []) > 1 else "—")],
            ["Checkout", {"1": "One page", "0": "5 steps"}.get(cfg.get("PS_ORDER_PROCESS_TYPE"), "—")],
            ["Guest checkout", yes_no.get(cfg.get("PS_GUEST_CHECKOUT_ENABLED"), "—")],
            ["Active languages", ", ".join(i.get("iso_code") or "?" for i in languages) or "—"],
            ["Active currencies", ", ".join(m.get("iso_code") or "?" for m in currencies) or "—"],
            ["Webservice API", "with a read key" if inv.get("webservice") else "no key (public storefront only)"]]
    tables = [c.table("The store", ["Field", "Value"], data)]
    if rows_cat:
        tables.append(c.table("Products with issues", ["Product", "Reference", "Issues"], rows_cat[:150], f"{n_prob} of {len(prods)} reviewed"))
    if inv.get("carriers"):
        tables.append(c.table("Carriers", ["Carrier", "Active", "Free"],
                              [[ml(t.get("name")) or t.get("id"), yes_no.get(str(t.get("active")), "No"), yes_no.get(str(t.get("is_free")), "No")] for t in inv["carriers"]]))
    if inv.get("currencies"):
        tables.append(c.table("Currencies", ["Currency", "ISO", "Rate", "Active"],
                              [[ml(m.get("name")) or m.get("id"), m.get("iso_code"), m.get("conversion_rate"), yes_no.get(str(m.get("active")), "No")] for m in inv["currencies"]]))
    if inv.get("cart_rules"):
        tables.append(c.table("Vouchers (cart rules)", ["Code", "Active", "Expires", "Uses"],
                              [[(cr.get("code") or "").strip() or ml(cr.get("name")) or cr.get("id"), yes_no.get(str(cr.get("active")), "No"),
                                (str(cr.get("date_to"))[:10] if _date(cr.get("date_to")) else "—"), cr.get("quantity")] for cr in inv["cart_rules"]]))
    perf = [[k, cfg.get(k)] for k in ("PS_SMARTY_CACHE", "PS_SMARTY_FORCE_COMPILE", "PS_CCCCSS", "PS_CCCJS", "PS_CACHE_ENABLED", "PS_HTACCESS_CACHE_CONTROL") if cfg.get(k) is not None]
    if perf:
        tables.append(c.table("Web performance (settings)", ["Parameter", "Value"], perf))
    indicators = [{"label": "Products reviewed", "value": len(prods), "tone": "", "detail": "Webservice API" if inv.get("webservice") else "no key"},
                  {"label": "Products with issues", "value": n_prob, "tone": "bad" if n_prob else "ok", "detail": "price, stock, image, taxes"},
                  {"label": "Active carriers", "value": len(active_carriers), "tone": "bad" if (inv.get("carriers") is not None and not active_carriers) else "ok", "detail": f"of {len(inv.get('carriers') or [])}"}]
    return indicators, tables, n_prob


def read_local(path):
    """PrestaShop version and whether developer mode was left on, reading the local installation."""
    base = Path(path)
    info = {"version": None, "ps_mode_dev": None, "errors": {}}
    for rel, rx in (("app/AppKernel.php", r"const VERSION\s*=\s*'([^']+)'"),
                    ("config/settings.inc.php", r"_PS_VERSION_['\"]?\s*,\s*'([^']+)'"),
                    ("install/install_version.php", r"_PS_INSTALL_VERSION_['\"]?\s*,\s*'([^']+)'")):
        try:
            m = re.search(rx, (base / rel).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if m:
            info["version"] = m.group(1)
            break
    for rel in ("config/defines_custom.inc.php", "config/defines.inc.php"):
        try:
            txt = (base / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = re.search(r"_PS_MODE_DEV_['\"]?\s*,\s*(true|false|1|0)", txt, re.I)
        if m:
            info["ps_mode_dev"] = m.group(1).lower() in ("true", "1")
            break
    if info["version"] is None and info["ps_mode_dev"] is None:
        info["errors"]["local"] = f"The PrestaShop installation was not found in {path} (app/AppKernel.php, config/defines.inc.php)."
    return info


def main(argv=None):
    c.prepare_console()
    ap = argparse.ArgumentParser(description="Functional QA survey of a PrestaShop store (read-only).")
    ap.add_argument("--store", help="store URL (or PRESTASHOP_URL in the .env)")
    ap.add_argument("--story", default="")
    ap.add_argument("--product", default="", help="URL of a product page to review (otherwise, the first one in the catalog)")
    ap.add_argument("--max-products", type=int, default=300)
    ap.add_argument("--local", default="", help="path of the local installation to read the version and dev mode (or PRESTASHOP_LOCAL_PATH)")
    ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args(argv)

    env = c.read_env("PRESTASHOP_")
    base = c.normalize_url(args.store or env.get("PRESTASHOP_URL") or "")
    if not base:
        c.abort("Missing the store: pass it with --store https://my-store.example.com or set PRESTASHOP_URL in the .env.")
    c.authorize(base, env)
    key = (env.get("PRESTASHOP_WEBSERVICE_KEY") or "").strip()
    c.confirm(f"You are about to survey the PrestaShop store {base} (read-only{'; with the Webservice API' if key else ''}).", args.confirm)

    inv, errors = {"webservice": bool(key)}, {}
    local = args.local or env.get("PRESTASHOP_LOCAL_PATH") or ""
    if local:
        print(f"[prestashop] Local installation {local} …", file=sys.stderr)
        li = read_local(local)
        inv["version"], inv["ps_mode_dev"] = li["version"], li["ps_mode_dev"]
        errors.update(li["errors"])

    if key:
        print(f"[prestashop] Webservice {base}/api …", file=sys.stderr)
        cfg_rows, err = ps(base, key, "configurations", f"display=full&filter[name]=[{'|'.join(CONFIG_KEYS)}]&limit=200")
        if err:
            errors["configurations"] = err
        inv["config"] = {ml(x.get("name")) or x.get("name"): ml(x.get("value")) for x in _list(cfg_rows, "configurations")}

        for name, resource, params in (("carriers", "carriers", "display=full&limit=200"),
                                       ("zones", "zones", "display=full"),
                                       ("currencies", "currencies", "display=full"),
                                       ("languages", "languages", "display=full"),
                                       ("cart_rules", "cart_rules", "display=full&limit=200"),
                                       ("shops", "shops", "display=full")):
            print(f"[prestashop] Webservice · {name} …", file=sys.stderr)
            d, err = ps(base, key, resource, params)
            inv[name] = _list(d, resource)
            if err:
                errors[name] = err

        print("[prestashop] Webservice · stock_availables …", file=sys.stderr)
        st, err = ps(base, key, "stock_availables", f"display=full&limit={args.max_products * 3}")
        if err:
            errors["stock_availables"] = err
        stock = stock_map(_list(st, "stock_availables"))

        print("[prestashop] Webservice · products …", file=sys.stderr)
        pr, err = ps(base, key, "products", f"display=full&filter[active]=1&limit={args.max_products}")
        if err:
            errors["products"] = err
        inv["products_norm"] = [normalize_product(p, stock, inv.get("config") or {}, base) for p in _list(pr, "products")]
        cfg_name = (inv.get("config") or {}).get("PS_SHOP_NAME")
    else:
        inv["config"], inv["products_norm"], cfg_name = {}, [], None

    # Public storefront
    product_url = args.product or next((p.get("url") for p in inv["products_norm"] if p.get("url")), "")
    print(f"[prestashop] Storefront {base} …", file=sys.stderr)
    checks, storefront_findings, home = c.check_storefront(base, ERROR_PATTERNS, [product_url] if product_url else [])
    ch_p, h_p = c.check_product(product_url)
    is_ps = bool(re.search(r'name=["\']generator["\'][^>]*PrestaShop|var\s+prestashop\s*=|/modules/ps_', home.text or "", re.I))
    inv["name"] = cfg_name or re.sub(r"^https?://", "", base)
    checks += ch_p + [{"check": "PrestaShop detected", "status": "ok" if is_ps else "warning",
                       "detail": "yes (generator/front-office variables)" if is_ps else "no PrestaShop signals were recognized on the home page"},
                      {"check": "Webservice API", "status": "ok" if key and not errors.get("products") else ("warning" if key else "info"),
                       "detail": f'{len(inv["products_norm"])} product(s)' if key else "no key (public storefront only)"}]

    findings, suggestions = findings_and_suggestions(inv)
    findings = c.sort_findings(storefront_findings + h_p + findings)
    indicators, tables, n_prob = tables_and_indicators(inv, base)
    data = {"story": args.story or None, "platform": "prestashop",
            "store": {"url": base, "name": inv.get("name"),
                      "version": f'PrestaShop {inv.get("version")}' if inv.get("version") else "PrestaShop",
                      "environment": "—"},
            "storefront": {"checks": checks}, "inventory": {k: v for k, v in inv.items() if k != "products_norm"},
            "indicators": indicators, "tables": tables, "findings": findings, "suggestions": suggestions,
            "summary": {"products": len(inv["products_norm"]), "products_with_issues": n_prob}, "errors": errors}
    c.save("prestashop", data, c.output_folder("prestashop", args.story, base))
    return 0


if __name__ == "__main__":
    sys.exit(main())
