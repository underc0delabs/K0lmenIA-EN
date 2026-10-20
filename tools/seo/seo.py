#!/usr/bin/env python3
"""
Read-only, dependency-free SEO and GEO survey of a page (urllib + stdlib regex).

Usage (from the repo root):
    python tools/seo/seo.py --url https://my-site.com/page   [--output output/seo/page.json]

What it does (read-only, one GET per resource):
- Fetches the page and extracts the on-page SEO: title, meta description, canonical, meta robots, H1, Open Graph,
  structured data types (JSON-LD) and hreflang.
- Fetches robots.txt and detects whether it blocks the site and what it allows AI crawlers (GPTBot, ClaudeBot,
  PerplexityBot, Google-Extended) — key for GEO.
- Checks whether the sitemap exists.

It does not modify anything. The web-performance-auditor measures Core Web Vitals; the agent checks JS rendering with Playwright.
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = "k0lmenIA-QA/1.0 (read-only SEO survey)"
AI_BOTS = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "anthropic-ai", "PerplexityBot", "Google-Extended", "CCBot"]


def _find(rx, html, group=1):
    m = re.search(rx, html or "", re.I | re.S)
    return (m.group(group).strip() if m else None)


def extract_seo(html):
    """On-page SEO of an HTML document. Pure and testable."""
    types = set()
    for block in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html or "", re.I | re.S):
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
                stack.extend(v for v in x.values() if isinstance(v, (list, dict)))
    h1 = re.findall(r"<h1\b[^>]*>(.*?)</h1>", html or "", re.I | re.S)
    hreflang = re.findall(r'<link[^>]+rel=["\']alternate["\'][^>]+hreflang=["\']([^"\']+)["\']', html or "", re.I)
    return {
        "title": _find(r"<title[^>]*>(.*?)</title>", html),
        "meta_description": _find(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', html),
        "canonical": _find(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\'](.*?)["\']', html),
        "meta_robots": _find(r'<meta[^>]+name=["\']robots["\'][^>]+content=["\'](.*?)["\']', html),
        "og_title": _find(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']', html),
        "h1": [re.sub(r"<[^>]+>", "", x).strip() for x in h1],
        "jsonld_types": sorted(t for t in types if isinstance(t, str)),
        "hreflang": hreflang,
    }


def ai_crawlers(robots_txt):
    """For each AI bot, whether it has its own group and whether it is blocked (Disallow: /). Pure and testable."""
    out = {}
    lines = (robots_txt or "").splitlines()
    i = 0
    groups = []  # (agents set, disallows list)
    current_agents, current_dis, in_rules = set(), [], False
    for line in lines:
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        k, v = (x.strip() for x in line.split(":", 1))
        k = k.lower()
        if k == "user-agent":
            if in_rules:
                groups.append((current_agents, current_dis))
                current_agents, current_dis, in_rules = set(), [], False
            current_agents.add(v)
        elif k == "disallow":
            in_rules = True
            current_dis.append(v)
    if current_agents:
        groups.append((current_agents, current_dis))
    for bot in AI_BOTS:
        own = next((dis for ag, dis in groups if bot in ag), None)
        if own is None:
            out[bot] = "no rule of its own (inherits User-agent: *)"
        elif "/" in own:
            out[bot] = "blocked (Disallow: /)"
        else:
            out[bot] = "allowed"
    return out


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(3 * 1024 * 1024).decode(r.headers.get_content_charset() or "utf-8", "replace")
    except urllib.error.HTTPError as ex:
        return ex.code, ""
    except Exception as ex:
        return 0, f"{type(ex).__name__}: {ex}"


def survey(url):
    base = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(url))
    st, html = _get(url)
    inv = {"url": url, "status": st, "seo": extract_seo(html) if st and 200 <= st < 400 else {}}
    st_r, robots = _get(base + "/robots.txt", timeout=12)
    inv["robots_exists"] = bool(st_r and 200 <= st_r < 300)
    inv["ai_crawlers"] = ai_crawlers(robots) if inv["robots_exists"] else {}
    inv["robots_blocks_all"] = bool(re.search(r"(?im)^\s*user-agent:\s*\*\s*$.*?^\s*disallow:\s*/\s*$", robots or "", re.S))
    sm = (re.search(r"(?im)^sitemap:\s*(\S+)", robots or "") or [None, base + "/sitemap.xml"])[1]
    st_s, _ = _get(sm, timeout=15)
    inv["sitemap"] = {"url": sm, "exists": bool(st_s and 200 <= st_s < 300)}
    return inv


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="SEO/GEO survey of a page (read-only).")
    ap.add_argument("--url", required=True)
    ap.add_argument("--output", default="")
    args = ap.parse_args(argv)
    inv = survey(args.url)
    text = json.dumps(inv, ensure_ascii=False, indent=2)
    if args.output:
        p = Path(args.output)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        print(f"[seo] Data in {p}", file=sys.stderr)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
