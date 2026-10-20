#!/usr/bin/env python3
"""
QA survey of an AUTHORIZED Shopify store (read-only).

Usage (from the repo root):
    python tools/ecommerce/shopify.py --store https://my-store.myshopify.com [--story US-001]
        [--product https://.../products/t-shirt] [--max-products 250] [--theme-check] [--confirm]

What it does:
- Checks that the storefront is in ECOMMERCE_AUTHORIZED_URLS in the .env.
- Public storefront (no credentials): common checks (key pages, robots, sitemap, 404), whether the store is password protected, the published theme (Shopify.theme),
  visible Liquid errors and missing translations, the legal policies (refund, privacy,
  terms, shipping), the public catalog (/products.json), the cart (/cart.js) and a product page.
- Admin API GraphQL (optional, with SHOPIFY_ADMIN_TOKEN from a custom app with READ scopes):
  the store (plan, whether it is a development store, currencies, taxes), themes, products with variants and stock,
  locations, markets, webhooks, discount codes, shipping profiles and the token's scopes.
  Queries only: any "mutation" is rejected before it is sent.
- Theme Check (optional, --theme-check): runs `shopify theme check` on the theme code
  (SHOPIFY_THEME_PATH) with the Shopify CLI.
- Computes findings and test suggestions and leaves in output/shopify/<story or host>/: shopify.json and
  shopify-report.html (the previous run moves to history/).

It does not create orders, customers, products or discounts; it does not install apps or change the theme.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as c  # noqa: E402

API_VERSION = "2026-07"
ERROR_PATTERNS = [("Liquid error", r"Liquid (?:syntax )?error"), ("Missing translation", r"[Tt]ranslation missing:"),
                  ("Liquid error", r"Could not find asset snippets/")]
POLICIES = {"refund-policy": "refund", "privacy-policy": "privacy", "terms-of-service": "terms of service",
            "shipping-policy": "shipping"}
DANGEROUS_SCOPES = re.compile(r"^write_")

# key: list of alternatives (if the first fails because of the API version's schema, the next one is tried)
QUERIES = {
    "store": ["""{ shop { name myshopifyDomain primaryDomain { url host sslEnabled } currencyCode enabledPresentmentCurrencies
                 ianaTimezone weightUnit taxesIncluded taxShipping checkoutApiSupported setupRequired
                 plan { partnerDevelopment shopifyPlus publicDisplayName } shopPolicies { type url } } }""",
              """{ shop { name myshopifyDomain primaryDomain { url host sslEnabled } currencyCode enabledPresentmentCurrencies
                 ianaTimezone taxesIncluded checkoutApiSupported plan { partnerDevelopment shopifyPlus displayName } } }"""],
    "themes": ["{ themes(first: 30) { nodes { id name role updatedAt } } }"],
    "locations": ["{ locations(first: 30) { nodes { name isActive fulfillsOnlineOrders } } }"],
    "markets": ["{ markets(first: 30) { nodes { name handle status type } } }",
                "{ markets(first: 30) { nodes { name handle enabled primary } } }"],
    "webhooks": ["{ webhookSubscriptions(first: 100) { nodes { topic uri } } }",
                 "{ webhookSubscriptions(first: 100) { nodes { topic endpoint { __typename ... on WebhookHttpEndpoint { callbackUrl } } } } }"],
    "discounts": ["""{ codeDiscountNodes(first: 100) { nodes { codeDiscount { __typename
                     ... on DiscountCodeBasic { title status startsAt endsAt usageLimit appliesOncePerCustomer }
                     ... on DiscountCodeBxgy { title status startsAt endsAt usageLimit }
                     ... on DiscountCodeFreeShipping { title status startsAt endsAt usageLimit } } } } }"""],
    "shipping": ["{ deliveryProfiles(first: 20) { nodes { name default activeMethodDefinitionsCount zoneCountryCount } } }",
                 "{ deliveryProfiles(first: 20) { nodes { name default } } }"],
    "scopes": ["{ currentAppInstallation { accessScopes { handle } } }"],
}
PRODUCTS_QUERY = """query($cursor: String) { products(first: 100, after: $cursor) { pageInfo { hasNextPage endCursor }
  nodes { title handle status totalInventory tracksInventory onlineStoreUrl featuredMedia { id } seo { description }
          variants(first: 50) { nodes { sku price compareAtPrice inventoryQuantity inventoryPolicy } } } } }"""


def graphql(domain, token, version, query, variables=None, attempts=3):
    """(data, error). Queries only: a mutation is not sent."""
    if re.search(r"\bmutation\b", query, re.I):
        raise ValueError("read-only queries only: mutations are not sent")
    url = f"https://{domain}/admin/api/{version}/graphql.json"
    body = json.dumps({"query": query, "variables": variables or {}})
    for i in range(attempts):
        r = c.http(url, "POST", {"Content-Type": "application/json", "Accept": "application/json", "X-Shopify-Access-Token": token}, body, timeout=40)
        if r.error:
            return None, r.error
        d = r.json() or {}
        errors = d.get("errors")
        if r.status == 429 or (isinstance(errors, list) and any((e.get("extensions") or {}).get("code") == "THROTTLED" for e in errors)):
            time.sleep(2 * (i + 1))
            continue
        if r.status in (401, 403):
            return None, f"HTTP {r.status}: the token is invalid or lacks the read scope"
        if errors:
            msg = errors if isinstance(errors, str) else "; ".join(str(e.get("message")) for e in errors)
            return d.get("data"), msg[:300]
        return d.get("data"), None
    return None, "the API answered THROTTLED several times (query limit)"


def query_first(domain, token, version, alternatives):
    err = None
    for q in alternatives:
        data, err = graphql(domain, token, version, q)
        if data and not err:
            return data, None
    return None, err


def admin_products(domain, token, version, maximum):
    out, cursor, err = [], None, None
    while len(out) < maximum:
        data, err = graphql(domain, token, version, PRODUCTS_QUERY, {"cursor": cursor})
        if not data or not data.get("products"):
            break
        prods = data["products"]
        out += prods.get("nodes") or []
        if not (prods.get("pageInfo") or {}).get("hasNextPage"):
            break
        cursor = prods["pageInfo"]["endCursor"]
    return out[:maximum], err


def public_products(base, maximum):
    out, page = [], 1
    while len(out) < maximum and page <= 10:
        r = c.http(f"{base}/products.json?limit=250&page={page}", headers={"Accept": "application/json"}, timeout=30)
        prods = (r.json() or {}).get("products") if r.ok else None
        if not prods:
            break
        out += prods
        page += 1
    return out[:maximum]


def _num(x):
    try:
        return float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


def normalize_admin(p):
    vs = ((p.get("variants") or {}).get("nodes")) or []
    return {"title": p.get("title"), "ref": p.get("handle"), "active": p.get("status") == "ACTIVE",
            "prices": [_num(v.get("price")) for v in vs], "compare_at": [_num(v.get("compareAtPrice")) for v in vs],
            "image": bool(p.get("featuredMedia")), "stock": p.get("totalInventory"), "tracks_stock": p.get("tracksInventory"),
            "keeps_selling": any(v.get("inventoryPolicy") == "CONTINUE" for v in vs), "variants": len(vs),
            "no_sku": sum(1 for v in vs if not (v.get("sku") or "").strip()),
            "seo": bool(((p.get("seo") or {}).get("description") or "").strip()), "published": bool(p.get("onlineStoreUrl"))}


def normalize_public(p):
    vs = p.get("variants") or []
    return {"title": p.get("title"), "ref": p.get("handle"), "active": True,
            "prices": [_num(v.get("price")) for v in vs], "compare_at": [_num(v.get("compare_at_price")) for v in vs],
            "image": bool(p.get("images")), "stock": None, "tracks_stock": None, "keeps_selling": None,
            "variants": len(vs), "available": any(v.get("available") for v in vs), "no_sku": 0, "seo": None, "published": True}


def public_theme(html):
    m = re.search(r"Shopify\.theme\s*=\s*(\{.*?\});", html or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        name = re.search(r'"name"\s*:\s*"([^"]+)"', m.group(1))
        return {"name": name.group(1)} if name else None


def theme_check(path):
    cli = shutil.which("shopify")
    if not cli:
        return {"error": "The Shopify CLI was not found (npm install --global @shopify/cli)."}
    if not path or not Path(path).is_dir():
        return {"error": f"The theme folder does not exist: {path!r} (SHOPIFY_THEME_PATH or --theme-path)."}
    try:
        p = subprocess.run([cli, "theme", "check", "--path", str(path), "--output", "json"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600)
    except subprocess.TimeoutExpired:
        return {"error": "theme check took more than 10 minutes"}
    start = min([i for i in (p.stdout.find("["), p.stdout.find("{")) if i >= 0] or [-1])
    try:
        data = json.loads(p.stdout[start:]) if start >= 0 else None
    except ValueError:
        data = None
    if data is None:
        return {"error": (p.stderr or p.stdout or "no output").strip()[:300]}
    files = data if isinstance(data, list) else data.get("files") or []
    offenses = []
    for a in files:
        for o in a.get("offenses") or []:
            sev = o.get("severity")
            offenses.append({"file": a.get("path"), "rule": o.get("check"), "message": (o.get("message") or "")[:200],
                             "line": (o.get("start_row") if o.get("start_row") is not None else (o.get("start") or {}).get("line")),
                             "level": {0: "error", 1: "warning", 2: "info"}.get(sev, str(sev or "")).lower()})
    return {"offenses": offenses, "errors": sum(1 for o in offenses if o["level"] == "error"),
            "warnings": sum(1 for o in offenses if o["level"] == "warning")}


def _webhook_url(w):
    return w.get("uri") or ((w.get("endpoint") or {}).get("callbackUrl")) or ""


def findings_and_suggestions(inv):
    h, s = [], []
    store = inv.get("store") or {}
    plan = store.get("plan") or {}
    if inv.get("password"):
        h.append({"severity": "Low", "area": "Storefront", "text": "The store is password protected (/password): public checks are limited; to browse it, the agent goes in with Playwright and the storefront password."})
    if plan and plan.get("partnerDevelopment") is False:
        h.append({"severity": "High", "area": "Store", "text": f"This is not a development store (plan {plan.get('publicDisplayName') or plan.get('displayName') or '?'}): test orders only with the gateway in test mode (or Bogus Gateway) and with confirmation; afterwards they are cancelled and archived."})
    if store.get("setupRequired"):
        h.append({"severity": "Low", "area": "Store", "text": "Shopify flags that the store is missing its initial setup (setupRequired)."})
    if store.get("checkoutApiSupported") is False:
        h.append({"severity": "Medium", "area": "Checkout", "text": "The plan does not allow completing checkout through the API (checkoutApiSupported = false)."})

    for pol, name in POLICIES.items():
        status = (inv.get("policies") or {}).get(pol)
        if status is not None and status != 200:
            h.append({"severity": "Medium" if pol != "shipping-policy" else "Low", "area": "Legal",
                      "text": f"The {name} policy is not published (/policies/{pol} → HTTP {status}): it is shown in the checkout footer and many gateways require it."})

    theme = inv.get("public_theme") or {}
    if theme.get("role") and theme.get("role") != "main":
        h.append({"severity": "Low", "area": "Theme", "text": f'The storefront is being viewed with a theme that is not the published one (role {theme.get("role")}).'})
    themes = inv.get("themes") or []
    dev = [t for t in themes if t.get("role") in ("DEVELOPMENT", "UNPUBLISHED")]
    if len(dev) >= 15:
        h.append({"severity": "Low", "area": "Theme", "text": f"{len(dev)} unpublished or development themes (Shopify allows 20): consider cleaning up."})
    for t in themes:
        if t.get("role") == "MAIN":
            s.append({"area": "Theme", "element": t.get("name"), "test": f'Before publishing changes to the theme "{t.get("name")}", compare it with its preview (pixel-perfect) and go through home, collection, product, cart and search on mobile and desktop.'})

    tc = inv.get("theme_check") or {}
    if tc.get("errors"):
        h.append({"severity": "Medium", "area": "Theme", "text": f'Theme Check: {tc["errors"]} error(s) and {tc.get("warnings", 0)} warning(s) in the theme code.'})

    hc, _, _ = c.analyze_catalog(inv.get("products_norm"))
    h += hc
    for p in c.sold_out(inv.get("products_norm"))[:5]:
        s.append({"area": "Catalog", "element": p.get("title"), "test": 'Sold-out product that is not sold without stock: check that "Add to cart" is disabled and says "Sold out", and that it cannot be forced through /cart/add.'})
    oversold = [p for p in inv.get("products_norm") or [] if "oversell" in c.product_issues(p)][:3]
    for p in oversold:
        s.append({"area": "Catalog", "element": p.get("title"), "test": "Buy the product with no stock: confirm with the business that the pre-order is intentional and that inventory goes negative in a controlled way."})
    variants = [p for p in inv.get("products_norm") or [] if (p.get("variants") or 0) > 1][:3]
    for p in variants:
        s.append({"area": "Catalog", "element": p.get("title"), "test": "Pick each combination of options: price, image, availability and the URL (?variant=) change; a nonexistent combination cannot be bought."})

    for w in inv.get("webhooks") or []:
        url = _webhook_url(w)
        if url.startswith("http://"):
            h.append({"severity": "High", "area": "Integrations", "text": f'The webhook {w.get("topic")} sends to {url} without HTTPS.'})
        elif re.search(r"localhost|127\.0\.0\.1|ngrok|loca\.lt|trycloudflare", url):
            h.append({"severity": "Medium", "area": "Integrations", "text": f'The webhook {w.get("topic")} points to a tunnel or local machine ({url}): in a shared environment it is lost when that machine shuts down.'})
        s.append({"area": "Integrations", "element": w.get("topic"), "test": f'Trigger the {w.get("topic")} event and check that the receiver processes it only once (retries), validates the X-Shopify-Hmac-Sha256 signature and rejects a tampered payload.'})

    for d in inv.get("discounts") or []:
        cd = d.get("codeDiscount") or {}
        if cd.get("status") == "ACTIVE":
            s.append({"area": "Discounts", "element": cd.get("title"), "test": f'Apply "{cd.get("title")}" valid, in lowercase, with spaces, expired{", exceeding the usage limit" if cd.get("usageLimit") else ""}, combined with another discount and on a cart that does not meet the minimum; check the total, taxes and shipping.'})
        if cd.get("status") == "ACTIVE" and not cd.get("usageLimit") and not cd.get("endsAt"):
            h.append({"severity": "Low", "area": "Discounts", "text": f'The discount "{cd.get("title")}" is active with no usage limit and no end date: confirm it is intentional.'})

    for m in inv.get("markets") or []:
        if m.get("status", "ACTIVE" if m.get("enabled", True) else "DRAFT") == "ACTIVE":
            s.append({"area": "Markets", "element": m.get("name"), "test": f'Browse as a buyer from the "{m.get("name")}" market: currency, price rounding, taxes included or not, language, available shipping and final price at checkout.'})
    currencies = store.get("enabledPresentmentCurrencies") or []
    if len(currencies) > 1:
        s.append({"area": "Markets", "element": ", ".join(currencies[:8]), "test": "Switch currency on the storefront and check that the cart, the checkout and the confirmation email show the same currency and amount."})

    for e in inv.get("shipping") or []:
        if e.get("activeMethodDefinitionsCount") == 0:
            h.append({"severity": "High", "area": "Shipping", "text": f'The shipping profile "{e.get("name")}" has no active methods: its products cannot be bought with shipping.'})
        s.append({"area": "Shipping", "element": e.get("name"), "test": f'Checkout with products from the "{e.get("name")}" profile to an address inside and outside its zones, with weight/value at the limits of each rate and with free shipping.'})
    locs = [u for u in inv.get("locations") or [] if u.get("isActive")]
    if locs and not any(u.get("fulfillsOnlineOrders") for u in locs):
        h.append({"severity": "High", "area": "Inventory", "text": "No active location fulfills online orders."})
    if len(locs) > 1:
        s.append({"area": "Inventory", "element": ", ".join(u.get("name") for u in locs[:5]), "test": "With stock at only one location, buy and check which one it is deducted from and whether in-store pickup is offered."})

    scopes = inv.get("scopes") or []
    write = [a for a in scopes if DANGEROUS_SCOPES.match(a)]
    if write:
        h.append({"severity": "Low", "area": "QA token", "text": f'The QA token has write scopes ({", ".join(write[:8])}): read_* is enough for the survey. A read-only token is recommended.'})

    s += [{"area": "Checkout", "element": "Test gateway", "test": "With Bogus Gateway or Shopify Payments test mode: approved, declined and error payments; check the order status, the deducted stock and the confirmation email."},
          {"area": "Checkout", "element": "Guest and customer", "test": "Buy as a guest and with a customer account: prefilled data, saved addresses, order history and emails."},
          {"area": "Checkout", "element": "Cart", "test": "Add, change quantity (0, 1, maximum stock, more than the stock), remove and go back: the cart counter and the subtotal have to match /cart.js."},
          {"area": "Emails", "element": "Notifications", "test": "Review with the email-verifier the order confirmation, shipping, refund and abandoned cart emails: variables replaced, links and currency."}]
    return c.sort_findings(h), s


def tables_and_indicators(inv, base):
    store = inv.get("store") or {}
    plan = store.get("plan") or {}
    theme = inv.get("public_theme") or {}
    _, rows_cat, n_prob = c.analyze_catalog(inv.get("products_norm"))
    tables = []
    store_data = [["URL", base], ["Name", store.get("name") or "—"], ["myshopify domain", store.get("myshopifyDomain") or "—"],
                  ["Plan", plan.get("publicDisplayName") or plan.get("displayName") or "—"],
                  ["Development store", {True: "Yes", False: "No"}.get(plan.get("partnerDevelopment"), "—")],
                  ["Shopify Plus", {True: "Yes", False: "No"}.get(plan.get("shopifyPlus"), "—")],
                  ["Currency", store.get("currencyCode") or inv.get("cart_currency") or "—"],
                  ["Presentment currencies", ", ".join(store.get("enabledPresentmentCurrencies") or []) or "—"],
                  ["Taxes included in the price", {True: "Yes", False: "No"}.get(store.get("taxesIncluded"), "—")],
                  ["Time zone", store.get("ianaTimezone") or "—"],
                  ["Published theme", f'{theme.get("name") or "—"}{" " + theme["schema_version"] if theme.get("schema_version") else ""}'],
                  ["Password protected", "Yes" if inv.get("password") else "No"],
                  ["Admin API", f'version {inv.get("api_version")}' if inv.get("admin") else "no token (public storefront only)"]]
    tables.append(c.table("The store", ["Field", "Value"], store_data))
    if rows_cat:
        tables.append(c.table("Products with issues", ["Product", "Handle", "Issues"], rows_cat[:150], f"{n_prob} of {len(inv.get('products_norm') or [])} reviewed"))
    if inv.get("policies"):
        tables.append(c.table("Legal policies", ["Policy", "Status"], [[POLICIES[k], "Published" if v == 200 else f"HTTP {v}"] for k, v in inv["policies"].items()]))
    if inv.get("themes"):
        tables.append(c.table("Themes", ["Theme", "Role", "Updated"], [[t.get("name"), t.get("role"), (t.get("updatedAt") or "")[:10]] for t in inv["themes"]]))
    if inv.get("markets"):
        tables.append(c.table("Markets", ["Market", "Handle", "Status"], [[m.get("name"), m.get("handle"), m.get("status") or ("Active" if m.get("enabled") else "Inactive")] for m in inv["markets"]]))
    if inv.get("shipping"):
        tables.append(c.table("Shipping profiles", ["Profile", "General", "Active methods", "Countries"], [[e.get("name"), "Yes" if e.get("default") else "No", e.get("activeMethodDefinitionsCount", "—"), e.get("zoneCountryCount", "—")] for e in inv["shipping"]]))
    if inv.get("locations"):
        tables.append(c.table("Locations", ["Location", "Active", "Fulfills online"], [[u.get("name"), "Yes" if u.get("isActive") else "No", "Yes" if u.get("fulfillsOnlineOrders") else "No"] for u in inv["locations"]]))
    if inv.get("discounts"):
        tables.append(c.table("Discount codes", ["Discount", "Type", "Status", "From", "To", "Usage limit"],
                              [[(d.get("codeDiscount") or {}).get("title"), (d.get("codeDiscount") or {}).get("__typename", "").replace("DiscountCode", ""),
                                (d.get("codeDiscount") or {}).get("status"), ((d.get("codeDiscount") or {}).get("startsAt") or "")[:10],
                                ((d.get("codeDiscount") or {}).get("endsAt") or "—")[:10], (d.get("codeDiscount") or {}).get("usageLimit") or "no limit"] for d in inv["discounts"]]))
    if inv.get("webhooks"):
        tables.append(c.table("Webhooks", ["Event", "Destination"], [[w.get("topic"), _webhook_url(w)] for w in inv["webhooks"]]))
    tc = inv.get("theme_check") or {}
    if tc.get("offenses"):
        tables.append(c.table("Theme Check", ["Level", "Rule", "File", "Line", "Message"],
                              [[o["level"], o["rule"], o["file"], o.get("line") or "", o["message"]] for o in tc["offenses"][:200]], f'{len(tc["offenses"])} in total'))
    indicators = [{"label": "Products reviewed", "value": len(inv.get("products_norm") or []), "tone": "", "detail": "Admin API" if inv.get("admin") else "public catalog"},
                  {"label": "Products with issues", "value": n_prob, "tone": "bad" if n_prob else "ok", "detail": "price, stock, image, SEO"}]
    if tc and not tc.get("error"):
        indicators.append({"label": "Theme Check", "value": tc.get("errors", 0), "tone": "bad" if tc.get("errors") else "ok", "detail": f'errors · {tc.get("warnings", 0)} warnings'})
    return indicators, tables, n_prob


def main(argv=None):
    c.prepare_console()
    ap = argparse.ArgumentParser(description="QA survey of a Shopify store (read-only).")
    ap.add_argument("--store", help="storefront URL (or SHOPIFY_STORE_URL in the .env)")
    ap.add_argument("--story", default="")
    ap.add_argument("--product", default="", help="URL of a product page to review (otherwise, the first one in the catalog)")
    ap.add_argument("--max-products", type=int, default=250)
    ap.add_argument("--api-version", default="")
    ap.add_argument("--theme-check", action="store_true", help="run shopify theme check on SHOPIFY_THEME_PATH")
    ap.add_argument("--theme-path", default="")
    ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args(argv)

    env = c.read_env("SHOPIFY_")
    base = c.normalize_url(args.store or env.get("SHOPIFY_STORE_URL") or "")
    if not base:
        c.abort("Missing the store: pass it with --store https://my-store.myshopify.com or set SHOPIFY_STORE_URL in the .env.")
    c.authorize(base, env)
    domain = (env.get("SHOPIFY_STORE") or "").strip().lower()
    token = (env.get("SHOPIFY_ADMIN_TOKEN") or "").strip()
    version = args.api_version or env.get("SHOPIFY_API_VERSION") or API_VERSION
    if token and not domain:
        domain = re.sub(r"^https?://", "", base).split("/")[0] if base.endswith(".myshopify.com") else ""
        if not domain:
            print("[warning] SHOPIFY_ADMIN_TOKEN is set but SHOPIFY_STORE (my-store.myshopify.com) is missing: only the storefront is surveyed.", file=sys.stderr)
    if domain and not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.myshopify\.com", domain):
        c.abort(f"SHOPIFY_STORE has to be the myshopify domain (my-store.myshopify.com), not {domain!r}.")
    c.confirm(f"You are about to survey the Shopify store {base} (read-only{'; with the Admin API of ' + domain if token and domain else ''}).", args.confirm)

    inv, errors = {"api_version": version, "admin": bool(token and domain)}, {}
    print(f"[shopify] Storefront {base} …", file=sys.stderr)
    pw = c.http(base + "/", timeout=20)
    inv["password"] = "/password" in (pw.url or "") or bool(re.search(r'<form[^>]+action="/password"', pw.text or ""))
    inv["public_theme"] = public_theme(pw.text)
    if not pw.error and "shopify" not in (pw.text or "").lower() and "x-shopid" not in pw.headers and "powered-by" not in pw.headers:
        print("[warning] The home page does not look like Shopify (no cdn.shopify.com or Shopify headers).", file=sys.stderr)

    public = [] if inv["password"] else public_products(base, args.max_products)
    product_url = args.product or (f"{base}/products/{public[0]['handle']}" if public else "")
    checks, storefront_findings, _ = c.check_storefront(base, ERROR_PATTERNS, [product_url, f"{base}/collections/all", f"{base}/cart", f"{base}/search?q=a"]
                                                        if not inv["password"] else [])
    ch_p, h_p = c.check_product(product_url) if not inv["password"] else ([], [])
    checks += ch_p
    storefront_findings += h_p
    inv["policies"] = {} if inv["password"] else {k: c.http(f"{base}/policies/{k}", timeout=15).status for k in POLICIES}
    cart = c.http(base + "/cart.js", headers={"Accept": "application/json"}, timeout=15)
    inv["cart_currency"] = (cart.json() or {}).get("currency") if cart.ok else None
    checks.append({"check": "Cart (/cart.js)", "status": "ok" if cart.ok else "warning", "detail": f"HTTP {cart.status or cart.error}"})
    checks.append({"check": "Public catalog (/products.json)", "status": "ok" if public else "warning",
                   "detail": f"{len(public)} product(s)" if public else "not available (password or disabled)"})

    admin = []
    if inv["admin"]:
        for key, alternatives in QUERIES.items():
            print(f"[shopify] Admin API · {key} …", file=sys.stderr)
            data, err = query_first(domain, token, version, alternatives)
            if err:
                errors[key] = err
            data = data or {}
            if key == "store":
                inv["store"] = data.get("shop") or {}
            elif key == "themes":
                inv["themes"] = (data.get("themes") or {}).get("nodes") or []
            elif key == "locations":
                inv["locations"] = (data.get("locations") or {}).get("nodes") or []
            elif key == "markets":
                inv["markets"] = (data.get("markets") or {}).get("nodes") or []
            elif key == "webhooks":
                inv["webhooks"] = (data.get("webhookSubscriptions") or {}).get("nodes") or []
            elif key == "discounts":
                inv["discounts"] = (data.get("codeDiscountNodes") or {}).get("nodes") or []
            elif key == "shipping":
                inv["shipping"] = (data.get("deliveryProfiles") or {}).get("nodes") or []
            elif key == "scopes":
                inv["scopes"] = [a.get("handle") for a in ((data.get("currentAppInstallation") or {}).get("accessScopes") or [])]
        print("[shopify] Admin API · products …", file=sys.stderr)
        admin, err = admin_products(domain, token, version, args.max_products)
        if err:
            errors["products"] = err
    inv["products_norm"] = [normalize_admin(p) for p in admin] if admin else [normalize_public(p) for p in public]

    if args.theme_check:
        print("[shopify] Theme Check …", file=sys.stderr)
        inv["theme_check"] = theme_check(args.theme_path or env.get("SHOPIFY_THEME_PATH"))
        if inv["theme_check"].get("error"):
            errors["theme_check"] = inv["theme_check"]["error"]

    findings, suggestions = findings_and_suggestions(inv)
    findings = c.sort_findings(storefront_findings + findings)
    indicators, tables, n_prob = tables_and_indicators(inv, base)
    store = inv.get("store") or {}
    plan = store.get("plan") or {}
    data = {"story": args.story or None, "platform": "shopify",
            "store": {"url": base, "name": store.get("name") or re.sub(r"^https?://", "", base),
                      "version": f'theme {(inv.get("public_theme") or {}).get("name") or "—"}',
                      "environment": ("Development" if plan.get("partnerDevelopment") else "Live store") if plan else "—"},
            "storefront": {"checks": checks}, "inventory": {k: v for k, v in inv.items() if k != "products_norm"},
            "indicators": indicators, "tables": tables, "findings": findings, "suggestions": suggestions,
            "summary": {"products": len(inv["products_norm"]), "products_with_issues": n_prob}, "errors": errors}
    c.save("shopify", data, c.output_folder("shopify", args.story, base))
    return 0


if __name__ == "__main__":
    sys.exit(main())
