#!/usr/bin/env python3
"""
Shared code for the e-commerce surveys (shopify.py, wordpress.py, prestashop.py and vtex.py):

- Authorization: only URLs in ECOMMERCE_AUTHORIZED_URLS from the .env are surveyed (same rule as
  SECURITY_AUTHORIZED_URLS: the host has to match and, if the entry has a path, the URL has to
  start with it).
- Read-only HTTP (GET and, for GraphQL, POST of queries without mutations) with urllib, no dependencies.
- Functional storefront checks that apply to any store: home page and key purchase pages
  (load and response time), robots.txt and sitemap, a real 404 page, visible platform errors
  (Liquid, PHP, templates) and product structured data. Security is NOT reviewed here: that belongs to
  the security-analyst and the web-pentester.
- Saving: <platform>.json in output/<platform>/<story or host>/, the previous run moves to
  history/ (last 5) and the HTML report is generated (scripts/generate_ecommerce_report.py).

Format of what the checks return:
    finding    = {"severity": "Critical|High|Medium|Low", "area": "...", "text": "..."}
    suggestion = {"area": "...", "element": "...", "test": "..."}
    check      = {"check": "...", "status": "ok|warning|fail|info", "detail": "..."}
"""
import datetime
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTTP_AGENT = "k0lmenIA-QA/1.0 (read-only survey; +https://k0lmena.com)"
MAX_BODY = 3 * 1024 * 1024
SEV_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
SLOW_MS = 3000


def abort(msg, code=2):
    print(msg, file=sys.stderr)
    sys.exit(code)


def read_env(*prefixes):
    sys.path.insert(0, str(ROOT / "scripts"))
    from _env import read_env as _read
    values = _read()
    values.update({k: v for k, v in os.environ.items() if k.startswith(prefixes + ("ECOMMERCE_",))})
    return values


def normalize_url(url):
    url = (url or "").strip()
    if url and not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    p = urllib.parse.urlsplit(url)
    if not p.netloc:
        return ""
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), "", ""))


def authorized_list(env):
    return [normalize_url(u) for u in re.split(r"[,\s]+", env.get("ECOMMERCE_AUTHORIZED_URLS", "")) if u.strip()]


def is_authorized(url, entries):
    """True if the host of `url` matches an entry and its path starts with that entry's path."""
    u = urllib.parse.urlsplit(normalize_url(url))
    for a in entries:
        p = urllib.parse.urlsplit(a)
        if u.netloc == p.netloc and (u.path + "/").startswith((p.path or "") + "/"):
            return True
    return False


def authorize(url, env):
    entries = authorized_list(env)
    if not entries:
        abort("There are no authorized stores. Add to the .env at the repo root:\n"
              "  ECOMMERCE_AUTHORIZED_URLS=https://my-store-qa.example.com\n"
              "(only your own stores or ones you have permission for, ideally test/staging).")
    if not is_authorized(url, entries):
        abort(f"{url} is not in ECOMMERCE_AUTHORIZED_URLS in the .env. Only authorized stores are surveyed.")


def confirm(text, already_confirmed):
    if already_confirmed:
        return
    print(text)
    if input("Confirm? [y/N] ").strip().lower() not in ("y", "yes"):
        abort("Cancelled.", 1)


class Response:
    def __init__(self, status=0, headers=None, text="", url="", ms=0, error=None):
        self.status, self.headers, self.text, self.url, self.ms, self.error = status, headers or {}, text, url, ms, error

    @property
    def ok(self):
        return 200 <= self.status < 300

    def json(self):
        try:
            return json.loads(self.text)
        except ValueError:
            return None


def http(url, method="GET", headers=None, body=None, timeout=25, user=None, password=None):
    """Read-only request. Never raises: network errors end up in Response.error."""
    if method not in ("GET", "HEAD", "POST"):
        raise ValueError("only GET/HEAD/POST queries")
    h = {"User-Agent": HTTP_AGENT, "Accept": "*/*"}
    h.update(headers or {})
    if user is not None:
        import base64
        h["Authorization"] = "Basic " + base64.b64encode(f"{user}:{password or ''}".encode()).decode()
    data = body.encode("utf-8") if isinstance(body, str) else body
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
            text = r.read(MAX_BODY).decode(r.headers.get_content_charset() or "utf-8", "replace")
            return Response(r.status, {k.lower(): v for k, v in r.headers.items()}, text, r.geturl(), int((time.monotonic() - t0) * 1000))
    except urllib.error.HTTPError as ex:
        try:
            text = ex.read(MAX_BODY).decode("utf-8", "replace")
        except Exception:
            text = ""
        return Response(ex.code, {k.lower(): v for k, v in (ex.headers or {}).items()}, text, ex.geturl() or url,
                        int((time.monotonic() - t0) * 1000))
    except Exception as ex:  # DNS, TLS, timeout, connection refused
        return Response(0, {}, "", url, int((time.monotonic() - t0) * 1000), f"{type(ex).__name__}: {ex}"[:300])


def join(base, path):
    return base.rstrip("/") + "/" + path.lstrip("/")


def sort_findings(findings):
    findings.sort(key=lambda x: SEV_ORDER.get(x.get("severity"), 9))
    return findings


# ------------------------------------------------------------------ public storefront checks
_JSONLD = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)


def jsonld_types(html):
    types = set()
    for block in _JSONLD.findall(html or ""):
        try:
            d = json.loads(block.strip())
        except ValueError:
            continue
        stack = [d]
        while stack:
            x = stack.pop()
            if isinstance(x, list):
                stack.extend(x)
            elif isinstance(x, dict):
                t = x.get("@type")
                types.update(t if isinstance(t, list) else [t] if t else [])
                stack.extend(v for k, v in x.items() if k in ("@graph", "offers", "mainEntity", "itemListElement"))
    return types


def robots_blocks_all(text):
    """True if the User-agent: * group has "Disallow: /" (the whole store hidden from search engines)."""
    agents, in_rules, blocks = set(), False, False
    for line in (text or "").splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (x.strip() for x in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if in_rules:
                agents, in_rules = set(), False
            agents.add(value)
        elif key in ("disallow", "allow"):
            in_rules = True
            if "*" in agents and key == "disallow" and value == "/":
                blocks = True
    return blocks


def html_errors(html, patterns):
    """[(name, snippet)] of the server error patterns that show up in the HTML."""
    text = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", html or "", flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    out = []
    for name, rx in patterns:
        m = re.search(rx, text)
        if m:
            out.append((name, re.sub(r"\s+", " ", text[max(0, m.start() - 30):m.end() + 90]).strip()))
    return out


def check_storefront(base, error_patterns=(), extra_pages=()):
    """Common public checks. Returns (checks, findings, home) — home is the Response for the home page."""
    ch, h = [], []
    home = http(base + "/")
    if home.error or not home.status:
        ch.append({"check": "Home page", "status": "fail", "detail": f"Not responding: {home.error}"})
        h.append({"severity": "Critical", "area": "Storefront", "text": f"The home page {base}/ is not responding ({home.error})."})
        return ch, h, home
    if home.status >= 500:
        h.append({"severity": "Critical", "area": "Storefront", "text": f"The home page returns {home.status}."})
    ch.append({"check": "Home page", "status": "ok" if home.ok else "fail",
               "detail": f"HTTP {home.status} in {home.ms} ms{' (redirects to ' + home.url + ')' if home.url.rstrip('/') != base else ''}"})
    if home.ms > SLOW_MS:
        h.append({"severity": "Medium", "area": "Web performance", "text": f"The home page takes {home.ms} ms to respond (more than {SLOW_MS} ms): measure it with the web-performance-auditor."})

    # robots and sitemap
    rob = http(base + "/robots.txt", timeout=15)
    blocks = rob.ok and robots_blocks_all(rob.text)
    ch.append({"check": "robots.txt", "status": "warning" if blocks else ("ok" if rob.ok else "warning"),
               "detail": "blocks the whole store (Disallow: /)" if blocks else ("exists" if rob.ok else f"HTTP {rob.status or rob.error}")})
    if blocks:
        h.append({"severity": "Low", "area": "SEO", "text": "robots.txt blocks the whole store (Disallow: /). That is fine on staging; in production it removes the store from search engines."})
    sm_url = (re.search(r"(?im)^sitemap:\s*(\S+)", rob.text or "") or [None, base + "/sitemap.xml"])[1] if rob.ok else base + "/sitemap.xml"
    sm = http(sm_url, timeout=20)
    ok_sm = sm.ok and "<" in sm.text[:200]
    ch.append({"check": "Sitemap", "status": "ok" if ok_sm else "warning", "detail": sm_url if ok_sm else f"{sm_url}: HTTP {sm.status or sm.error}"})
    if not ok_sm:
        h.append({"severity": "Low", "area": "SEO", "text": f"The sitemap was not found ({sm_url})."})

    # real 404
    r404 = http(f"{base}/k0lmenia-does-not-exist-{uuid.uuid4().hex[:8]}", timeout=15)
    ch.append({"check": "404 page", "status": "ok" if r404.status == 404 else "warning", "detail": f"HTTP {r404.status or r404.error}"})
    if r404.status == 200:
        h.append({"severity": "Low", "area": "SEO", "text": "A URL that does not exist returns 200 instead of 404 (soft 404)."})
    elif r404.status >= 500:
        h.append({"severity": "Medium", "area": "Storefront", "text": f"A URL that does not exist returns {r404.status} (server error instead of 404)."})

    # Key purchase pages and visible errors (home page and extra pages)
    seen = set()
    pages = [(base + "/", home)]
    for u in extra_pages:
        if u:
            r = http(u, timeout=20)
            pages.append((u, r))
            path = urllib.parse.urlsplit(u).path or "/"
            ch.append({"check": f"Page {path}", "status": "ok" if r.ok else "fail", "detail": f"HTTP {r.status or r.error} in {r.ms} ms"})
            if r.status >= 500 or r.error:
                h.append({"severity": "High", "area": "Storefront", "text": f"{u} does not load (HTTP {r.status or r.error})."})
    for url, resp in pages:
        for name, frag in html_errors(resp.text, error_patterns):
            if (name, url) in seen:
                continue
            seen.add((name, url))
            h.append({"severity": "High", "area": "Storefront", "text": f"{name} visible on {url}: “{frag[:160]}”"})
    ch.append({"check": "Visible server errors", "status": "fail" if seen else "ok",
               "detail": f"{len(seen)} found" if seen else "none on the pages reviewed"})
    return ch, h, home


def check_product(product_url):
    """Structured data of a product page (Product + Offer) and whether it responds."""
    ch, h = [], []
    if not product_url:
        return ch, h
    r = http(product_url, timeout=20)
    if not r.ok:
        ch.append({"check": "Product page", "status": "fail", "detail": f"{product_url}: HTTP {r.status or r.error}"})
        h.append({"severity": "High", "area": "Catalog", "text": f"The product page {product_url} does not load (HTTP {r.status or r.error})."})
        return ch, h
    types = jsonld_types(r.text)
    ch.append({"check": "Product page", "status": "ok", "detail": f"{product_url} in {r.ms} ms"})
    has_product = "Product" in types
    ch.append({"check": "Product structured data", "status": "ok" if has_product and "Offer" in types else "warning",
               "detail": ", ".join(sorted(t for t in types if isinstance(t, str))) or "no JSON-LD"})
    if not has_product:
        h.append({"severity": "Low", "area": "SEO", "text": "The product page has no Product structured data (JSON-LD): it does not show price and stock in Google Shopping."})
    elif "Offer" not in types and "AggregateOffer" not in types:
        h.append({"severity": "Low", "area": "SEO", "text": "The page's Product JSON-LD has no offers (price and availability)."})
    return ch, h


# ------------------------------------------------------------------ catalog (same rule on every platform)
# Each platform translates its products to this format (whatever it does not know, it leaves as None):
#   {"title", "ref" (handle/id), "active": bool|None, "prices": [float], "compare_at": [float|None],
#    "image": bool|None, "stock": int|None, "tracks_stock": bool|None, "keeps_selling": bool|None,
#    "variants": int, "no_sku": int, "seo": bool|None, "published": bool|None, "tax": bool|None}
ISSUES = {
    "zero_price": ("High", "for sale with price 0"),
    "oversell": ("Medium", "still sold when out of stock (overselling)"),
    "no_image": ("Medium", "without an image"),
    "without_tax": ("Medium", "without a tax rule"),
    "compare_at_lower": ("Low", "with a compare-at (strikethrough) price lower than or equal to the price"),
    "no_sku": ("Low", "with stock-tracked variants without a SKU"),
    "unpublished": ("Low", "active but not published on the online store"),
    "no_seo": ("Low", "without a meta description"),
}


def product_issues(p):
    if p.get("active") is False:
        return []
    out = []
    prices = [x for x in p.get("prices") or [] if x is not None]
    if prices and min(prices) <= 0:
        out.append("zero_price")
    stock = p.get("stock")
    if p.get("tracks_stock") and stock is not None and stock <= 0 and p.get("keeps_selling"):
        out.append("oversell")
    if p.get("image") is False:
        out.append("no_image")
    if p.get("tax") is False and prices and max(prices) > 0:
        out.append("without_tax")
    if any(c is not None and pr is not None and 0 < c <= pr for pr, c in zip(p.get("prices") or [], p.get("compare_at") or [])):
        out.append("compare_at_lower")
    if p.get("tracks_stock") and (p.get("no_sku") or 0) > 0:
        out.append("no_sku")
    if p.get("published") is False:
        out.append("unpublished")
    if p.get("seo") is False:
        out.append("no_seo")
    return out


def analyze_catalog(products, area="Catalog"):
    """(findings aggregated by issue, rows for the products-with-issues table, count with issues)."""
    by_problem, rows = {}, []
    for p in products or []:
        ps = product_issues(p)
        for k in ps:
            by_problem.setdefault(k, []).append(p.get("title") or p.get("ref") or "?")
        if ps:
            rows.append([p.get("title") or "?", p.get("ref") or "", "; ".join(ISSUES[k][1] for k in ps)])
    h = []
    for k, (sev, text) in ISSUES.items():
        names = by_problem.get(k)
        if names:
            h.append({"severity": sev, "area": area,
                      "text": f"{len(names)} product(s) {text}: {', '.join(names[:5])}{'…' if len(names) > 5 else ''}."})
    return h, rows, len(rows)


def sold_out(products):
    return [p for p in products or [] if p.get("active") is not False and p.get("tracks_stock") and (p.get("stock") is not None and p["stock"] <= 0)
            and not p.get("keeps_selling")]


def table(title, columns, rows, sub=""):
    return {"title": title, "sub": sub, "columns": columns, "rows": rows}


# ------------------------------------------------------------------ saving
def output_folder(platform, story, url):
    name = story or urllib.parse.urlsplit(normalize_url(url)).netloc or platform
    return ROOT / "output" / platform / re.sub(r"[^\w.-]+", "-", name)


def save(platform, data, folder):
    data.setdefault("generated", datetime.datetime.now().isoformat(timespec="seconds"))
    findings = data.get("findings") or []
    data["summary"] = dict({"findings": len(findings), "critical": sum(1 for x in findings if x.get("severity") in ("Critical", "High")),
                            "suggestions": len(data.get("suggestions") or []),
                            "by_severity": {s: sum(1 for x in findings if x.get("severity") == s) for s in SEV_ORDER}},
                           **(data.get("summary") or {}))
    folder.mkdir(parents=True, exist_ok=True)
    report = f"{platform}-report.html"
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import _history
        _history.archive(folder, [f"{platform}.json", "analysis.json", report], f"{platform}.json")
    except Exception as ex:
        print(f"[warning] could not archive the previous run: {ex}", file=sys.stderr)
    (folder / f"{platform}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        import generate_ecommerce_report
        generate_ecommerce_report.generate(folder / f"{platform}.json", folder / report)
        print(f"[{platform}] Report: {folder / report}", file=sys.stderr)
    except Exception as ex:
        print(f"[warning] could not generate the HTML report: {ex}", file=sys.stderr)
    err = data.get("errors") or {}
    print(f"[{platform}] {len(findings)} finding(s), {len(data.get('suggestions') or [])} test suggestion(s)"
          f"{', ' + str(len(err)) + ' query(ies) with errors' if err else ''}.")
    print(f"[{platform}] Data: {folder / (platform + '.json')}")
    return folder / f"{platform}.json"


def prepare_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
