#!/usr/bin/env python3
"""
Functional QA survey of an AUTHORIZED WordPress / WooCommerce site (read-only).

Usage (from the repo root):
    python tools/ecommerce/wordpress.py --site https://my-store-qa.example.com [--story US-001]
        [--product https://.../product/t-shirt/] [--max-products 300] [--wp-cli] [--confirm]

What it does:
- Checks that the site is in ECOMMERCE_AUTHORIZED_URLS in the .env.
- Public storefront: common checks (home and key pages, robots, sitemap, 404, visible PHP errors or the
  WordPress "critical error"), which modules the REST API exposes (/wp-json: WooCommerce, SEO,
  forms, page builders) and the public catalog from the WooCommerce Store API.
- WooCommerce REST API (optional, with WOOCOMMERCE_CONSUMER_KEY/SECRET of a READ key): system
  status (versions, database pending update, cron, outgoing calls, plugins and their latest
  version, overridden and outdated theme templates, WooCommerce pages), payment gateways and
  whether they are in test mode, shipping zones and methods, coupons, webhooks, general settings and products
  with stock and backorders.
- WP-CLI (optional, --wp-cli with WORDPRESS_LOCAL_PATH or WORDPRESS_WP_CLI): WordPress, plugin and
  theme updates, and overdue cron events.
- Computes findings and test suggestions and leaves in output/wordpress/<story or host>/: wordpress.json and
  wordpress-report.html (the previous run moves to history/).

GET only (and read-only WP-CLI commands). It does not create orders, customers or products or change settings. The
site's security is not reviewed here (security-analyst, web-pentester).
"""
import argparse
import datetime
import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as c  # noqa: E402

# The Spanish alternatives are WordPress's own localized messages (sites in Spanish).
ERROR_PATTERNS = [("PHP error", r"(?:Fatal error|Parse error|Warning|Notice|Deprecated):\s.{0,200}? on line \d+"),
                  ("WordPress critical error", r"There has been a critical error on this website|Ha habido un error crítico en esta web"),
                  ("No database connection", r"Error establishing a database connection|Error al establecer una conexión con la base de datos")]
NAMESPACES = {"wc/v3": "WooCommerce", "wc/store/v1": "WooCommerce (Store API)", "yoast/v1": "Yoast SEO", "rankmath/v1": "Rank Math",
              "contact-form-7/v1": "Contact Form 7", "gf/v2": "Gravity Forms", "elementor/v1": "Elementor", "jetpack/v4": "Jetpack",
              "wpml/v1": "WPML", "pll/v1": "Polylang", "wc-admin": "WooCommerce Admin", "wc-analytics": "WooCommerce Analytics",
              "mailpoet/v1": "MailPoet", "litespeed/v1": "LiteSpeed Cache", "wp-rocket/v1": "WP Rocket"}
TEST_KEYS = ("testmode", "test_mode", "sandbox", "sandbox_mode", "environment", "mode")


def wc(base, ck, cs, path):
    """GET to the WooCommerce REST API with a read key. (data, error)."""
    r = c.http(f"{base}/wp-json/wc/v3/{path}", headers={"Accept": "application/json"}, user=ck, password=cs, timeout=40)
    if r.error:
        return None, r.error
    if r.status in (401, 403):
        return None, f"HTTP {r.status}: the key is invalid or does not have read permission"
    if not r.ok:
        return None, f"HTTP {r.status}: {(r.text or '')[:160]}"
    d = r.json()
    return (d, None) if d is not None else (None, "non-JSON response")


def store_products(base, maximum):
    out, page = [], 1
    while len(out) < maximum and page <= 20:
        r = c.http(f"{base}/wp-json/wc/store/v1/products?per_page=100&page={page}", headers={"Accept": "application/json"}, timeout=30)
        d = r.json() if r.ok else None
        if not isinstance(d, list) or not d:
            break
        out += d
        page += 1
    return out[:maximum]


def products_v3(base, ck, cs, maximum):
    out, page, err = [], 1, None
    while len(out) < maximum and page <= 20:
        d, err = wc(base, ck, cs, f"products?per_page=100&page={page}&status=publish")
        if not isinstance(d, list) or not d:
            break
        out += d
        page += 1
    return out[:maximum], err


def _num(x):
    try:
        return float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


def normalize_store(p):
    pr = p.get("prices") or {}
    div = 10 ** int(pr.get("currency_minor_unit") or 0)
    price = _num(pr.get("price"))
    regular = _num(pr.get("regular_price"))
    return {"title": p.get("name"), "ref": p.get("slug"), "active": True, "url": p.get("permalink"),
            "prices": [price / div if price is not None else None],
            "compare_at": [regular / div if regular is not None and p.get("on_sale") else None],
            "image": bool(p.get("images")), "stock": None, "tracks_stock": None, "keeps_selling": None,
            "variants": len(p.get("variations") or []) or 1, "no_sku": 0, "seo": None, "published": True,
            "available": p.get("is_in_stock"), "type": p.get("type")}


def normalize_v3(p, calculates_taxes):
    price, regular = _num(p.get("price")), _num(p.get("regular_price"))
    return {"title": p.get("name"), "ref": p.get("slug"), "active": p.get("status") == "publish" and p.get("purchasable", True),
            "url": p.get("permalink"), "prices": [price] if p.get("type") != "variable" else [],
            "compare_at": [regular if p.get("on_sale") and regular and price and regular <= price else None],
            "image": bool(p.get("images")), "stock": p.get("stock_quantity"), "tracks_stock": bool(p.get("manage_stock")),
            "keeps_selling": p.get("backorders") in ("yes", "notify"), "variants": len(p.get("variations") or []) or 1,
            "no_sku": 0 if (p.get("sku") or "").strip() else 1,
            "tax": (p.get("tax_status") != "none") if calculates_taxes else None, "seo": None, "published": True,
            "available": p.get("stock_status") != "outofstock", "type": p.get("type")}


def _version(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v or ""))[:4])


def in_test_mode(gw):
    """True / False / None (unknown) according to the gateway settings."""
    settings = gw.get("settings") or {}
    for key in TEST_KEYS:
        if key in settings:
            v = str((settings[key] or {}).get("value", "")).lower()
            if v in ("yes", "1", "true", "sandbox", "test", "staging"):
                return True
            if v in ("no", "0", "false", "live", "production", "produccion"):
                return False
    return None


def wp_cli(cli_cmd, path, args):
    cmd = shlex.split(cli_cmd) + list(args) + (["--path=" + path] if path else []) + ["--skip-themes", "--quiet"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    except (OSError, subprocess.TimeoutExpired) as ex:
        return None, str(ex)[:200]
    if p.returncode != 0:
        return None, (p.stderr or p.stdout or "WP-CLI error").strip()[:300]
    try:
        return json.loads(p.stdout or "null"), None
    except ValueError:
        return None, "non-JSON output"


def findings_and_suggestions(inv, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    h, s = [], []
    ss = inv.get("system_status") or {}
    env = ss.get("environment") or {}
    db = ss.get("database") or {}
    if not inv.get("woocommerce"):
        h.append({"severity": "Low", "area": "Site", "text": "WooCommerce was not detected in the REST API: it was surveyed as a WordPress site (no store)."})
    if env.get("version") and db.get("wc_database_version") and _version(env["version"])[:2] != _version(db["wc_database_version"])[:2]:
        h.append({"severity": "High", "area": "WooCommerce", "text": f'The WooCommerce database is at {db["wc_database_version"]} and the plugin at {env["version"]}: the database update still needs to run (orders and stock may fail).'})
    if env.get("wp_cron") is False:
        h.append({"severity": "Medium", "area": "Site", "text": "WP-Cron is disabled: scheduled sales, cancellation of unpaid orders and deferred emails depend on a server cron. Confirm that it exists."})
    if env.get("remote_post_successful") is False:
        h.append({"severity": "High", "area": "Integrations", "text": "The site cannot make outgoing calls (remote_post): gateways, webhooks and payment notifications may fail."})
    if env.get("php_version") and _version(env["php_version"]) < (8, 1):
        h.append({"severity": "Low", "area": "Site", "text": f'PHP {env["php_version"]}: several current plugin versions require 8.1 or later.'})
    if env.get("default_timezone") and env["default_timezone"] != "UTC":
        h.append({"severity": "Low", "area": "Site", "text": f'The default PHP time zone is {env["default_timezone"]} and WooCommerce expects UTC: review order and coupon dates.'})

    old = [p for p in ss.get("active_plugins") or [] if p.get("version_latest") and _version(p.get("version_latest")) > _version(p.get("version"))]
    old += [p for p in inv.get("cli_plugins") or [] if p.get("update") == "available" and p.get("status") in ("active", "active-network")
            and not any((x.get("plugin") or "").split("/")[0] == p.get("name") for x in old)]
    if old:
        names = [f'{p.get("name")} {p.get("version")}' for p in old]
        h.append({"severity": "Medium", "area": "Plugins", "text": f'{len(old)} active plugin(s) with an update available: {", ".join(names[:6])}{"…" if len(names) > 6 else ""}. Update on staging and run the purchase flow regression.'})
        for p in old[:5]:
            s.append({"area": "Plugins", "element": p.get("name"), "test": f'After updating {p.get("name")} on staging: go through catalog, cart, checkout and My account, and review the browser console.'})
    inactive = ss.get("inactive_plugins") or []
    if len(inactive) > 5:
        h.append({"severity": "Low", "area": "Plugins", "text": f"{len(inactive)} installed and inactive plugins: consider deleting the ones not in use."})
    if inv.get("cli_core_update"):
        h.append({"severity": "Medium", "area": "Site", "text": f'A WordPress update is available ({", ".join(u.get("version", "?") for u in inv["cli_core_update"][:2])}).'})

    theme = ss.get("theme") or {}
    if theme.get("has_outdated_templates"):
        outdated = [o for o in theme.get("overrides") or [] if o.get("version") and o.get("core_version") and o["version"] != o["core_version"]]
        h.append({"severity": "High", "area": "Theme", "text": f'The theme {theme.get("name")} overrides {len(outdated) or "several"} outdated WooCommerce template(s): the cart, the checkout or the emails may look or behave wrong.'})
        for o in outdated[:5]:
            s.append({"area": "Theme", "element": o.get("file"), "test": f'Review the screen that uses {o.get("file")} (template {o.get("version")}, WooCommerce expects {o.get("core_version")}): texts, fields and buttons.'})
    if inv.get("woocommerce") and theme and theme.get("has_woocommerce_support") is False and not theme.get("is_block_theme"):
        h.append({"severity": "Medium", "area": "Theme", "text": f'The theme {theme.get("name")} does not declare WooCommerce support.'})

    for pg in ss.get("pages") or []:
        name = pg.get("page_name") or "?"
        if pg.get("page_set") is False or pg.get("page_exists") is False:
            h.append({"severity": "High", "area": "WooCommerce", "text": f'The WooCommerce page "{name}" is not configured or does not exist.'})
        elif pg.get("page_visible") is False:
            h.append({"severity": "High", "area": "WooCommerce", "text": f'The page "{name}" exists but is not published.'})
        elif pg.get("shortcode_required") and not pg.get("shortcode_present") and not pg.get("block_present"):
            h.append({"severity": "High", "area": "WooCommerce", "text": f'The page "{name}" is missing the WooCommerce shortcode or block: it looks empty.'})
        if pg.get("block_present"):
            s.append({"area": "Checkout", "element": name, "test": f'"{name}" uses blocks: check that the payment, shipping and extra field plugins work with the block checkout (not all of them are compatible).'})

    enabled = [g for g in inv.get("gateways") or [] if g.get("enabled")]
    if inv.get("woocommerce") and inv.get("gateways") is not None and not enabled:
        h.append({"severity": "High", "area": "Payments", "text": "No payment gateway is enabled: a purchase cannot be completed."})
    for g in enabled:
        test = in_test_mode(g)
        if test is False:
            h.append({"severity": "High", "area": "Payments", "text": f'The gateway "{g.get("title") or g.get("id")}" is enabled in LIVE mode: in QA no payments are made with it until it is switched to test mode.'})
        s.append({"area": "Payments", "element": g.get("title") or g.get("id"),
                  "test": f'Pay with "{g.get("title") or g.get("id")}" {"in test mode " if test else "(first confirm it is in test mode) "}with an approved, a declined and a 3-D Secure card; check order status, stock, order note and email. Go back from the gateway and repeat the payment.'})

    for z in inv.get("zones") or []:
        methods = [m for m in z.get("methods") or [] if m.get("enabled")]
        if not methods:
            h.append({"severity": "Medium", "area": "Shipping", "text": f'The shipping zone "{z.get("name")}" has no enabled methods: those addresses cannot buy with shipping.'})
        for m in methods[:4]:
            s.append({"area": "Shipping", "element": f'{z.get("name")} · {m.get("title")}', "test": f'Checkout with an address in the "{z.get("name")}" zone choosing "{m.get("title")}": cost, free-shipping minimum, changing the address to another zone and recalculating the total.'})

    for cu in inv.get("coupons") or []:
        expires = cu.get("date_expires_gmt") or cu.get("date_expires")
        expired = False
        if expires:
            try:
                expired = datetime.datetime.fromisoformat(expires.replace("Z", "")).replace(tzinfo=datetime.timezone.utc) < now
            except ValueError:
                pass
        if expired:
            h.append({"severity": "Low", "area": "Coupons", "text": f'The coupon "{cu.get("code")}" expired ({expires[:10]}) and is still published.'})
        elif cu.get("usage_limit") and (cu.get("usage_count") or 0) >= cu["usage_limit"]:
            h.append({"severity": "Low", "area": "Coupons", "text": f'The coupon "{cu.get("code")}" used up its uses ({cu.get("usage_count")} of {cu.get("usage_limit")}).'})
        else:
            s.append({"area": "Coupons", "element": cu.get("code"), "test": f'Apply "{cu.get("code")}" valid, in uppercase, with spaces, on a cart below the minimum{" (" + str(cu.get("minimum_amount")) + ")" if _num(cu.get("minimum_amount")) else ""}, with excluded products and together with another coupon; check discount, taxes and shipping.'})

    for w in inv.get("webhooks") or []:
        if w.get("status") in ("disabled", "paused"):
            h.append({"severity": "High", "area": "Integrations", "text": f'The webhook "{w.get("name")}" ({w.get("topic")}) is {w.get("status")}: WooCommerce disables them after several delivery failures.'})
        elif w.get("status") == "active":
            s.append({"area": "Integrations", "element": w.get("topic"), "test": f'Trigger {w.get("topic")} and check that the receiver processes it only once and validates the X-WC-Webhook-Signature signature.'})

    overdue = []
    for ev in inv.get("cli_cron") or []:
        try:
            nxt = datetime.datetime.fromisoformat(str(ev.get("next_run_gmt")).replace(" ", "T")).replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
        if (now - nxt).total_seconds() > 3600:
            overdue.append(ev.get("hook"))
    if overdue:
        h.append({"severity": "Medium", "area": "Site", "text": f'{len(overdue)} cron event(s) overdue by more than an hour: {", ".join(overdue[:5])}. Cron is not running.'})
    failed = inv.get("cli_failed_actions")
    if isinstance(failed, int) and failed > 0:
        h.append({"severity": "Medium", "area": "WooCommerce", "text": f"{failed} failed scheduled action(s) in Action Scheduler: deferred emails, webhooks, renewals or reports that did not run (WooCommerce → Status → Scheduled Actions)."})
    auto = [p.get("name") for p in inv.get("cli_plugins") or [] if p.get("auto_update") == "on" and p.get("status") in ("active", "active-network")]
    if auto:
        h.append({"severity": "Low", "area": "Plugins", "text": f'{len(auto)} active plugin(s) with automatic updates ({", ".join(auto[:6])}): in production they update without going through staging.'})

    prods = inv.get("products_norm") or []
    hc, _, _ = c.analyze_catalog(prods)
    h += hc
    for p in c.sold_out(prods)[:3]:
        s.append({"area": "Catalog", "element": p.get("title"), "test": "Product out of stock without backorders: the buy button does not show and it cannot be added through ?add-to-cart=ID."})
    for p in [p for p in prods if "oversell" in c.product_issues(p)][:3]:
        s.append({"area": "Catalog", "element": p.get("title"), "test": "Buy with no stock and backorders allowed: notice to the buyer, order status and controlled negative stock."})
    for p in [p for p in prods if p.get("type") == "variable"][:3]:
        s.append({"area": "Catalog", "element": p.get("title"), "test": "Variable product: each combination changes price, image and stock; an out-of-stock or nonexistent combination cannot be added."})

    if inv.get("woocommerce"):
        s += [{"area": "Checkout", "element": "Guest and account", "test": "Buy as a guest, creating an account at checkout and while logged in; validations of each field (form-tester)."},
              {"area": "Checkout", "element": "Cart", "test": "Quantities 0, 1, maximum stock and more; remove products; cart with an expired session; mini-cart and cart page with the same total."},
              {"area": "Emails", "element": "WooCommerce emails", "test": "With the email-verifier: new order (store), processing, completed, refunded, customer note and password reset."},
              {"area": "Permissions", "element": "Roles", "test": "With the permissions-tester: customer, shop manager (shop_manager) and anonymous on My account, other customers' orders and the admin panel."}]
    return c.sort_findings(h), s


def tables_and_indicators(inv, base):
    ss = inv.get("system_status") or {}
    env = ss.get("environment") or {}
    theme = ss.get("theme") or {}
    prods = inv.get("products_norm") or []
    _, rows_cat, n_prob = c.analyze_catalog(prods)
    settings = {a.get("id"): a.get("value") for a in inv.get("settings") or []}
    data = [["URL", base], ["Name", inv.get("name") or "—"], ["WordPress", env.get("wp_version") or inv.get("public_version") or "—"],
            ["WooCommerce", env.get("version") or ("detected" if inv.get("woocommerce") else "no")],
            ["PHP", env.get("php_version") or "—"], ["Multisite", {True: "Yes", False: "No"}.get(env.get("wp_multisite"), "—")],
            ["Theme", f'{theme.get("name") or "—"} {theme.get("version") or ""}'.strip()],
            ["Order storage", {True: "HPOS (dedicated tables)", False: "WordPress posts"}.get((ss.get("settings") or {}).get("HPOS_enabled"), "—")
             + (" with sync" if (ss.get("settings") or {}).get("HPOS_sync_enabled") else "")],
            ["Currency", settings.get("woocommerce_currency") or "—"], ["Calculates taxes", {"yes": "Yes", "no": "No"}.get(settings.get("woocommerce_calc_taxes"), "—")],
            ["Modules in the REST API", ", ".join(inv.get("modules") or []) or "—"],
            ["WooCommerce REST API", "with a read key" if inv.get("system_status") else "no key (public catalog only)"]]
    tables = [c.table("The site", ["Field", "Value"], data)]
    if rows_cat:
        tables.append(c.table("Products with issues", ["Product", "Slug", "Issues"], rows_cat[:150], f"{n_prob} of {len(prods)} reviewed"))
    plugins = ss.get("active_plugins") or []
    if plugins:
        tables.append(c.table("Active plugins", ["Plugin", "Version", "Latest", "Status"],
                              [[p.get("name"), p.get("version"), p.get("version_latest") or "—",
                                "Outdated" if p.get("version_latest") and _version(p["version_latest"]) > _version(p.get("version")) else "Up to date"] for p in plugins]))
    elif inv.get("cli_plugins"):
        tables.append(c.table("Plugins (WP-CLI)", ["Plugin", "Status", "Version", "Update"],
                              [[p.get("name"), p.get("status"), p.get("version"), p.get("update_version") or ("available" if p.get("update") == "available" else "—")] for p in inv["cli_plugins"]]))
    over = [o for o in theme.get("overrides") or [] if o.get("version") and o.get("core_version") and o["version"] != o["core_version"]]
    if over:
        tables.append(c.table("Outdated WooCommerce templates", ["File", "Theme version", "WooCommerce version"],
                              [[o.get("file"), o.get("version"), o.get("core_version")] for o in over]))
    if ss.get("pages"):
        tables.append(c.table("WooCommerce pages", ["Page", "Configured", "Published", "Content"],
                              [[pg.get("page_name"), "Yes" if pg.get("page_set") and pg.get("page_exists") else "No", "Yes" if pg.get("page_visible") else "No",
                                "Blocks" if pg.get("block_present") else ("Shortcode" if pg.get("shortcode_present") else "—")] for pg in ss["pages"]]))
    if inv.get("gateways"):
        tables.append(c.table("Payment gateways", ["Gateway", "Enabled", "Mode"],
                              [[g.get("title") or g.get("id"), "Yes" if g.get("enabled") else "No",
                                {True: "Test", False: "LIVE"}.get(in_test_mode(g), "Unknown")] for g in inv["gateways"]]))
    if inv.get("zones"):
        tables.append(c.table("Shipping zones", ["Zone", "Enabled methods"],
                              [[z.get("name"), ", ".join(m.get("title") for m in z.get("methods") or [] if m.get("enabled")) or "none"] for z in inv["zones"]]))
    if inv.get("coupons"):
        tables.append(c.table("Coupons", ["Code", "Type", "Amount", "Expires", "Uses"],
                              [[cu.get("code"), cu.get("discount_type"), cu.get("amount"), (cu.get("date_expires") or "—")[:10],
                                f'{cu.get("usage_count") or 0}/{cu.get("usage_limit") or "∞"}'] for cu in inv["coupons"]]))
    if inv.get("webhooks"):
        tables.append(c.table("Webhooks", ["Name", "Event", "Status", "Destination"],
                              [[w.get("name"), w.get("topic"), w.get("status"), w.get("delivery_url")] for w in inv["webhooks"]]))
    n_old = sum(1 for p in plugins if p.get("version_latest") and _version(p["version_latest"]) > _version(p.get("version"))) \
        or sum(1 for p in inv.get("cli_plugins") or [] if p.get("update") == "available")
    indicators = [{"label": "Products reviewed", "value": len(prods), "tone": "", "detail": "REST API" if inv.get("system_status") else "public Store API"},
                  {"label": "Products with issues", "value": n_prob, "tone": "bad" if n_prob else "ok", "detail": "price, stock, image, taxes"},
                  {"label": "Outdated plugins", "value": n_old, "tone": "warn" if n_old else "ok", "detail": f"of {len(plugins or inv.get('cli_plugins') or [])}"}]
    if theme:
        indicators.append({"label": "Outdated templates", "value": len(over), "tone": "bad" if over else "ok", "detail": "overridden by the theme"})
    return indicators, tables, n_prob


def main(argv=None):
    c.prepare_console()
    ap = argparse.ArgumentParser(description="Functional QA survey of a WordPress / WooCommerce site (read-only).")
    ap.add_argument("--site", help="site URL (or WORDPRESS_URL in the .env)")
    ap.add_argument("--story", default="")
    ap.add_argument("--product", default="", help="URL of a product page to review (otherwise, the first one in the catalog)")
    ap.add_argument("--max-products", type=int, default=300)
    ap.add_argument("--wp-cli", action="store_true", help="check updates and cron with WP-CLI (WORDPRESS_LOCAL_PATH or WORDPRESS_WP_CLI)")
    ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args(argv)

    env = c.read_env("WORDPRESS_", "WOOCOMMERCE_")
    base = c.normalize_url(args.site or env.get("WORDPRESS_URL") or "")
    if not base:
        c.abort("Missing the site: pass it with --site https://my-store.example.com or set WORDPRESS_URL in the .env.")
    c.authorize(base, env)
    ck, cs = (env.get("WOOCOMMERCE_CONSUMER_KEY") or "").strip(), (env.get("WOOCOMMERCE_CONSUMER_SECRET") or "").strip()
    c.confirm(f"You are about to survey the WordPress site {base} (read-only{'; with the WooCommerce REST API' if ck and cs else ''}).", args.confirm)

    inv, errors = {}, {}
    print(f"[wordpress] REST API {base}/wp-json …", file=sys.stderr)
    root = c.http(base + "/wp-json/", headers={"Accept": "application/json"}, timeout=25)
    info = root.json() if root.ok else None
    if not isinstance(info, dict):
        errors["wp-json"] = f"HTTP {root.status or root.error}: the REST API is not responding (plain permalinks or disabled?)"
        info = {}
    ns = info.get("namespaces") or []
    inv["name"] = info.get("name")
    inv["modules"] = sorted({v for k, v in NAMESPACES.items() if any(n == k or n.startswith(k + "/") for n in ns)})
    inv["woocommerce"] = any(n.startswith("wc/") for n in ns)
    feed = c.http(base + "/feed/", timeout=15)
    m = re.search(r"<generator>https?://wordpress\.org/\?v=([\d.]+)</generator>", feed.text or "")
    inv["public_version"] = m.group(1) if m else None

    public = store_products(base, args.max_products) if inv["woocommerce"] else []
    if ck and cs and inv["woocommerce"]:
        for key, path in (("system_status", "system_status"), ("gateways", "payment_gateways"), ("coupons", "coupons?per_page=100"),
                          ("webhooks", "webhooks?per_page=100"), ("settings", "settings/general")):
            print(f"[wordpress] WooCommerce · {key} …", file=sys.stderr)
            d, err = wc(base, ck, cs, path)
            inv[key] = d
            if err:
                errors[key] = err
        zones, err = wc(base, ck, cs, "shipping/zones")
        if err:
            errors["zones"] = err
        inv["zones"] = []
        for z in zones or []:
            methods, err = wc(base, ck, cs, f'shipping/zones/{int(z.get("id", 0))}/methods')
            inv["zones"].append({"id": z.get("id"), "name": z.get("name"), "methods": methods or []})
        print("[wordpress] WooCommerce · products …", file=sys.stderr)
        v3, err = products_v3(base, ck, cs, args.max_products)
        if err:
            errors["products"] = err
        calculates = {a.get("id"): a.get("value") for a in inv.get("settings") or []}.get("woocommerce_calc_taxes") == "yes"
        inv["products_norm"] = [normalize_v3(p, calculates) for p in v3] if v3 else [normalize_store(p) for p in public]
    else:
        inv["products_norm"] = [normalize_store(p) for p in public]

    if args.wp_cli:
        cli = env.get("WORDPRESS_WP_CLI") or ("wp" if shutil.which("wp") else "")
        path = env.get("WORDPRESS_LOCAL_PATH") or ""
        if not cli:
            errors["wp-cli"] = "WP-CLI (https://wp-cli.org) was not found, and WORDPRESS_WP_CLI is not in the .env."
        else:
            print("[wordpress] WP-CLI …", file=sys.stderr)
            for key, cmd in (("cli_plugins", ["plugin", "list", "--format=json", "--fields=name,status,version,update,update_version,auto_update"]),
                             ("cli_core_update", ["core", "check-update", "--format=json"]),
                             ("cli_cron", ["cron", "event", "list", "--format=json", "--fields=hook,next_run_gmt"]),
                             ("cli_failed_actions", ["action-scheduler", "action", "list", "--status=failed", "--format=count"])):
                d, err = wp_cli(cli, path, cmd)
                inv[key] = d or []
                if err:
                    errors[key] = err

    product_url = args.product or next((p.get("url") for p in inv["products_norm"] if p.get("url")), "")
    pages = [product_url] + [f'{base}/?page_id={int(pg["page_id"])}' for pg in (inv.get("system_status") or {}).get("pages") or []
                             if str(pg.get("page_id") or "").isdigit() and int(pg["page_id"]) > 0][:5]
    print(f"[wordpress] Storefront {base} …", file=sys.stderr)
    checks, storefront_findings, _ = c.check_storefront(base, ERROR_PATTERNS, pages + [f"{base}/?s=a"])
    ch_p, h_p = c.check_product(product_url)
    checks += ch_p + [{"check": "REST API (/wp-json)", "status": "ok" if not errors.get("wp-json") else "warning", "detail": f'{len(ns)} namespace(s)'},
                      {"check": "Public catalog (Store API)", "status": "ok" if public else ("warning" if inv["woocommerce"] else "info"),
                       "detail": f"{len(public)} product(s)" if public else ("no products" if inv["woocommerce"] else "no WooCommerce")}]

    findings, suggestions = findings_and_suggestions(inv)
    findings = c.sort_findings(storefront_findings + h_p + findings)
    indicators, tables, n_prob = tables_and_indicators(inv, base)
    envr = (inv.get("system_status") or {}).get("environment") or {}
    data = {"story": args.story or None, "platform": "wordpress",
            "store": {"url": base, "name": inv.get("name") or re.sub(r"^https?://", "", base),
                      "version": f'WordPress {envr.get("wp_version") or inv.get("public_version") or "?"}'
                                 + (f' · WooCommerce {envr["version"]}' if envr.get("version") else ""),
                      "environment": "—"},
            "storefront": {"checks": checks}, "inventory": {k: v for k, v in inv.items() if k != "products_norm"},
            "indicators": indicators, "tables": tables, "findings": findings, "suggestions": suggestions,
            "summary": {"products": len(inv["products_norm"]), "products_with_issues": n_prob}, "errors": errors}
    c.save("wordpress", data, c.output_folder("wordpress", args.story, base))
    return 0


if __name__ == "__main__":
    sys.exit(main())
