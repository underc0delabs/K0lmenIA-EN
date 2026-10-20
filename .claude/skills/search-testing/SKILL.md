---
name: search-testing
description: How to test search and relevance (Elasticsearch/OpenSearch, Algolia, Solr, Typesense, Meilisearch or database full-text) — relevance and ranking (the right result in the top positions, boosting by field/business), typo tolerance and fuzzy, synonyms and stemming/lemmatization by language, stop words and accents/diacritics, "zero results" and suggestions (did-you-mean), autocomplete/typeahead, facets and filters (and their combination with the query), pagination and order, freshness and indexing (a new record appears, a deleted one disappears), exact match by SKU/code, empty or very long queries, query injection, security (don't return documents without the user's permission), web performance/search latency, and measurement with a golden set of query→expected result and metrics (precision@k, recall, nDCG, MRR); how to automate (golden set against the search endpoint with api-runner or the UI with Playwright), typical bugs and questions for the PO. Used by the search-tester.
---

# Search and relevance testing

Search is not "it brings back something": it is **bringing back the right thing, at the top, fast**. It is tested with a **golden set** (queries with the expected result(s)) and edge cases, plus relevance, filters and indexing. It is complemented by `design-techniques` and, for stores, by `ecommerce-testing`.

## 1. Relevance and ranking

- The query with clear intent brings back the **right result in the top positions** (not on page 3).
- **Boosting**: more important fields (title > description), and business rules (featured, stock, promos) affect the order as expected.
- One-word, multi-word, exact-phrase (quotes) and partial queries.

## 2. Error and language tolerance

- **Typos / fuzzy**: "iphon", "labtop" find the right thing (with a reasonable edit distance).
- **Synonyms** (cellphone/mobile, tee/t-shirt) and **stemming/lemmatization** by language (shoe/shoes, run/running).
- **Stop words**, **accents/diacritics** (café = cafe, résumé = resume), uppercase/lowercase.

## 3. Zero results and helpers

- A query with no results shows a **clear message** and, if applicable, **did-you-mean** / suggestions, not an empty page or an error.
- **Autocomplete/typeahead**: suggests as you type, fast and relevant.

## 4. Facets, filters and order

- The **facets** (category, price, brand) filter well and **combine with the query**; the counters for each facet are correct; clearing filters returns to the base state.
- **Pagination** and **order** (relevance, price, date) without losing or duplicating results.

## 5. Indexing and freshness

- A **new document appears** in the search after indexing (watch out for the indexing delay: it may not be a bug), a **deleted one disappears**, an edited one reflects the change.
- **Exact match by SKU/code/ID**; search by attributes.

## 6. Edges and security

- **Empty** query, spaces only, very long, with special characters or wildcards; that it doesn't break or cause **injection** in the query (Query DSL injection).
- **Security/permissions**: a user doesn't see in the results documents they don't have access to (multi-tenant, drafts, private).

## 7. Performance

- **Latency** of the search and of autocomplete under typical and heavy queries (many facets); for load, `performance-mapper`.

## 8. Measure (golden set and metrics)

- Build a **golden set**: query → expected result(s) or criterion ("the first result must be X"). Measure **precision@k**, **recall**, and for ranking **nDCG** or **MRR**.
- It is also the **regression suite**: when analyzers, synonyms or boosting are changed, the set is run and compared (did relevance improve or get worse?).

## 9. Automate

- Golden set against the **search endpoint** with the `api-runner`, or against the **UI** with Playwright (`e2e-execution`); verify the position/presence of the expected result, facets and zero-results.
- Test data: products/documents with synonyms, accents, deliberate typos and one with no results (`test-data-generator`).

## 10. Typical search bugs

- The obvious result doesn't appear first (bad relevance/boosting).
- It doesn't tolerate typos or accents; synonyms that don't work.
- Zero results with no message or suggestion (empty screen).
- A facet whose counter doesn't match the results; a query+filter combination that breaks.
- A deleted document that keeps appearing (stale indexing).
- Results that expose private/other-tenant documents.
- Slow or irrelevant autocomplete; a search that takes down the backend with a heavy query.

## 11. Typical questions for the PO (search)

When it isn't written down, they are `MI-XX`:

- Which search engine (Elasticsearch/OpenSearch, Algolia, Solr, DB full-text)?
- What are the most important queries and their expected result (for the golden set)?
- What boosting/business rules affect the order?
- Are synonyms and stemming configured? In which languages?
- How long does indexing take to reflect a change?
- Are there documents with permissions (private/multi-tenant) that must not leak?
