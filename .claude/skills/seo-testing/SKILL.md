---
name: seo-testing
description: How to test the SEO and GEO (generative engine optimization / AI search engines) of a site — technical SEO (indexability, robots.txt, sitemap.xml, canonicals, meta robots/noindex, status codes and 301/302 redirects, URLs, pagination, hreflang and internationalization, Schema.org/JSON-LD structured data, Open Graph and Twitter Cards, performance and Core Web Vitals, mobile-first, JS/SSR vs. CSR rendering), on-page SEO (title, meta description, H1-Hn headings, image alt, internal links, content and keywords, cannibalization, duplicate content), and GEO (how to show up in Google's AI Overviews, ChatGPT, Perplexity and Copilot — citable and structured content, authority and E-E-A-T, direct answers, structured data, llms.txt, AI crawler access —GPTBot, ClaudeBot, PerplexityBot— in robots.txt, freshness and sources); how to measure and automate (fetch the page and check meta/robots/sitemap/structured data; Lighthouse for CWV with web-performance-auditor), typical bugs and questions for the PO. Used by the seo-analyst.
---

# SEO and GEO testing

SEO is about **search engines** finding, understanding and indexing the site; **GEO** (Generative Engine Optimization) is about **AI engines** (AI Overviews, ChatGPT, Perplexity, Copilot) **citing** it in their answers. They share a lot (clear, structured and authoritative content), but GEO adds its own. It leans on the `web-performance-auditor` (Core Web Vitals) and `translation-analyst` (hreflang/languages).

## 1. Indexability (technical SEO)

- **robots.txt**: doesn't block what must be indexed; declares the **Sitemap:**. A `Disallow: /` in production takes the site out of Google (fine in staging).
- **sitemap.xml**: exists, is valid, lists the canonical URLs (not the blocked or `noindex` ones), and is up to date.
- **meta robots / X-Robots-Tag**: `noindex` where appropriate (internal search results, carts), and **not** on pages that must rank. A `noindex` forgotten in production is one of the worst SEO bugs.
- **Status codes and redirects**: 200 on indexable pages, **301** (not 302) for permanent redirects, no chains or loops; an old URL redirects, it doesn't give a 404 or a soft-404.
- **Canonicals** (`rel=canonical`): each page points to its canonical version; no cross canonicals or pointing to another page.

## 2. On-page

- **Title** unique and descriptive (~60 chars), **meta description** (~155 chars), a single **H1**, a coherent heading hierarchy.
- **Alt** on the images, **internal links** with useful anchor, no duplicate content or **cannibalization** (two pages competing for the same keyword).
- Clean and stable URLs; parameters that don't generate indexable duplicates.

## 3. Structured data and social

- **Schema.org (JSON-LD)**: the correct type (Product, Article, FAQ, BreadcrumbList, Organization, LocalBusiness…), valid and consistent with what is visible. It enables rich results **and** helps GEO.
- **Open Graph** and **Twitter Cards** so the site looks good when shared (and some engines use them).

## 4. International

- **hreflang** correct and reciprocal across languages/regions, with `x-default`; not pointing to `noindex` or broken pages (see `translation-analyst`).

## 5. Performance and rendering

- **Core Web Vitals** (LCP, CLS, INP) with the `web-performance-auditor`: they are a ranking and experience factor.
- **Rendering**: if the site is CSR (pure JS), Google may see it empty; verify that the key content is in the initial HTML (SSR/prerender) or that it renders well. Content that only appears after interaction isn't indexed.
- **Mobile-first**: Google indexes the mobile version; make sure it has the same content and structured data as desktop.

## 6. GEO (generative / AI engines)

- **AI crawler access**: in `robots.txt`, define whether you allow **GPTBot** (OpenAI), **ClaudeBot/anthropic-ai**, **PerplexityBot**, **Google-Extended** (training) and **OAI-SearchBot**. Blocking them takes you out of their answers; allowing them makes you citable. It is a business decision: confirm it.
- **Citable content**: **direct and self-contained** answers (a paragraph that answers the question), question-form headings, lists and tables, clear definitions; the engines cite fragments, not whole pages.
- **Authority and E-E-A-T** (experience, expertise, authoritativeness, trust): author, cited sources, update date, verifiable data. AI engines prefer trustworthy and fresh sources.
- **Structured data** (FAQ, HowTo, Article): they help the AI extract the answer.
- **llms.txt** (emerging): a file that summarizes the site for LLMs; optional, but it adds value.
- **Freshness**: dated and updated content; old content is cited less.

## 7. Measure and automate

- The `npm run seo` tool (`tools/seo/seo.py`) fetches a URL and checks title, meta description, canonical, meta robots, Open Graph, JSON-LD, H1, hreflang, robots.txt, sitemap and AI crawler access.
- The Core Web Vitals, with the `web-performance-auditor`; the JS render, by opening the page with Playwright and comparing the initial HTML with the rendered one.

## 8. Typical SEO/GEO bugs

- `noindex` or `Disallow: /` forgotten in production.
- Canonical pointing to another page or to `http` on an `https` site.
- Duplicate or empty title/description; several H1s or none.
- 302 redirects where they should be 301; redirect chains; soft-404.
- Invalid JSON-LD or one that doesn't match what is visible.
- Key content only in JS that Google doesn't render.
- hreflang not reciprocal or to broken pages.
- AI crawlers blocked by mistake (or allowed when the business didn't want them).
- Sitemap with `noindex`, broken or non-canonical URLs.

## 9. Typical questions for the PO (SEO/GEO)

When it isn't written down, they are `MI-XX`:

- Which pages must be indexed and which must not? Is there a sitemap and who generates it?
- Is the site SSR or CSR? Is the key content in the initial HTML?
- Which languages/regions and how is hreflang handled?
- Do you want to show up in AI engines? Are GPTBot/ClaudeBot/PerplexityBot allowed?
- Which structured data types apply to the content?
- Are there target keywords per page (to detect cannibalization)?
