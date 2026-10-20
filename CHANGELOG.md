# k0lmenIA changelog

The most relevant changes, newest first. The details of each one are in the git history.

## 2026-10-20 — Mutation testing and a wizard to choose an agent/skill
- **`mutation-analyst`** (sonnet) + skill `mutation-testing`: **mutation testing** — measures the real quality of the test suite by introducing mutants and checking whether the tests kill them (a better signal than line coverage). Runs the stack's tool (Stryker, mutmut/cosmic-ray, PITest, Infection), reads the report with `tools/mutation/mutation.py` (`npm run mutation`, a parser for Stryker's standard format), calculates the global and per-file mutation score, lists the surviving mutants and tells the equivalent ones apart. Report with `generate_generic_report.py`.
- **Skill `testing-guide`**: interactive wizard that **the main conversation** uses to guide the user (asks step by step and, based on the answers, recommends or runs the right agent/skill); includes the map from platform and test type to agent/skill. It's a skill (not a subagent) because subagents can't ask questions, just like `performance-guide`.
- Documentation updated to **76 agents / 44 skills**: README, AGENTS.md, CLAUDE.md, skills README, website (ES/EN) with card and skills, regenerated PDF and images, and the dashboard (`reports_portal.py`). Tests: new `test_mutation.py`; `test_integrity.py` covers the additions.

## 2026-10-19 — Observability, search, documents and content/typo reviewer
- **Integrity test** (`tests/test_integrity.py`): verifies that every `npm run`, script and tool an agent mentions exists, that every skill has its folder with the correct name, that every agent has a card on the website and that the agent count is consistent across the README, AGENTS.md and the website (ES/EN). Full project audit: 0 inconsistencies.

Four new families (from 71 to 75 agents, 42 skills):
- **`observability-analyst`** (sonnet) + skill `observability-testing`: validates that the service emits proper **logs** (trace id, no PII), **metrics** (Prometheus RED/USE, cardinality), **traces** (OpenTelemetry), **healthchecks** (liveness/readiness), error tracking, SLOs and that **alerts** fire. Tool `tools/observability/observability.py` (`npm run observability`, healthchecks and `/metrics` over urllib).
- **`search-tester`** (sonnet) + skill `search-testing`: **search and relevance** (Elasticsearch/OpenSearch, Algolia, Solr, DB full-text) — ranking, typos/fuzzy, synonyms, facets, zero-results, indexing, security and a **golden set** with metrics (precision@k, nDCG).
- **`document-tester`** (sonnet) + skill `document-testing`: **generated documents** (PDF/Excel/CSV) — data and totals, **unreplaced placeholders**, format/locale, layout, metadata and security. Tool `tools/documents/documents.py` (`npm run documents`, pypdf/openpyxl).
- **`content-reviewer`** (sonnet) + skill `content-testing`: **content and typos** in the main language — spelling (optional LanguageTool), visible placeholders and i18n keys, duplicated words, Lorem ipsum and microcopy consistency (complements the `translation-analyst`). Tool `tools/content/content.py` (`npm run content`, dependency-free heuristics).
- All of them reuse `generate_generic_report.py`. Wiring: `package.json`, `CLAUDE.md`, `AGENTS.md`, README and skills README, the **dashboard** `reports_portal.py`, and the **website (ES/EN) at 75 agents** with their cards and skills (regenerated PDF and images). Tests: new `test_quality_tools.py`.

## 2026-10-19 — Documentation, website, images, PDF and dashboard sync
Brought everything public and the dashboard up to date with the added agents/skills:
- **Website** (`docs/index.html` + `docs/index.html`): counter at **71 agents**, **18 new agent cards** (prestashop, vtex, sap, desktop, mobile, dependencies, secure code, ai, messaging, soap, contracts, seo, data, dynamics, blockchain, ivr, games, pos) and **21 new skill rows**, in Spanish and English.
- **Images and PDF**: regenerated with `node docs/generate.js` (the 8 diagram PNGs and the 2 ES/EN PDFs, which now reflect the 71 agents).
- **README**: agents table completed with the 18 new rows (the detailed catalog is still in `AGENTS.md`).
- **Central dashboard** (`scripts/reports_portal.py` → `output/index.html`): it already centralized every agent HTML report (auto-discovers `output/`); added the **readable names and order** of the ~18 new platforms (prestashop, vtex, sap, desktop, mobile, ai, messaging, soap, dependencies, sast, contracts, seo, data, dynamics, blockchain, ivr, games, pos, streaming) so they don't show up with a generic name.

## 2026-10-19 — Cross-platform accessibility, server-side chaos and doctor
Improvements to existing agents:
- **Mobile/desktop accessibility**: new skill `accessibility-testing` (a11y on web, mobile and desktop with the WCAG mapping for each platform) and the `accessibility-analyst` now audits **web** (axe-core + Playwright), **mobile** (Appium: accessible labels, touch targets, TalkBack/VoiceOver) and **desktop** (UI Automation with `controls.py`: controls without an accessible name, keyboard, high contrast). The `mobile-tester` hands mobile a11y off to the `accessibility-analyst`.
- **Server-side chaos**: on top of browser-side chaos, the `resilience-tester` adds **real dependency chaos with Toxiproxy** — new tool `tools/resilience/toxiproxy.py` (`npm run toxiproxy`, Toxiproxy's REST API over `urllib`, no dependencies): injects latency, outages and slowness into a database/API/cache and restores them. QA only, confirmed and with `reset` at the end.
- **doctor.py**: checks `pywin32` (SAP GUI Scripting for the `sap-tester`), `pywinauto` (control tree for the `desktop-tester`) and `appium` (mobile and WinAppDriver on desktop), on top of the SCA/SAST tools already included.
- Documentation updated to **38 skills** (skills README, AGENTS.md, CLAUDE.md, `tools/resilience` README, `package.json`). Tests: new `test_toxiproxy.py`.

## 2026-10-19 — Contracts, SEO/GEO, data, gRPC, Dynamics/CRM-ERP, blockchain, IVR, games and POS
Big expansion of domains to "test every kind of project":
- **`contract-tester`** (sonnet) + skill `contract-testing`: contract testing (Pact), consumer-driven and bi-directional, for REST, GraphQL, gRPC and events; provider verification, `can-i-deploy` and compatibility.
- **`seo-analyst`** (sonnet) + skill `seo-testing`: **SEO and GEO** (optimization for search engines and for AI engines). Tool `tools/seo/seo.py` (`npm run seo`, stdlib `urllib`/regex only): on-page, structured data, hreflang, robots/sitemap and AI crawler access (GPTBot/ClaudeBot/PerplexityBot).
- **`data-tester`** (sonnet) + skill `data-testing`: data and pipelines (ETL) — quality by dimension, source↔target reconciliation, schema/drift, transformations, SCD, idempotency and PII; relies on `data-verifier`.
- **gRPC in the API family**: new skill `grpc-testing` (Protobuf, RPC modes, status codes, deadlines, compatibility) wired into `api-runner`, `api-mapper` and `api-case-generator`; **WebSocket** is covered in `async-testing` (`messaging-tester`).
- **`dynamics-tester`** (sonnet) + skill `dynamics-testing`: Microsoft Dynamics 365 and other low-code CRM/ERP (roles, logic —flows/plugins/BPF/roll-ups—, end-to-end processes, read-only Web API + Playwright per role).
- **`blockchain-tester`** (opus) + skill `blockchain-testing`: blockchain/Web3 and smart contracts on testnet/local (functional, tokens, gas, security —reentrancy, access control, oracles, proxies—, Hardhat/Foundry, invariants).
- **`ivr-tester`** (sonnet) + skill `ivr-testing`: voice/IVR and voicebots (DTMF/ASR menu tree, prompts, routing and queues, SIP/VoIP telephony, recording and PCI).
- **`game-tester`** (sonnet) + skill `game-testing`: video games (mechanics, saving, compatibility, performance, multiplayer/anti-cheat, monetization, exploratory testing).
- **`pos-tester`** (sonnet) + skill `pos-testing`: point of sale and hardware (sales flow and cash count, pinpad and peripherals, fiscal, offline/sync, reconciliation).
- New **`scripts/generate_generic_report.py`**: a reusable HTML report (same house style) used by the testers without a report of their own, to avoid duplicating generators. New `tools/seo/` folder.
- Documentation updated to **71 agents** and **37 skills** (README, AGENTS.md, CLAUDE.md, skills README, `package.json`). Tests: new `test_seo.py` and `test_generic_report.py`.

## 2026-10-19 — Messaging/events (async), GraphQL and SOAP
Expanding the coverage of APIs and distributed systems:
- **`messaging-tester`** (sonnet) + skill `async-testing`: tests **asynchronous / event-driven** systems — Kafka, RabbitMQ/AMQP, SQS/SNS, MQTT, WebSocket and SSE. Covers delivery (at-least-once/exactly-once), ordering by key/partition, **idempotency and deduplication**, retries and **DLQ** (poison messages), schemas and compatibility (Avro/JSON Schema), consumer lag and backpressure, the **outbox** pattern and security. Tool `tools/messaging/messaging.py` (`npm run messaging`, publishes/consumes/inspects with lazily imported brokers + pure ordering/duplicate/schema checks) and report `scripts/generate_messaging_report.py`.
- **First-class GraphQL**: new skill `graphql-testing` (schema/introspection, queries/mutations/subscriptions, **partial errors and nullability**, field-level authorization, N+1, depth/complexity, pagination) wired into `api-runner`, `api-mapper` and `api-case-generator`, which already supported it in a scattered way. (Execution still goes through Newman/k0lmena and `summarize_graphql.py`.)
- **`soap-tester`** (sonnet) + skill `soap-testing`: tests **SOAP** services from their WSDL — operations, XSD validation, **SOAP Faults**, namespaces/SOAPAction, SOAP 1.1/1.2, **WS-Security** and idempotency. Tool `tools/soap/wsdl.py` (`npm run soap`, surveys the WSDL and generates the sample envelope; stdlib `xml` only, no dependencies) and report `scripts/generate_soap_report.py`; the envelopes are sent with `api-runner`.
- Documentation updated to **63 agents** and **28 skills** (README, AGENTS.md, CLAUDE.md, skills README and the `tools/messaging` and `tools/soap` READMEs, `package.json`). Tests: new `test_messaging.py` and `test_soap.py`.

## 2026-10-19 — High priority: mobile, static security (SCA/SAST) and AI/LLM
Closing the biggest gaps in "testing every kind of project":
- **`mobile-tester`** (sonnet) + skill `mobile-testing`: tests mobile apps (Android/iOS; native, hybrid or web/PWA) **live with Appium**, beyond the automation generation the `mobile-mapper` already did. Covers permissions (grant/deny/revoke), interruptions, connectivity (offline, slow network), deep links and push, lifecycle (background, rotation, kill/relaunch), OS and screen compatibility, performance and mobile security (OWASP MASVS). Report `scripts/generate_mobile_report.py`; connector `appium`.
- **`dependency-analyst`** (sonnet) + skill `dependency-analysis`: read-only **SCA** (`npm run dependencies`, `tools/security/dependencies.py`) that runs `npm audit`/`pip-audit`/`osv-scanner`, aggregates CVEs by severity, tells direct from transitive and vulnerable from outdated, and flags licenses. Report `scripts/generate_dependencies_report.py`.
- **`secure-code-analyst`** (opus) + skill `secure-code`: read-only **SAST and secrets** (`npm run sast`, `tools/security/sast.py`) with a built-in secret scanner (pure Python, always runs, **redacts** the value) and `semgrep` if available; triages false positives and maps to OWASP/CWE. Report `scripts/generate_sast_report.py`. They complement the **dynamic** analysis (ZAP) of `security-analyst`/`web-pentester`.
- **`ai-tester`** (sonnet) + skill `ai-testing`: tests **AI/LLM** features (chatbot, RAG, classifier, agent) with a golden set and evals: quality and hallucinations, grounding/citations, **prompt security** (direct and indirect injection, jailbreak, system prompt/PII leakage), output format, robustness, latency and cost. Runs against the endpoint (`api-execution`) or the UI (`e2e-execution`). Report `scripts/generate_ai_report.py`.
- New `tools/security/` folder (SCA/SAST, read-only; dependencies imported lazily, degrading with a clear message). `doctor.py` checks `pip-audit`, `osv-scanner` and `semgrep` (optional).
- Documentation updated to **61 agents** and **25 skills** (README, AGENTS.md, CLAUDE.md, skills README and the `tools/security` README, `package.json`). Tests: new `test_mobile.py`, `test_static_security.py` and `test_ai.py`.

## 2026-10-19 — SAP and desktop application agents
- **`sap-tester`** (sonnet): tests an SAP system (S/4HANA or ECC) in a QA client on both fronts — **SAP GUI for Windows** (transactions/T-codes with the Scripting API over COM) and **Fiori/UI5** (launchpad, apps and OData services) — plus **authorizations and roles** (PFCG, SU01, SU53, SoD) and **end-to-end business processes** (Order to Cash, Procure to Pay, Record to Report). Surveys the GUI session read-only (system, client, user, transaction) with `tools/sap/sap_gui.py` (`npm run sap`, Scripting API via pywin32), runs with the Scripting API (GUI), Playwright (Fiori) and the api-runner (OData), and covers smoke, regression after a transport, performance (ST03/ST05) and security. Report `scripts/generate_sap_report.py`, skill `sap-testing`. Never against a production client.
- **`desktop-tester`** (sonnet): tests Windows desktop apps of any technology (WinForms, WPF, UWP/WinUI, Win32, **Electron**, Java Swing/SWT, Qt). Surveys the control tree read-only with `tools/desktop/controls.py` (`npm run desktop`, pywinauto/UI Automation) and automates with **Appium + WinAppDriver** or **pywinauto** (native) or **Playwright** (Electron); covers functional (windows, menus, forms, keyboard, clipboard), installation and updates, files, OS integration (registry, DPI, multi-monitor), smoke, regression, performance (memory, leaks, responsiveness), security (credentials on disk, signing, privileges) and accessibility. Report `scripts/generate_desktop_report.py`, skill `desktop-testing`. On a QA VM, never production.
- Both follow the "no data binary" pattern (like wallets): the agent writes `analysis.json` and the generator renders it with `_report_styles`. The survey tools import their dependencies (pywin32 / pywinauto, Windows only) lazily and degrade with a clear message if they're missing.
- Documentation updated to **57 agents** and **21 skills** (README, AGENTS.md, CLAUDE.md, skills README, the `tools/sap` and `tools/desktop` READMEs). Tests: new `test_sap.py` and `test_desktop.py`.

## 2026-10-19 — More complete e-commerce (smoke, regression, performance, security) + VTEX
- **Coverage by test type**: the hub skill `ecommerce-testing` adds **smoke testing**, **post-deploy regression** (on top of campaign regression), **performance — what to measure in a store** (CWV per page, cache correctness, third parties, N+1, load on the purchase flow) and **store security** (price and quantity tampering, IDOR on orders and invoices, coupon and voucher abuse, webhook signatures, gateway in live mode, exposed admin panel or debug, PII, rate limiting, PCI). Each platform skill (`shopify-testing`, `wordpress-testing`, `prestashop-testing`) adds a section with what's specific to those four types, and the `shopify-tester`, `wordpress-tester` and `prestashop-tester` agents run the **smoke test first** and explicitly hand off performance (`web-performance-auditor`, `performance-mapper`) and security (`security-analyst`, `web-pentester`); their `description` now names the five types (functional, smoke, regression, performance, security).
- **`vtex-tester`** (sonnet): tests a VTEX store. Surveys read-only the storefront (including VTEX IO errors and storefront detection: Store Framework, FastStore or legacy), the **public Catalog System** (the channel's catalog with SKUs, price and availability) and, with a read-only app (`X-VTEX-API-AppKey`/`AppToken`), the sales channels (trade policies), the shipping policies (SLAs) and the promotions; warns if the `master` workspace is being surveyed. Derives and prioritizes the tests (smoke in a QA workspace, checkout/orderForm, sandbox payments, channels, promos and stacking, SKUs and stock, OMS, marketplace) and runs them with Playwright. Tool `tools/ecommerce/vtex.py` (`npm run vtex`), reuses `_common.py` and the `scripts/generate_ecommerce_report.py` report, and the `vtex-testing` skill.
- Documentation updated to **55 agents** (README, AGENTS.md, CLAUDE.md, skills and ecommerce READMEs, `.env.example` with the VTEX block). Tests: new VTEX cases in `test_ecommerce.py`.

## 2026-10-19 — E-commerce agent: PrestaShop
- **`prestashop-tester`** (sonnet): tests an authorized PrestaShop store (1.6, 1.7, 8.x), focused on functional/E2E QA, performance and smoke testing of a local installation. Surveys read-only the storefront (key pages, visible PHP errors or PrestaShop exceptions, product JSON-LD) and, with a read-only **Webservice API** key, the products with stock and combinations, carriers (and whether any is active), zones, currencies, languages, cart rules (vouchers), shops (multistore) and the key QA and performance settings (maintenance mode, catalog mode, HTTPS, Smarty and compilation, CSS/JS combine-compress-cache, guest checkout, rounding, taxes, terms); with `--local` it reads the version and whether `_PS_MODE_DEV_` was left on. Derives suggestions (local smoke, checkout and test payments, carriers and zones, combinations and stock, rounding and taxes, performance, multistore and multi-language) and runs them with Playwright on mobile and desktop. Tool `tools/ecommerce/prestashop.py` (`npm run prestashop`), reuses `_common.py` and the `scripts/generate_ecommerce_report.py` report, and the `prestashop-testing` skill. It's functional: store security is left to `security-analyst` and `web-pentester`.
- Documentation updated to **54 agents** (README, AGENTS.md, CLAUDE.md, skills and ecommerce READMEs, `.env.example` with the PrestaShop block). Tests: new cases in `test_ecommerce.py`.

## 2026-10-19 — E-commerce agents: Shopify and WordPress / WooCommerce (2)
- **`shopify-tester`** (sonnet): tests an authorized Shopify store. Surveys read-only the storefront (key pages, published theme, Liquid errors and missing translations, legal policies, `/products.json`, `/cart.js`, product JSON-LD) and, with a `read_*` token for the GraphQL Admin API (mutations are rejected before being sent), the store (whether it's a development store, plan, currencies, taxes), themes, products with variants and stock, locations, markets, shipping profiles, discounts, webhooks and the token's scopes; with `--theme-check`, Theme Check on the theme code. Derives suggestions (checkout with Bogus Gateway, discounts, markets, shipping, variants, webhooks with HMAC) and runs them with Playwright on mobile and desktop. Tool `tools/ecommerce/shopify.py` (`npm run shopify`).
- **`wordpress-tester`** (sonnet): tests an authorized WordPress site or WooCommerce store. Surveys read-only the storefront (key pages, PHP errors or the WordPress critical error, `/wp-json` modules, Store API catalog) and, with a read key for the WooCommerce REST API, the system status (database pending update, cron, outgoing calls, outdated plugins, old theme templates, WooCommerce pages), gateways and whether they're in test mode, shipping zones and methods, coupons, disabled webhooks and products with backorders; with `--wp-cli`, updates and overdue cron. Tool `tools/ecommerce/wordpress.py` (`npm run wordpress`).
- Shared: `tools/ecommerce/_common.py` (authorization through `ECOMMERCE_AUTHORIZED_URLS`, storefront checks and catalog analysis: zero price, no image, overselling, strikethrough price, no SKU, no tax), the `scripts/generate_ecommerce_report.py` report with the run evolution, and the `ecommerce-testing`, `shopify-testing` and `wordpress-testing` skills. They're functional: store security is left to `security-analyst` and `web-pentester`. The doctor warns if the Shopify CLI or WP-CLI (optional) are missing.
- Documentation updated to **53 agents** (ES/EN website, README, AGENTS.md, CLAUDE.md, .env.example with the e-commerce block). Tests: new `test_ecommerce.py`.

## 2026-10-19 — Salesforce, wallets/tokens and project researcher agents (3)
- **`salesforce-tester`** (sonnet): tests a Salesforce **sandbox** org. Surveys read-only with the `sf` CLI (profiles and users per profile, permission sets, record types, validation rules, active flows and Process Builder, triggers, Apex coverage, OWD/sharing, duplicates, approvals and limits), computes findings (coverage < 75 %, retired Process Builder, several triggers per object, open OWD) and test suggestions (negative per validation, 200-record bulk per trigger, flows per path, access per profile, record types), runs the Apex tests with `--apex`, runs per profile in Lightning with Playwright and verifies through read-only SOQL. Never production (it detects it and stops), doesn't touch metadata or permissions. Tool `tools/salesforce/inventory.py` (`npm run salesforce`), report `scripts/generate_salesforce_report.py`, MCP connector `salesforce` (read-only SOQL + `run_apex_test`), skills `salesforce-testing` and `token-testing`. The doctor checks the `sf` CLI.
- **`wallet-tester`** (sonnet): tests digital wallets, fintech and payments in **sandbox**, with the rule "money is neither created nor destroyed". Covers balance conservation and the ledger, transaction statuses, **idempotency**, **double spending/concurrency**, rounding and currency, limits, KYC/AML, reconciliation with the gateway, signed webhooks and the security of tokens and card tokenization (PCI). It has no binary of its own: it runs with `api-runner`, Playwright, `data-verifier` (balances through read-only SQL) and `resilience-tester`; report `scripts/generate_wallets_report.py`. Test money and cards, never real ones; it doesn't edit data. Skills `wallet-testing` and `token-testing`.
- **`project-researcher`** (sonnet): surveys the **whole** project over MCP for a QA who's new to it. You can give it the **URL of a board** (Jira, Azure DevOps, Trello, Linear, monday, ClickUp, Notion, GitHub/GitLab Projects board or dashboard) and from there it **walks down the hierarchy**: epics → stories → tasks/subtasks → comments → **reference links** (Confluence, Figma, docs, repos; one level deep). It sweeps read-only Jira/Confluence, Azure DevOps (Boards, Wiki, Repos, Test Plans), GitHub/GitLab and Figma (sampled backlog, bugs, sprints, releases, wiki, README), extracts a summary, the **epics/stories/tasks tree it walked** and the **links it collected**, modules with progress, actors, flows, integrations, environments, team, decisions, backlog status, glossary and timeline, and detects **ambiguities and contradictions** (`AMB-XX`, with their sources) that it turns into **prioritized questions** (`Q-XX`) for the team. It delivers a **package**: an HTML site with **concept maps** (architecture and how it works, as self-contained SVG) and charts, `research-report.md`, a short **`summary.md`** and a self-contained **`research-presentation.html`** (←/→ and prints to PDF, one slide per page), with the walk, clickable links and a comparison against the previous survey (`scripts/generate_research_report.py`). Skills `project-survey` and `context-research`.
- **4 new skills**: `project-survey`, `salesforce-testing`, `token-testing` (reusable, also by the `web-pentester`) and `wallet-testing`.
- Documentation updated to **51 agents** (ES/EN website, diagrams, README, AGENTS.md, CLAUDE.md, .env.example with the Salesforce and wallets blocks). Tests: new `test_salesforce.py`, `test_wallets.py` and `test_research.py`.

## 2026-10-18 — SECURITY.md and documented dependency risk
- New `SECURITY.md`: the project's security scope, secrets handling, and the 39 transitive `npm audit` vulnerabilities that remain as **accepted risk** (they come from dev/test tools and their "fix" would break the framework). Documents why the risk is low in this context, how they'll be resolved when upstream publishes the patches, and sets the next review: **2026-11-18**.

## 2026-10-18 — k0lmena dependencies up to date
- Updated to their latest compatible version: `@playwright/test` 1.64.1, `@types/node` 26.6.5, the WebdriverIO 9.32.x stack, `dotenv` 18, `js-yaml` 5, `axe-core` 4.14.0, `mssql` 12.7.9, `mysql2` 3.24.6; and the MCP servers `appium-mcp` 1.97.1 and `mcp-remote` 0.15.1. `dotenv/config` was replaced with an explicit `config()` (dotenv 18 changed how types are resolved).
- **Kept on purpose**: TypeScript on 6.x (TS 7 is the native rewrite and breaks `ts-node`, which the whole framework depends on) and the WebdriverIO stack on 9.x (`@wdio/browserstack-service` doesn't have 10 yet). They'll be upgraded when the ecosystem (ts-node / browserstack-service) catches up.
- Verified with `npm run test:repo` (80/0), `pytest` (320) and `tsc --noEmit`.

## 2026-10-17 — Model per agent (token savings)
- Every agent sets its `model:` in the frontmatter to avoid overspending: `haiku` for the mechanical ones (they run a script and build the JSON/HTML), `sonnet` for most QA work and `opus` only for the ones that reason the most or are sensitive (story-analyst, security-analyst, web-pentester). The criteria are documented in `CLAUDE.md`; the real cost per agent is measured by `scripts/token_metrics.py`.

## 2026-10-17 — Automation savings on the dashboard
- The quality dashboard calculates the **time saved by automating**: the estimated manual execution time of the automated cases minus how long they take running on their own (`npm test`). It shows the **savings per run** and the **cumulative** savings for the period in the indicators, and a savings column per story. It uses the manual time that was already stored per case and the real duration of the last run.

## 2026-10-17 — Priority in BDD and pentest agent
- **Priority tag in BDD**: scenarios carry `@critical`/`@high`/`@medium`/`@low` (the equivalent of the *Priority* column in manual cases). `scripts/management/readers.py` reads it (an explicit tag wins; `@smoke` still counts as `High`); the mappers keep that tag in the `.feature` files they generate. Before, a "Critical" case reached the management tool as "Medium". The estimated manual execution time was already stored (*Estimated time (min)* column in manual cases; calculated with `estimation.py` in BDD), the basis for measuring automation savings.
- **New `web-pentester` agent** (authorized ethical hacking): tries to break into a site that is **your own or with written permission** with the OWASP ZAP active scan plus manual verification of the OWASP Top 10 (access control, authentication, injection, XSS, configuration, CSRF/SSRF) with Playwright MCP, confirms each finding and delivers the HTML report (active mode) plus a `pentest-report.md` with steps to reproduce and the fix. Only URLs in `SECURITY_AUTHORIZED_URLS`, with `PENTEST_AUTHORIZED=yes`, never production without authorization and without destructive techniques (DoS, mass brute force, data deletion).
- `tools/zap/scan.py` adds `--active` (full scan, gated by authorization) and `generate_security_report.py` tells a passive report from an active one (`--mode`).

## 2026-10-17 — Agent quality review
- **No false greens**: a `Then` that fails because the app doesn't comply is no longer marked `@blocked` in web-mapper and mobile-mapper (`npm test` never ran it and the bug stayed hidden): it stays active with `# POSSIBLE BUG`. A Newman request without `pm.test` comes out *Blocked* ("No assertions"), not *Passed*.
- **Traceability**: manual cases keep the `TC-XXX` IDs the story already had (BDD, automation, management); a `Scenario Outline` is a single case; `TC-API` is numbered per story or contract. The closure report and the dashboard tell the same `TC` from two stories apart (story + ID key) and also take `npm test` results from `history/`. The rule for US versus the tool's key is now in *ID conventions*.
- **Missing info** with a single format (`{id, what_is_missing, question}`) in every HTML report; test data and API cases no longer assume rules: they flag them as `MI-XX`.
- **Self-review before delivering** in the generators and analysts, and the report scripts warn on stderr about IDs or severities in `analysis.json` that don't exist.
- **Side effects and security**: the API runner confirms methods with side effects; the mappers never run against production; `--submit-empty` presses the right form's button; the security report masks secrets in the ZAP evidence.
- **Fixed references**: the publisher's `--dry-run` before the subcommand, `--repo` required in the selector (diff from the merge base), pixel-perfect's `--accept` with its `--url`, failure retries per suite, `run_newman.py --data`, `format_tables.py` with its file, estimation with labels as text, closed statuses in the triager, case and coverage templates without assumptions presented as facts.
- `npm run debug` leaves its reports in `reports/debug/` (they no longer mix with the web report) and the web mappers' validation uses `REPORT_DIR=reports/validation` so it doesn't overwrite the last `npm test`.

## 2026-10-17 — npm test builds the full report
- `npm test` now generates on its own, when each web and API suite finishes, the full k0lmena report (`reports/<suite>/index.html`, the one from `npm run report:web` / `report:api`). Before, only Cucumber's basic HTML (`front-report.html`) was left, and that was the one the reports portal linked to after automating with the `web-mapper`.
- The portal shows a single entry per suite with the full report (the basic one stays as "other" and the `features/` pages don't show up as separate reports); the history also stores the full report of each run.

## 2026-10-16 — npm run configure
- **`npm run configure`**: a wizard to get the project ready without knowing variable or connector names. It asks for the app's URL and the test user, where the stories live, where you keep the cases, where the code is and whether you use Figma (numbered options); it asks only for the details of what you chose (tokens aren't shown), writes them to the `.env` (creating it if it doesn't exist) and enables the connectors. It can be run again: Enter keeps what was already there. `npm run connector` remains for one-off changes.

## 2026-10-16 — APIs from a Swagger that actually work
- `scripts/summarize_openapi.py`: summarizes a Swagger 2.0 or OpenAPI 3.x spec (JSON or YAML, by URL or file) with the correct `API_BASEURL` (server + basePath, relative servers and servers with variables), the authentication step for each `securityScheme`, parameters, a sample body (JSON, form or multipart) and documented statuses. The `api-case-generator` and the `api-mapper` use it instead of reading the spec by hand.
- API steps (`api/steps/common.steps.ts`): URL joined with a single slash (before: `/v2/v2/pet` or `hostpet`), API key in header or query, basic authentication, query parameters, forms (`with the form:`), plain-text responses, finding an element in a list, the spec's types (`integer`, …), int64 ids without losing precision, per-request timeout, `{variables}` without a value that stop with a clear message, and every credential hidden in the report. The steps that already existed keep their text.
- Unique data per scenario: `{random}`, `{uuid}`, `{timestamp}` and `{now}`.
- The `api-mapper` verifies every `Then` against the API, makes each scenario create the data it reads and marks `@differs-from-spec` when the API doesn't follow the spec (to separate bugs from badly written tests). The `api-case-generator` only uses the contract's statuses.

## 2026-10-16 — Cross-browser without false positives and the URL in a single place
- **Cross-browser**: whatever fails in only one browser is confirmed before being reported. In suite mode, the scenario is repeated in that browser (`--retries`, 2 by default) and if it passes it's marked *Flaky*; in pages mode, the page is reloaded in every browser and intermittent issues drop to *Low* or are discarded.
- Errors are compared by their origin (file:line:column) and their own words, because each engine words the same error differently (before, an error from every browser showed up as "Firefox only"). Each engine's console noise is ignored, resources are compared without the query string and without the favicon, and what one browser requested and the others didn't weighs less.
- No scrollbars when comparing (Firefox draws them taking up width), colors normalized to sRGB (oklch and other formats), shifts caused by text measurement in *Low* unless something ends up off screen, "missing" elements that were there with the same text, and Firefox on mobile (it doesn't emulate a phone) with its visual differences in *Low*.
- The agent no longer tries to reproduce in Firefox with Playwright MCP (it opens Chromium): it uses the script or the suite with `BROWSER=firefox`.
- **The app URL goes only in `APP_URL`**: k0lmena builds `BASEURL` from it (`env.js`); `BASEURL` in the `.env` remains as a legacy name and `npm run doctor` warns if it's redundant or doesn't match.

## 2026-10-16 — Saved session with npm run login
- `npm run login` (k0lmena `tools/login`): opens the browser, you log in by hand (captcha, 2FA or SSO included) and it saves the session (cookies, localStorage and IndexedDB) in `.auth/` (gitignored). `--name <role>` saves one per role.
- With `SESSION=yes` (or `SESSION=<role>`) in the `.env`, the k0lmena web suites and the agents' browser (Playwright MCP, with `--isolated --storage-state`) start logged in. `@no-session` scenarios start without a session.

## 2026-10-14 (3) — k0lmena style on the website, diagrams, PDF and reports
- The documentation website, the diagrams (and their images), the PDF and every HTML report (the Python ones and the k0lmena reports) use the https://k0lmena.com style: night and charcoal background, amber, honey and orange, honeycomb pattern, `// section` labels and hexagonal bullets.
- Embedded k0lmena typography: Saira (headings), Inter (text) and JetBrains Mono (code), under the OFL license (`docs/assets/fonts/` and `scripts/fonts/`); they replace Geist.
- Warm chart palette validated for contrast and color blindness; statuses use green, honey, orange and warm red.
- The website starts in dark mode (optional warm light theme) and the PDF comes out with the same dark style.
- New diagram `docs/assets/img/relationships.png`: how agents, skills, templates, scripts, tools and MCP connectors relate to each other (in the README, the website and `ARCHITECTURE.md`).

## 2026-10-14 (3) — Search, English version, portal with filters, doctor, onboarding and token usage
- **Website with search** (Ctrl K or /): results by section with the term highlighted, accent-insensitive, keyboard navigation and a jump to the exact spot.
- **English version** of the website (`docs/en/`), the diagrams and the PDF (`docs/k0lmenIA-documentation.pdf`), with a language switcher.
- **Reports portal with filters**: search box, filters by tool, story, status and date, and a per-story view.
- **More complete `npm run doctor`**: by section (also fonts, `.env` integrations, git, workflows and the Claude CLI), with `--section`, `--quick` and `--json`; it never shows secrets.
- New `onboarding-guide` agent: onboarding plan for a new QA with the product, its environment, the agents for their role, the first tasks, questions and a checklist (`scripts/generate_onboarding.py`).
- **Token usage** (`npm run metrics`, `scripts/token_metrics.py`): estimated cost per agent, day and model from the Claude Code transcripts, with savings opportunities; the quality dashboard includes it.

## 2026-10-14 (2) — Permissions, resilience, triage, questions, dashboard, notifications, monitoring, evals and more sources
- New `permissions-tester` agent: `npm run permissions` logs in with each role (plus anonymous) and builds the role × route and role × endpoint matrix, with access by direct URL, menus and buttons visible per role and differences from the documented rule. GET only.
- New `resilience-tester` agent: `npm run resilience` intercepts the network from the browser (API with 500/503/404, timeout, slow network, offline, empty, broken or null-filled responses, static files that don't load) and checks for blank screens, silent failures, endless spinners, technical messages, retries and recovery.
- New `bug-triager` agent: looks for duplicates and possible regressions in Jira, Azure DevOps, the local bugs and the repository issues (`scripts/find_duplicates.py`) and suggests severity, component, assignee and story. The `bug-report-generator` suggests it before you file a bug.
- New `project-consultant` agent: answers product questions using only the project documentation, citing the source or saying it isn't documented.
- New `quality-dashboard` agent: dashboard per sprint or release (passed and trend, % automated, coverage, bugs, flaky tests, manual time) with a management summary.
- **Reports portal**: `output/index.html` with the latest report from every tool; it regenerates itself when any report finishes.
- **Incremental documentation**: the `project-documenter` stores the status of what it documented (`.status.json`), redoes only what changed and lists in `changes.md` the cases to review (`scripts/documentation_changes.py`).
- **Slack and Teams notifications** through webhooks (`scripts/notify.py`, `npm run notify`), with an `npm test` summary.
- Read-only **synthetic monitoring** (`npm run monitor`): URLs, texts, times, certificate and `@synthetic` scenarios; notifies when something breaks or recovers; schedulable workflow `.github/workflows/monitoring.yml`.
- **Agent evals** (`evals/`, `scripts/evaluate_agents.py`, `npm run evals`): cases with deliberate traps, deterministic checks, an isolated workspace with `claude -p` and a report with regressions; manual workflow `.github/workflows/evals.yml`.
- **APIs**: GraphQL (generic steps in k0lmena, `scripts/summarize_graphql.py`, GraphQL cases in the generator) and Bruno and Insomnia collections (`scripts/convert_collection.py`, which `run_newman.py` uses automatically), with demos in `input/api/`.
- **More management tools**: official MCP connectors for Linear, ClickUp, monday.com, Asana, Trello, Notion, YouTrack and Shortcut as story sources; the `context-research` skill includes each tool's field equivalences.
- The tests don't touch the portal (`K0LMENIA_PORTAL=0`).

## 2026-10-14 — Project documenter and repository connection
- New `project-documenter` agent: builds the project documentation in `input/documentation/` so the rest of the agents work with real context. It reads the application repository read-only (README and docs, validations and limits, messages, statuses, roles and permissions, routes, API contracts and the PRs and commits of each story), the Jira or Azure DevOps stories with their comments, subtasks, epic, links and URLs (Confluence, Wiki, Figma and public pages; private ones are recorded as *Not accessible*) and the website. It produces a project base, a dossier per story and an index; every fact with its source.
- **Application repository** in the `.env` (`REPO_PROVIDER`, `REPO_NAME`, `REPO_BRANCH`, `REPO_LOCAL_PATH`) with each provider's official MCP servers: new connectors `github` (remote, read-only mode, `GITHUB_TOKEN`) and `gitlab` (`/api/v4/mcp`, OAuth or `GITLAB_TOKEN`) in the catalog; Azure Repos with the `repositories` domain, which now comes by default in `azure-devops`; Bitbucket Cloud with the `atlassian` connector and token authentication.
- `npm run functional-map` (k0lmena `tools/functional-map`): crawls the site with GET only and documents each page (sections, menus, forms with every field and its constraints, buttons, messages and tables), without submitting anything. Reuses pixel-perfect's page discovery and the form field extraction.
- `scripts/documentation_index.py`: index of `input/documentation/` with the type, sources, date and whether each document should be reviewed.
- The `context-research` skill reads the project documentation first (the index and the story dossier), so every agent that researches a story benefits from it; the repository code counts as *observed*, not as a requirement.
- `input/documentation/` is no longer versioned (it may contain code and the client's internal information).
- `npm run connector -- activate` takes a connector's URL variables from the `.env` (`GITLAB_URL`, `K0LMENA_TMT_URL`).

## 2026-10-11 (5) — Case reviewer, charters, UX, forms, logs and execution time
- **Estimated manual execution time** for each case (`scripts/estimation.py`, formula in `templates/time-estimation.md`): *Estimated time (min)* column with the total in the case spreadsheet and in the `.md`; when uploading to the management tool it goes in the description and in the native field (Original Estimate in Xray Cloud and Server/DC, estimatedTime in QTM4J, estimatedEffort in AIO Tests; if it's rejected, the case is created without it); for Azure DevOps in the JSON and as a tag. A value entered by hand in the spreadsheet overrides the formula.
- New `case-reviewer` agent: score per case, vague results and steps, duplicates, scenarios without a Then or written imperatively, stories without negative cases, execution time and improved versions.
- New `charter-generator` agent: session-based exploration charters, printable sheets, a notes template and the sessions report (bugs, questions, time split, areas covered).
- New `ux-evaluator` agent: `npm run ux` with Nielsen's 10 heuristics on desktop and mobile, the 404 page and manual review of the flows.
- New `form-tester` agent: `npm run forms` tests every field without submitting (it blocks any submission) and builds the field × test matrix.
- New `log-analyst` agent: groups log errors by signature, the timeline and the cross-reference with the failed scenarios; the common k0lmena steps record the start and end of each scenario.

## 2026-10-11 (4) — Emails, translations and run history
- New `email-verifier` agent: with Mailpit as a test mailbox (`tools/mailpit/`), `npm run emails` checks per case that what's expected arrives (recipient, subject, texts, links, attachments), unreplaced variables, broken or localhost links, images, plain text, size, HTML compatibility with email clients (Mailpit's html-check) and how it looks on desktop and mobile. Email steps for the k0lmena `.feature` files (`tools/emails/emails.steps.ts`).
- New `translation-analyst` agent: `npm run translator` crawls every page in every language (hreflang, URL template or browser language) and detects untranslated text, visible keys, badly encoded characters, truncated or overflowing text, numbers and dates from another region and the lang attribute.
- **Run history**: every tool keeps its last 5 runs with the evidence in `history/` (and `npm test`, in `reports/<suite>/history/`); the reports add "Run evolution" with what's new, what was resolved, the indicators over time and the link to each previous report.
- Line charts: with few points they mark each one and the end labels are no longer cut off.

## 2026-10-11 (3) — Pixel perfect, cross-browser, repairer and case selector
- New `pixel-perfect` agent: `npm run pixel-perfect` takes a baseline of every page at every resolution (or uses a Figma design) and compares pixel by pixel and element by element: what shifted and by how many pixels, displaced blocks with their cause (what appeared or grew above them), changes in size, text and style, missing and new elements. Stable capture (no animations, with fonts and images loaded and dynamic areas hidden). Report with a baseline/current slider comparator, a difference map and the before and after of every finding.
- New `cross-browser` agent: `npm run cross-browser` runs the k0lmena web suite in Chromium, Firefox and WebKit (each browser in its own folder, without overwriting the last `npm test`) and separates what fails only in some of them from what fails in all of them; without automation, it crawls the pages and compares them against the base browser (exclusive JavaScript and console errors, resources, overflow, elements and styles).
- New `automation-repairer` agent: `npm run repair` extracts from the error the locator that failed, tests it against the saved DOM, diagnoses it (no longer exists, matches several, not visible, the wait failed), proposes a unique and robust locator, applies it with a backup and a diff and verifies the scenarios. It doesn't change a test to cover up a bug.
- New `test-case-selector` agent: `scripts/select_cases.py` cross-references a change (git, PR, Jira, release notes) with the manual, BDD and automated cases and builds the selection by risk (must-run, recommended, minimal regression) with the `npm test` command and the uncovered changes.
- k0lmena: the web suite saves the page DOM on failure (`reports/web/dom/`), `REPORT_DIR` also moves Cucumber's JSON and HTML report, and the `failure-analyst` collects the DOM and URL of each failure.
- Fix: with empty `VIEWPORT_WIDTH`/`VIEWPORT_HEIGHT` the browser window ended up at 0x0 (clicks failed with "outside of the viewport"); it now uses 1366x768.

## 2026-10-11 (2) — Bento-style reports with navigation
- Every HTML report (the 10 Python reports, the one for each `npm run perf` run and the Cucumber report theme) moves to a dashboard-style design: a sidebar with the report's table of contents that highlights the section being read, a header with search (Ctrl K) and a bento grid.
- Embedded Geist and Geist Mono typography (`scripts/fonts`, OFL license): they look the same on any machine and offline.
- Cards with a gradient border, indicators with a status label, glow and a progress bar or sparkline; columns and bars with gradients, donuts with proportion bars in the legend, glowing lines and a new semicircular gauge.
- Long tables automatically get a search box, filters by severity, status or type (with a counter) and sorting by clicking the header.

## 2026-10-11 — Web performance, failure analysis and coverage
- New `web-performance-auditor` agent: Lighthouse 13 on mobile and desktop (localized texts) with `npm run web-performance`. Scores, lab Core Web Vitals with Google's thresholds, opportunities with the estimated savings and the resources causing them, LCP element, weight by resource type, third parties, loading sequence and each page's native report.
- New `failure-analyst` agent: `scripts/analyze_failures.py` classifies the `npm test` failures (possible bug, locator or wait, environment, data, automation error, undefined step), detects the flaky ones by comparing with retries and collects the screenshot, video and trace; the agent confirms the cause and writes up the real bugs.
- New `coverage-analyst` agent: `scripts/analyze_coverage.py` builds the US → criteria → cases → automation → management → result → bugs matrix and flags the gaps.
- All three with their HTML report in the new design, documentation, permissions and tests.

## 2026-10-10 (4) — Redesign of every report
- New design system (`scripts/_report_styles.py`) for the 7 HTML reports (plan, run, closure, performance, security, exploratory and accessibility): wider (up to 1480px), cards with the title inside, indicators with icons based on what they measure and the status as a symbol (✓ ✕ ! ⊘), never color alone, tables with a highlighted header and aligned numbers.
- New charts: smooth curves with a gradient area and labels only on the maximum and the last value, columns with the value at the tip, donuts with a legend of values and percentages, bars over a faint rail. New categorical palette led by teal (#14A895), validated for color blindness and contrast with the dataviz skill's script; the status colors don't change.
- Same design in the report for each `npm run perf` run (k0lmena) and in the Cucumber report theme (`npm test` web, API and mobile).
- Fix: the duration of a performance run no longer shows "3m 60s".

## 2026-10-10 (3) — Accessibility
- New `accessibility-analyst` agent: audits WCAG 2.2 (AA by default) and reviews by hand with Playwright MCP what a tool can't judge (alternative texts, headings, forms and errors, menus and modals with the keyboard, screen reader). It never claims conformance.
- `npm run accessibility` (`tools/k0lmena/tools/accessibility/audit.js`): axe-core 4.13 with localized texts, Tab navigation (non-visible focus, focus traps, skip to content) and reflow at 320px; a screenshot of every page and of every failing element, and video. Each run replaces the previous one in `output/accessibility/<US or host>/`.
- `scripts/generate_accessibility_report.py`: HTML report with compliance, failed WCAG criteria (name and level), every issue with its elements, screenshots and how to fix it, keyboard and focus order, manual review and recommendations.

## 2026-10-10 (2) — Exploratory testing
- New `web-explorer` agent: crawls the site (`APP_URL` from the `.env` or the requested URL) looking for broken links and images, JavaScript and console errors and failing resources; checks responsive behavior on mobile, tablet and desktop (horizontal scroll, small text, small touch targets per WCAG 2.5.8, meta viewport) with screenshots; and explores by hand with Playwright MCP.
- `npm run explore` (`tools/k0lmena/tools/explorer/explore.js`): the automated crawl, with no tokens per page. GET only: it doesn't submit forms or follow logout links. It separates broken links from unverifiable ones (403, 429, timeouts).
- `scripts/generate_exploratory_report.py`: dark-mode HTML report with indicators, charts, every finding with its screenshot (click to enlarge), load times, responsive matrix, videos, galleries, broken links, per-page details and the manual exploration. `npm run explore` generates it automatically when it finishes.
- Full evidence: a screenshot of every page and every resolution with the issues marked in red, and video of the crawl and of each resolution. Each run replaces the previous one in `output/exploratory/<US or host>/`.

## 2026-10-10 — Direct startup, connectors on demand
- Claude Code starts without asking you to approve connectors: `.mcp.json` only includes the ones enabled for everyone (Playwright and Atlassian).
- The optional ones (Azure DevOps, Figma, QMetry, QTM4J, AIO Tests, k0lmenaTMT, Appium) move to `scripts/mcp/catalog.json` and each person enables their own with `npm run connector -- activate <name>` (Claude Code local scope: only for that person, without touching versioned files).
- `npm run doctor` also checks the connectors enabled this way. Tests guarantee that everything in `.mcp.json` comes enabled.

## 2026-10-09 (3) — Functional verification
- `run_newman.py` honors the `base_url` of the environment or the collection; `API_BASEURL` from the `.env` is used only if they don't define it (the demo ended up hitting Petstore).
- `npm run doctor` accepts Xray Server/DC with user and password, and Azure DevOps without a PAT (interactive login or `az login`).
- `npm run perf` warns if the same script name exists in two tools, instead of silently picking one.
- `npm run test:repo` also works with Node 20.

## 2026-10-09 (2) — Full review: robustness, security, tests and documentation

**Fixes**
- Six agents (analysis, case, data and bug generators) can now read Jira, Azure DevOps, Confluence and Figma: their tool list was restricted.
- No agent is left waiting for an answer: if a piece of data is missing, it finishes and returns "I need you to confirm"; the main conversation asks and continues it.
- BDD scenarios carry `@TC-XXX`: the BDD → automation → management → results traceability no longer breaks. `@smoke` always in lowercase.
- Results published per story: a `@TC-001` from another story is no longer loaded into the wrong case.
- Retries on 429/5xx resend the full evidence (before, it could be uploaded empty); network drops are retried.
- `upload-cases` records each case as soon as it creates it: if the link fails, it isn't duplicated and the link is retried.
- The closure report adds up every source (live runs, `npm test`, bugs, performance and security) with `scripts/collect_results.py`; the bug template adds Story, Status and Priority.
- The `.feature` reader keeps `Examples` with tags and supports `Rule`.
- Three agents (manual-case-generator, closure-report-generator and performance-mapper) didn't load: their description had an unquoted ": " and the YAML was invalid. A test now validates the header of every agent and skill.

**Security**
- MCP servers with pinned versions (no `@latest`) and Playwright with `--secrets .env`.
- Databases with SSL: the certificate is verified (`no-verify` is explicit); `DB_<NAME>_SSL_CA` for custom CAs.
- k6 is downloaded verifying its SHA-256; validation of keys, stories and paths in the scripts.
- Project permissions: read-only and generation commands are allowed; anything that writes outside still asks for confirmation.

**New**
- `npm run doctor`: checks the environment and tells you what's missing.
- `scripts/run_newman.py`: runs collections with the token and the URL from the `.env` on any system.
- Repo tests (pytest and node --test) and CI on GitHub Actions (Ubuntu and Windows).
- `LICENSE`, this `CHANGELOG` and `input/README.md`.

## 2026-10-09 (1) — New integrations and reports
- Redesign of every report: modern dark mode, validated palettes and charts with tooltips.
- Every connector ready (Jira, Azure DevOps, Confluence, Figma, QMetry, AIO Tests, k0lmenaTMT, Xray) and Jira enabled by default.
- Web security with OWASP ZAP (passive scan) and its report.
- JMeter in performance, a step-by-step test guide and a final report.
- Azure DevOps (Boards, Test Plans, Wiki) and credentials for every connector read from the `.env`.

## 2026-10-08
- k0lmenaTMT connector; context research and "Missing info" (`MI-XX`).
- data-verifier agent and database checks.
- Documentation site (GitHub Pages), PDF and diagrams.
- performance-mapper and the k0lmena performance runner.
- Integration with Xray, QMetry (QTM4J) and AIO Tests; GIF as evidence.
- Integration of k0lmena and the web-mapper, api-mapper and mobile-mapper agents.
- The project is renamed k0lmenIA.

## 2026-06
- First versions of the QARMY agents: analysis, cases, data, bugs, API, test plan and final report.
