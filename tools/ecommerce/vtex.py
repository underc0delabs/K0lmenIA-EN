#!/usr/bin/env python3
"""
Functional QA survey of an AUTHORIZED VTEX store (read-only).

Usage (from the repo root):
    python tools/ecommerce/vtex.py --store https://www.my-store.com --account myaccount
        [--story US-001] [--product https://.../p] [--max-products 300] [--sc 1] [--confirm]

What it does:
- Checks that the store is in ECOMMERCE_AUTHORIZED_URLS in the .env.
- Public storefront: common checks (home and key pages, robots, sitemap, 404, visible store or
  VTEX IO errors) and the structured data of a product page.
- Public Catalog System (no credentials): the sales channel catalog (`/api/catalog_system/pub/
  products/search`) with SKUs, price and availability (commertialOffer) — enough to analyze the catalog.
- Admin APIs (optional, with VTEX_APP_KEY/VTEX_APP_TOKEN of an app with READ-ONLY scopes):
  sales channels (trade policies), shipping policies (SLAs) and promotions.
- Computes findings and test suggestions and leaves in output/vtex/<story or host>/: vtex.json and
  vtex-report.html (the previous run moves to history/).

GET only. It does not create purchase orderForms, orders or data and does not change configuration. The store's
security is not reviewed here (security-analyst, web-pentester).
"""
import argparse
import datetime
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as c  # noqa: E402

ERROR_PATTERNS = [("Store error", r"Internal Server Error|Something went wrong|503 Service"),
                  ("VTEX IO error", r"RenderRuntime|Failed to fetch|GraphQL error|react-error"),
                  ("Visible VTEX error", r'"error"\s*:\s*\{|VtexIdclientAutCookie|Workspace .* not found')]


def _num(x):
    try:
        return float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _items(d):
    """VTEX APIs return a list, or {"items": [...]} (paginated). Normalizes to a list."""
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        return d.get("items") or d.get("Items") or []
    return []


def api_host(account, environment):
    return f"https://{account}.{environment}.com.br"


def vtex_get(url, key=None, token=None, timeout=40):
    """Public GET or, with AppKey/AppToken, admin GET. (data, error)."""
    headers = {"Accept": "application/json"}
    if key and token:
        headers["X-VTEX-API-AppKey"] = key
        headers["X-VTEX-API-AppToken"] = token
    r = c.http(url, headers=headers, timeout=timeout)
    if r.error:
        return None, r.error
    if r.status in (401, 403):
        return None, f"HTTP {r.status}: the app (AppKey/AppToken) is invalid or does not have read permission"
    if r.status == 404:
        return None, "HTTP 404: the resource is not available in this account"
    if not r.ok:
        return None, f"HTTP {r.status}: {(r.text or '')[:160]}"
    d = r.json()
    return (d, None) if d is not None else (None, "non-JSON response")


def products_pub(host, maximum, sc=None):
    """Public catalog of the sales channel, paginated 50 at a time (API limit)."""
    out, start = [], 0
    sc_q = f"&sc={sc}" if sc else ""
    while len(out) < maximum and start < 2500:
        end = start + 49
        d, err = vtex_get(f"{host}/api/catalog_system/pub/products/search?_from={start}&_to={end}{sc_q}", timeout=30)
        batch = d if isinstance(d, list) else []
        if not batch:
            break
        out += batch
        if len(batch) < 50:
            break
        start += 50
    return out[:maximum]


def normalize(p, base):
    items = p.get("items") or []
    offers, has_img, no_sku = [], False, 0
    for it in items:
        if it.get("images"):
            has_img = True
        refs = it.get("referenceId") or []
        if not any((r.get("Value") or "").strip() for r in refs):
            no_sku += 1
        for s in it.get("sellers") or []:
            co = s.get("commertialOffer") or {}
            offers.append((_num(co.get("Price")), _num(co.get("ListPrice")), bool(co.get("IsAvailable")), int(co.get("AvailableQuantity") or 0)))
    prices_v = [o[0] for o in offers if o[0] is not None]
    min_price = min(prices_v) if prices_v else None
    lp_rep = next((o[1] for o in offers if o[0] == min_price), None)
    link = p.get("link") or (f'{base}/{p.get("linkText")}/p' if p.get("linkText") else None)
    return {"title": p.get("productName"), "ref": (p.get("productReference") or "").strip() or p.get("productId"),
            "active": True, "url": link,
            "prices": [min_price] if min_price is not None else [],
            "compare_at": [lp_rep],
            "image": has_img, "stock": sum(o[3] for o in offers), "tracks_stock": True,
            "keeps_selling": None, "variants": len(items) or 1, "no_sku": no_sku,
            "tax": None, "seo": bool(p.get("metaTagDescription")),
            "published": any(o[2] for o in offers), "type": "multi-sku" if len(items) > 1 else "simple"}


def _date(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def findings_and_suggestions(inv, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    h, s = [], []

    if inv.get("workspace") and inv["workspace"].lower() == "master":
        h.append({"severity": "Medium", "area": "Environment", "text": "You are surveying the master workspace (production). For QA, use your own workspace (qa--myaccount.myvtex.com), which is an isolated copy."})

    prods = inv.get("products_norm") or []
    if inv.get("public_api") and not prods:
        h.append({"severity": "High", "area": "Catalog", "text": "The public catalog returned no products for the sales channel: nothing to buy (wrong sales channel, unindexed catalog or products without a trade policy?)."})

    channels = _items(inv.get("saleschannels"))
    active = [t for t in channels if t.get("IsActive")]
    if inv.get("saleschannels") is not None and not active:
        h.append({"severity": "High", "area": "Sales channels", "text": "There is no active sales channel (trade policy): the store does not sell."})
    for t in active[:6]:
        s.append({"area": "Sales channels", "element": f'{t.get("Name")} ({t.get("Id")})',
                  "test": f'Buy on the “{t.get("Name")}” channel ({t.get("CurrencyCode") or "?"}): prices, availability and checkout of the channel; a product outside this channel cannot be bought here.'})

    slas = _items(inv.get("shipping"))
    active_slas = [x for x in slas if x.get("isActive", True)]
    if inv.get("shipping") is not None and not active_slas:
        h.append({"severity": "High", "area": "Shipping", "text": "There is no active shipping policy (SLA): a purchase with shipping cannot be completed."})
    for x in active_slas[:6]:
        s.append({"area": "Shipping", "element": x.get("name") or x.get("id"),
                  "test": f'Checkout with the shipping policy “{x.get("name") or x.get("id")}”: cost by region and weight, price ranges, free shipping and recalculation when the address or the CEP/postal code changes.'})

    for pr in _items(inv.get("promotions")):
        is_active = pr.get("isActive")
        end = _date(pr.get("endDateUtc") or pr.get("endDate"))
        name = pr.get("name") or pr.get("idCalculatorConfiguration") or "?"
        if is_active and end and end < now:
            h.append({"severity": "Low", "area": "Promotions", "text": f'The promotion “{name}” is active but expired ({str(pr.get("endDateUtc") or pr.get("endDate"))[:10]}).'})
        elif is_active:
            s.append({"area": "Promotions", "element": name, "test": f'Apply the promotion “{name}”: it is calculated on the right cart, does not stack with another one when it should not, and respects dates, channel and conditions.'})

    hc, _, _ = c.analyze_catalog(prods)
    h += hc
    for p in [p for p in prods if p.get("type") == "multi-sku"][:3]:
        s.append({"area": "Catalog", "element": p.get("title"), "test": "Product with several SKUs: each SKU changes price, image, reference and availability; an out-of-stock or nonexistent SKU cannot be added."})
    for p in [p for p in prods if not p.get("published")][:3]:
        s.append({"area": "Catalog", "element": p.get("title"), "test": "Product that appears in the catalog but shows no availability: it cannot be added to the cart or bought through the orderForm API."})

    if inv.get("public_api"):
        s += [{"area": "Checkout", "element": "orderForm", "test": "Full purchase flow (identification, address, shipping, payment) as a guest and with an account; the orderForm total adds up with the cart, the gateway, the order (OMS) and the email; double-clicking pay does not duplicate the order."},
              {"area": "Payments", "element": "Payment conditions", "test": "Each payment method in sandbox (approved, declined, 3-D Secure) and, if applicable, installments; the anti-fraud does not reject a legitimate test purchase. Never real cards."},
              {"area": "Emails", "element": "Transactional", "test": "With the email-verifier: confirmation, payment approved, invoice/invoiced, shipped and cancelled; unreplaced template variables and links."},
              {"area": "Permissions", "element": "My account", "test": "With the permissions-tester: a customer sees only their own orders and addresses (not someone else's, not even by changing the id in the OMS/Master Data API)."},
              {"area": "Web performance", "element": "Catalog and product page", "test": "With the web-performance-auditor: home, category with filters, product page and search; orderForm and search latency; impact of the VTEX IO apps. For load, the performance-mapper."}]
    return c.sort_findings(h), s


def tables_and_indicators(inv, base):
    prods = inv.get("products_norm") or []
    _, rows_cat, n_prob = c.analyze_catalog(prods)
    channels = _items(inv.get("saleschannels"))
    active = [t for t in channels if t.get("IsActive")]
    slas = _items(inv.get("shipping"))
    promos = _items(inv.get("promotions"))
    data = [["URL", base], ["Account", inv.get("account") or "—"], ["Workspace", inv.get("workspace") or "master"],
            ["Storefront", inv.get("storefront") or "—"],
            ["Active sales channels", str(len(active)) + (f' of {len(channels)}' if channels else "") if inv.get("saleschannels") is not None else "—"],
            ["Admin APIs", "with AppKey/AppToken" if inv.get("api_admin") else "no credentials (public catalog)"]]
    tables = [c.table("The store", ["Field", "Value"], data)]
    if rows_cat:
        tables.append(c.table("Products with issues", ["Product", "Reference", "Issues"], rows_cat[:150], f"{n_prob} of {len(prods)} reviewed"))
    if channels:
        tables.append(c.table("Sales channels (trade policies)", ["Channel", "Id", "Currency", "Active"],
                              [[t.get("Name"), t.get("Id"), t.get("CurrencyCode"), "Yes" if t.get("IsActive") else "No"] for t in channels]))
    if slas:
        tables.append(c.table("Shipping policies (SLAs)", ["Policy", "Active"],
                              [[x.get("name") or x.get("id"), "Yes" if x.get("isActive", True) else "No"] for x in slas]))
    if promos:
        tables.append(c.table("Promotions", ["Name", "Type", "Active", "Expires"],
                              [[pr.get("name"), pr.get("type"), "Yes" if pr.get("isActive") else "No",
                                (str(pr.get("endDateUtc") or pr.get("endDate"))[:10] if (pr.get("endDateUtc") or pr.get("endDate")) else "—")] for pr in promos[:100]]))
    indicators = [{"label": "Products reviewed", "value": len(prods), "tone": "", "detail": "public Catalog System"},
                  {"label": "Products with issues", "value": n_prob, "tone": "bad" if n_prob else "ok", "detail": "price, image, SKU, compare-at"},
                  {"label": "Active sales channels", "value": len(active), "tone": "bad" if (inv.get("saleschannels") is not None and not active) else "ok", "detail": f"of {len(channels)}" if channels else "no credentials"}]
    return indicators, tables, n_prob


def main(argv=None):
    c.prepare_console()
    ap = argparse.ArgumentParser(description="Functional QA survey of a VTEX store (read-only).")
    ap.add_argument("--store", help="storefront URL (or VTEX_URL in the .env)")
    ap.add_argument("--account", default="", help="VTEX account name (or VTEX_ACCOUNT); otherwise it is inferred from the URL")
    ap.add_argument("--story", default="")
    ap.add_argument("--product", default="", help="URL of a product page to review (otherwise, the first one in the catalog)")
    ap.add_argument("--max-products", type=int, default=300)
    ap.add_argument("--sc", default="", help="sales channel for the public catalog")
    ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args(argv)

    env = c.read_env("VTEX_")
    base = c.normalize_url(args.store or env.get("VTEX_URL") or "")
    if not base:
        c.abort("Missing the store: pass it with --store https://www.my-store.com or set VTEX_URL in the .env.")
    c.authorize(base, env)

    host_url = urllib.parse.urlsplit(base).netloc
    account = (args.account or env.get("VTEX_ACCOUNT") or "").strip()
    if not account:
        m = re.match(r"^([\w-]+)\.(?:vtexcommercestable|myvtex|vtexlocal)\.", host_url)
        account = m.group(1) if m else ""
    environment = (env.get("VTEX_ENVIRONMENT") or "vtexcommercestable").strip()
    key, token = (env.get("VTEX_APP_KEY") or "").strip(), (env.get("VTEX_APP_TOKEN") or "").strip()
    sc = (args.sc or env.get("VTEX_SALES_CHANNEL") or "").strip()
    c.confirm(f"You are about to survey the VTEX store {base}{' (account ' + account + ')' if account else ''} (read-only{'; with the admin APIs' if key and token else ''}).", args.confirm)

    inv, errors = {"account": account or None, "workspace": (env.get("VTEX_WORKSPACE") or "master").strip(),
                   "public_api": bool(account), "api_admin": bool(account and key and token)}, {}
    host = api_host(account, environment) if account else None

    if host:
        print(f"[vtex] Public catalog {host} …", file=sys.stderr)
        pub = products_pub(host, args.max_products, sc)
        inv["products_norm"] = [normalize(p, base) for p in pub]
        if not pub:
            errors["catalog"] = "The public catalog returned no products (sales channel? try --sc 1)."
        if key and token:
            for name, path in (("saleschannels", "/api/catalog_system/pvt/saleschannel/list"),
                               ("shipping", "/api/logistics/pvt/shipping-policies?page=1&perPage=100"),
                               ("promotions", "/api/rnb/pvt/benefits/calculatorconfiguration")):
                print(f"[vtex] API · {name} …", file=sys.stderr)
                d, err = vtex_get(host + path, key, token)
                inv[name] = d
                if err:
                    errors[name] = err
    else:
        inv["products_norm"] = []
        errors["account"] = "The VTEX account could not be determined: pass it with --account or VTEX_ACCOUNT. Without an account only the public storefront is surveyed."

    # Public storefront
    product_url = args.product or next((p.get("url") for p in inv["products_norm"] if p.get("url")), "")
    print(f"[vtex] Storefront {base} …", file=sys.stderr)
    checks, storefront_findings, home = c.check_storefront(base, ERROR_PATTERNS, [product_url] if product_url else [])
    ch_p, h_p = c.check_product(product_url)
    txt = home.text or ""
    if re.search(r"__RUNTIME__|vtex\.render-runtime|data-vtex", txt):
        inv["storefront"] = "Store Framework (VTEX IO)"
    elif re.search(r"faststore|@faststore", txt, re.I):
        inv["storefront"] = "FastStore"
    elif re.search(r"vtex", txt, re.I):
        inv["storefront"] = "VTEX (legacy/CMS Portal)"
    is_vtex = bool(inv.get("storefront")) or bool(account)
    checks += ch_p + [{"check": "VTEX detected", "status": "ok" if is_vtex else "warning",
                       "detail": inv.get("storefront") or ("account " + account if account else "no VTEX signals were recognized")},
                      {"check": "Public catalog (Catalog System)", "status": "ok" if inv["products_norm"] else ("warning" if account else "info"),
                       "detail": f'{len(inv["products_norm"])} product(s)' if inv["products_norm"] else ("no products" if account else "no account")}]

    findings, suggestions = findings_and_suggestions(inv)
    findings = c.sort_findings(storefront_findings + h_p + findings)
    indicators, tables, n_prob = tables_and_indicators(inv, base)
    data = {"story": args.story or None, "platform": "vtex",
            "store": {"url": base, "name": account or re.sub(r"^https?://", "", base),
                      "version": f"VTEX · {inv.get('storefront')}" if inv.get("storefront") else "VTEX",
                      "environment": inv.get("workspace") or "master"},
            "storefront": {"checks": checks}, "inventory": {k: v for k, v in inv.items() if k != "products_norm"},
            "indicators": indicators, "tables": tables, "findings": findings, "suggestions": suggestions,
            "summary": {"products": len(inv["products_norm"]), "products_with_issues": n_prob}, "errors": errors}
    c.save("vtex", data, c.output_folder("vtex", args.story, base))
    return 0


if __name__ == "__main__":
    sys.exit(main())
