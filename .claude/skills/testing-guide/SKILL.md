---
name: testing-guide
description: Interactive assistant that guides the person to choose what to test and with which k0lmenIA agent or skill, asking step by step and recommending (or running) based on the answers. Used by the main conversation (not a subagent, because subagents can't ask questions) when the person doesn't know where to start, asks for a recommendation of test types, or wants to be guided. Includes the platform map (web, REST/GraphQL/gRPC/SOAP API, mobile, desktop, e-commerce, SAP, Salesforce, Dynamics, AI/LLM, blockchain, IVR, games, POS, messaging) by test type (functional, exploratory, smoke, regression, performance, SAST/SCA/DAST security, accessibility, visual, cross-browser, UX, i18n, content/typos, contracts, data, observability, search, documents, mutation, resilience) to the corresponding agent or skill, the suggested question flow and how to always start from the project context. The main conversation uses it to build a short plan and run what was agreed.
---

# Testing guide (assistant for choosing an agent/skill)

This skill is used by **the main conversation** (not a subagent: subagents can't ask questions) to **guide the person** when they don't know what to test or with which agent/skill. The flow is: **ask little and specific → recommend the minimum set → run what was agreed**, always starting from the project context.

## 1. How to conduct the guide

- **First look at the context**, don't ask what is already known: `input/documentation/` (built by the `project-documenter`), the `.env` (APP_URL, which connectors there are), a Jira/US key if there is one, and whatever the repo reveals.
- **Ask with options** (use multiple-choice questions, with a recommended one), one or two at a time; branch based on the answer. Don't dump all 76 options: narrow it down.
- **Recommend the minimum set** that covers what the person needs (not the whole catalog), and explain why each one.
- **Offer to run it**: invoke the recommended agent/skill. Before anything with a side effect (test orders, writes, load, installs), confirm and pass the agent what you already settled (headed/headless, URL, story…).
- The **full catalog** (what each agent does, what it confirms) is in `AGENTS.md`; it is the source of truth.

## 2. Typical questions to branch on

1. **What do you want to achieve?** — test a specific story/feature · a regression before a release · a product quality survey · a quick smoke · investigate a bug.
2. **What type of project / platform is it?** — web · API · mobile · desktop · e-commerce (which one?) · SAP/Salesforce/Dynamics · AI/LLM · other.
3. **Which dimension are you worried about?** — functional · performance · security · accessibility · visual · data · etc. (you can suggest several).
4. **Is there a story/criteria?** (to derive cases with context) **QA environment and credentials?**
5. Depending on the case: **headed or headless?**, **which browsers/devices?**, **is the gateway in test mode?**, etc.

## 3. Map: test type → agent/skill

```
+--------------------------------+------------------------------------------------------------+
| You want to…                   | Use                                                        |
+================================+============================================================+
| Plan the strategy              | test-strategist (plan) · testing-guide (this one, to       |
|                                | choose)                                                    |
+--------------------------------+------------------------------------------------------------+
| Write cases (manual/BDD)       | manual-case-generator · bdd-case-generator                 |
+--------------------------------+------------------------------------------------------------+
| API cases                      | api-case-generator                                         |
+--------------------------------+------------------------------------------------------------+
| Test data                      | test-data-generator                                        |
+--------------------------------+------------------------------------------------------------+
| Run in the browser             | e2e-runner (one-off) · web-mapper + npm test (regression)  |
+--------------------------------+------------------------------------------------------------+
| Run API                        | api-runner · api-mapper (automate)                         |
+--------------------------------+------------------------------------------------------------+
| Exploratory                    | web-explorer · charter-generator                           |
+--------------------------------+------------------------------------------------------------+
| Smoke / regression             | test-case-selector + the suite; by platform, its           |
|                                | tester-* (below)                                           |
+--------------------------------+------------------------------------------------------------+
| Performance / load             | performance-guide (plan) + performance-mapper              |
+--------------------------------+------------------------------------------------------------+
| Web performance (CWV)          | web-performance-auditor                                    |
+--------------------------------+------------------------------------------------------------+
| Accessibility                  | accessibility-analyst                                      |
| (web/mobile/desktop)           |                                                            |
+--------------------------------+------------------------------------------------------------+
| Visual / visual regression     | pixel-perfect                                              |
+--------------------------------+------------------------------------------------------------+
| Cross-browser                  | cross-browser                                              |
+--------------------------------+------------------------------------------------------------+
| Usability (UX)                 | ux-evaluator                                               |
+--------------------------------+------------------------------------------------------------+
| Forms                          | form-tester                                                |
+--------------------------------+------------------------------------------------------------+
| Permissions by role            | permissions-tester                                         |
+--------------------------------+------------------------------------------------------------+
| Resilience / chaos             | resilience-tester (browser + Toxiproxy server-side)        |
+--------------------------------+------------------------------------------------------------+
| Emails                         | email-verifier                                             |
+--------------------------------+------------------------------------------------------------+
| Translations / i18n            | translation-analyst                                        |
+--------------------------------+------------------------------------------------------------+
| Content / typos                | content-reviewer                                           |
+--------------------------------+------------------------------------------------------------+
| Data / DB                      | data-verifier (queries) · data-tester (ETL/quality)        |
+--------------------------------+------------------------------------------------------------+
| Observability                  | observability-analyst                                      |
+--------------------------------+------------------------------------------------------------+
| Search / relevance             | search-tester                                              |
+--------------------------------+------------------------------------------------------------+
| Documents (PDF/Excel)          | document-tester                                            |
+--------------------------------+------------------------------------------------------------+
| Contract testing               | contract-tester                                            |
+--------------------------------+------------------------------------------------------------+
| SEO / GEO                      | seo-analyst                                                |
+--------------------------------+------------------------------------------------------------+
| Mutation testing               | mutation-analyst                                           |
+--------------------------------+------------------------------------------------------------+
| Dynamic security / pentest     | security-analyst (passive) · web-pentester (active)        |
+--------------------------------+------------------------------------------------------------+
| Static security                | dependency-analyst (SCA) · secure-code-analyst (SAST)      |
+--------------------------------+------------------------------------------------------------+
| Code quality / best practices  | code-quality-analyst                                       |
+--------------------------------+------------------------------------------------------------+
| Logs / failures                | log-analyst · failure-analyst                              |
+--------------------------------+------------------------------------------------------------+
| Coverage / traceability        | coverage-analyst                                           |
+--------------------------------+------------------------------------------------------------+
| Report a bug                   | bug-report-generator · bug-triager (duplicates)            |
+--------------------------------+------------------------------------------------------------+
| Round closure / dashboard      | closure-report-generator · quality-dashboard               |
+--------------------------------+------------------------------------------------------------+
| Management                     | test-manager · results-publisher                           |
| (Xray/QMetry/AIO/ADO)          |                                                            |
+--------------------------------+------------------------------------------------------------+
```

## 4. Map: platform → tester

```
+---------------------------+----------------------------------+
| Platform                  | Tester                           |
+===========================+==================================+
| Shopify                   | shopify-tester                   |
+---------------------------+----------------------------------+
| WordPress / WooCommerce   | wordpress-tester                 |
+---------------------------+----------------------------------+
| PrestaShop                | prestashop-tester                |
+---------------------------+----------------------------------+
| VTEX                      | vtex-tester                      |
+---------------------------+----------------------------------+
| Any store (base)          | ecommerce-testing (skill)        |
+---------------------------+----------------------------------+
| SAP (GUI and Fiori)       | sap-tester                       |
+---------------------------+----------------------------------+
| Salesforce                | salesforce-tester                |
+---------------------------+----------------------------------+
| Dynamics / other CRM-ERP  | dynamics-tester                  |
+---------------------------+----------------------------------+
| Mobile (Android/iOS)      | mobile-tester · mobile-mapper    |
+---------------------------+----------------------------------+
| Desktop (Windows)         | desktop-tester                   |
+---------------------------+----------------------------------+
| AI / LLM                  | ai-tester                        |
+---------------------------+----------------------------------+
| Messaging / events        | messaging-tester                 |
+---------------------------+----------------------------------+
| SOAP                      | soap-tester                      |
+---------------------------+----------------------------------+
| Blockchain / Web3         | blockchain-tester                |
+---------------------------+----------------------------------+
| Voice / IVR               | ivr-tester                       |
+---------------------------+----------------------------------+
| Video games               | game-tester                      |
+---------------------------+----------------------------------+
| Point of sale (POS)       | pos-tester                       |
+---------------------------+----------------------------------+
| Wallets / payments        | wallet-tester                    |
+---------------------------+----------------------------------+
| Streaming / cameras       | streaming-tester · onvif-tester  |
+---------------------------+----------------------------------+
```

## 5. Frequent paths (branching examples)

- **"I have a new story and don't know where to start"** → `story-analyst` (ambiguities) → `manual-case-generator`/`-bdd` → `e2e-runner` or `web-mapper` → bugs with `bug-report-generator`.
- **"I want the product to be solid before a release"** → `test-case-selector` (what to run) + regression (npm test) + `web-performance-auditor` + `accessibility-analyst` + `security-analyst`; closure with `closure-report-generator`.
- **"It's an online store"** → the `tester-<platform>` + `ecommerce-testing`; add `email-verifier`, `form-tester`, `pixel-perfect`.
- **"I'm worried about security"** → static (`dependency-analyst` + `secure-code-analyst`) and dynamic (`security-analyst`, and `web-pentester` with authorization).
- **"Are my tests good?"** → `coverage-analyst` (what gets run) + `mutation-analyst` (what gets verified).

## 6. Rules

- **Don't overwhelm**: ask the minimum, recommend the minimum, and leave the rest as "if you want, later".
- **Start from the context** (documentation, `.env`, story): don't ask what is already there.
- **Confirm before running** anything with a side effect, and pass the agent the data you already settled.
- If something is missing to decide (environment, credentials, scope), ask for it; don't assume.
- When the scope is unclear, offer a **smoke** first and then go deeper.
