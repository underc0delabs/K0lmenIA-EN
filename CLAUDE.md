# k0lmenIA — Project context

This repository is a set of **QA agents for Claude Code**, designed to help manual testing professionals speed up their day-to-day tasks: planning the test strategy, analyzing stories, writing test cases (manual, BDD and API), generating test data, writing bug reports, running end-to-end tests in the browser, running API tests, generating HTML results reports and putting together the round's closure report.

All work and all outputs are **in English**.

---

## How the flow works

1. **`input/`** — This is where the inputs go: user stories, product documentation, API contracts and error observations.
2. **Agents** (`.claude/agents/`) — Each agent is a specialist. Claude Code invokes them on its own based on what the person asks; you can also ask for them explicitly.
3. **`templates/` and `scripts/`** — They define the **output format**. The **bug report** follows `templates/bug-report-template.md`. **Test cases** are generated as an **Excel** spreadsheet (`.xlsx`) with `scripts/generate_cases.py` (reference: `templates/test-cases-template.xlsx`) plus a Markdown **coverage report** (reference: `templates/coverage-template.md`).
4. **`output/`** — This is where the generated artifacts are saved, organized by type.

```
input/ → [ agent ] → output/
              ↑
   templates/ + scripts/  (format)
```

### Questions and confirmations (main conversation ↔ agents)

Agents run as subagents and **cannot ask the person questions mid-task**. Therefore:

- **Before invoking an agent**, the main conversation settles with the person whatever the agent will surely need and is not in the request. For example: headed or headless (`e2e-runner`, `web-mapper`), which story if there are several, the URL or the environment, and the story key in Jira or Azure DevOps for management.
- **If an agent ends by returning "I need you to confirm"**, the main conversation asks the person those questions (with options, the recommended one first) and **continues the same agent** with the answers; it does not start a new one.
- Actions with side effects (writing to a database, creating or modifying data in Jira/Xray/QMetry/AIO/Azure DevOps, running load, methods with side effects) are confirmed **with the person** and passed to the agent explicitly; they are never assumed.
- **Performance**: the guided planning is done by the main conversation with the `performance-guide` skill; the `performance-mapper` works with the confirmed plan.
- **You don't know what to test or with which agent/skill**: the main conversation uses the `testing-guide` skill to ask you step by step and recommend or run the right agent/skill (it is also a main-conversation skill, because subagents can't ask questions).
- **Running already automated tests**: that is `npm test` in k0lmena (no agents, no tokens). The live runners (`e2e-runner`, `api-runner`) are for one-off cases that aren't worth automating.

---

## Available agents

The details of each agent (skills, scripts, tools, connectors, inputs, outputs and what it confirms) are in `AGENTS.md`.

```
+----------------------------+----------------------------------------+---------------------------------------+
| Agent                      | What it does                           | Saves the output in                   |
+============================+========================================+=======================================+
| `project-documenter`       | Gathers the project documentation:     | `input/documentation/`                |
|                            | repository (read-only), stories with   |                                       |
|                            | comments, PRs and links, and the       |                                       |
|                            | functional map of the website; project |                                       |
|                            | baseline, per-story dossier and index  |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `story-analyst`            | Analyzes stories and acceptance        | `output/story-analysis/`              |
|                            | criteria; detects ambiguities and      |                                       |
|                            | builds refinement questions            |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `test-strategist`          | Test plan/strategy (scope, risks,      | `output/test-plans/`                  |
|                            | test types, criteria) as an HTML       |                                       |
|                            | dashboard in dark mode                 |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `manual-case-generator`    | Test cases in Excel (.xlsx) and        | `output/test-cases/manual/`           |
|                            | Markdown (.md), + coverage report      |                                       |
|                            | (.md) with ambiguities and questions   |                                       |
|                            | for the PO                             |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `bdd-case-generator`       | Gherkin scenarios (keywords and        | `output/test-cases/bdd/`              |
|                            | content in English) + per-criterion    |                                       |
|                            | coverage report (.md)                  |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `bug-report-generator`     | Bug reports, following                 | `output/bug-reports/`                 |
|                            | `templates/bug-report-template.md`     |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `bug-triager`              | Looks for duplicates and regressions   | `output/triage/`                      |
|                            | (Jira, Azure DevOps, local bugs,       |                                       |
|                            | repository issues) and suggests        |                                       |
|                            | severity, priority, component, owner   |                                       |
|                            | and story                              |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `project-consultant`       | Answers product questions with the     | Answer in the chat (+                 |
|                            | project documentation, citing the      | `output/consultations/`)              |
|                            | source of each fact                    |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `onboarding-guide`         | Onboarding plan for a new QA: product  | `output/onboarding/`                  |
|                            | walkthrough with sources,              |                                       |
|                            | environment, agents for their role,    |                                       |
|                            | plan for the first weeks, questions    |                                       |
|                            | and checklist; HTML and Markdown       |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `test-data-generator`      | Realistic test data (Markdown or CSV)  | `output/test-data/`                   |
+----------------------------+----------------------------------------+---------------------------------------+
| `api-case-generator`       | API test cases (summary table +        | `output/api-cases/`                   |
|                            | detail with JSON) from                 |                                       |
|                            | contracts/endpoints                    |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `e2e-runner`               | Runs the requested cases/scenarios in  | `output/runs/`                        |
|                            | the browser with Playwright MCP (asks  |                                       |
|                            | headed or headless), reports with      |                                       |
|                            | evidence and generates the run's HTML  |                                       |
|                            | report                                 |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `api-runner`               | Runs API tests by running a Postman,   | `output/runs/`                        |
|                            | Bruno or Insomnia collection with      |                                       |
|                            | Newman and generates the run's HTML    |                                       |
|                            | report                                 |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `html-report-generator`    | Builds the HTML report (dark-mode      | `output/runs/`                        |
|                            | dashboard, with indicators and         |                                       |
|                            | charts) of a run, from its results     |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `closure-report-generator` | Closure report for the round           | `output/closure-reports/`             |
|                            | (results, bugs, go/no-go               |                                       |
|                            | recommendation) as an HTML dashboard   |                                       |
|                            | in dark mode                           |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `web-mapper`               | Walks the website with Playwright MCP  | `tools/k0lmena/web/` +                |
|                            | following manual or BDD cases and      | `output/mappings/`                    |
|                            | generates the k0lmena automation       |                                       |
|                            | (adjusted .feature, steps and          |                                       |
|                            | locators)                              |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `api-mapper`               | Reads a Postman collection or a        | `tools/k0lmena/api/` +                |
|                            | Swagger/OpenAPI, verifies the          | `output/mappings/`                    |
|                            | endpoints and generates the k0lmena    |                                       |
|                            | .feature files with the generic steps  |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `test-manager`             | Creates folders and cases in Xray      | The management tool +                 |
|                            | (Cloud or Server/DC), QTM4J or AIO     | `output/management/`                  |
|                            | Tests (via `scripts/management/`) or   |                                       |
|                            | in Azure DevOps Test Plans (via the    |                                       |
|                            | `azure-devops` MCP), links them to     |                                       |
|                            | stories, creates cycles and adds       |                                       |
|                            | cases to them                          |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `results-publisher`        | Uploads the results of a k0lmena run   | The management tool                   |
|                            | (`npm test`) to the cycle: status,     |                                       |
|                            | comment and evidence (screenshot;      |                                       |
|                            | video if it failed)                    |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `data-verifier`            | Connects to the databases in the       | Answer in the chat (+                 |
|                            | `.env` (PostgreSQL, MySQL/MariaDB, SQL | `output/data-verifications/` if       |
|                            | Server, MongoDB) to verify test data   | requested)                            |
|                            | or whatever is asked; adds DB checks   |                                       |
|                            | to the k0lmena `.feature` files only   |                                       |
|                            | if asked. Read-only; writes only with  |                                       |
|                            | confirmation and never in production   |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `mobile-mapper`            | Walks the mobile app with Appium MCP   | `tools/k0lmena/mobile/` +             |
|                            | following the cases and generates the  | `output/mappings/`                    |
|                            | k0lmena automation (.feature, steps    |                                       |
|                            | and locators)                          |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `performance-mapper`       | Performance tests (smoke, load,        | `tools/k0lmena/performance/` +        |
|                            | stress, soak, spike) with k6,          | `output/performance/<US>/` +          |
|                            | Artillery + Playwright or JMeter.      | `reports/performance/` +              |
|                            | First, the main conversation guides    | `output/mappings/`                    |
|                            | the person with the performance-guide  |                                       |
|                            | skill (test type, tool, users, ramp,   |                                       |
|                            | duration and thresholds, with          |                                       |
|                            | suggestions); the agent generates the  |                                       |
|                            | script, validates it, runs what was    |                                       |
|                            | confirmed and builds the HTML report   |                                       |
|                            | with metrics, charts and               |                                       |
|                            | recommendations                        |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `web-explorer`             | Exploratory testing: walks the         | `output/exploratory/`                 |
|                            | website (APP_URL from the `.env` or    |                                       |
|                            | the requested URL) looking for broken  |                                       |
|                            | links and images, JavaScript and       |                                       |
|                            | console errors, checks responsive      |                                       |
|                            | behavior at several resolutions and    |                                       |
|                            | explores by hand with Playwright MCP;  |                                       |
|                            | builds the HTML report with findings   |                                       |
|                            | and screenshots                        |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `accessibility-analyst`    | Audits accessibility (WCAG 2.2, AA)    | `output/accessibility/`               |
|                            | on web (axe-core, keyboard, reflow,    |                                       |
|                            | manual review with Playwright),        |                                       |
|                            | mobile (Appium: labels, touch          |                                       |
|                            | targets, TalkBack/VoiceOver) and       |                                       |
|                            | desktop (UI Automation: unnamed        |                                       |
|                            | controls, keyboard); HTML report with  |                                       |
|                            | criteria and how to fix                |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `web-performance-auditor`  | Load speed with Lighthouse on mobile   | `output/web-performance/`             |
|                            | and desktop: scores, Core Web Vitals   |                                       |
|                            | (LCP, CLS, TBT), opportunities with    |                                       |
|                            | the estimated savings and loading      |                                       |
|                            | sequence; HTML report                  |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `failure-analyst`          | Analyzes npm test failures:            | `output/failures/` +                  |
|                            | classifies them (possible bug,         | `output/bug-reports/`                 |
|                            | locator or wait, environment, data,    |                                       |
|                            | automation), detects flaky tests with  |                                       |
|                            | retries, rescues the evidence and      |                                       |
|                            | writes up the real bugs; HTML report   |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `coverage-analyst`         | Coverage and traceability matrix:      | `output/coverage/`                    |
|                            | stories, criteria, cases, automation,  |                                       |
|                            | management, latest result and bugs;    |                                       |
|                            | marks the gaps (what is left to        |                                       |
|                            | test); HTML report                     |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `quality-dashboard`        | Quality dashboard per sprint or        | `output/dashboard/`                   |
|                            | release (passed and trend, automated,  |                                       |
|                            | coverage, bugs, flaky) with a summary  |                                       |
|                            | for management; HTML report            |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `pixel-perfect`            | Visual regression: compares each page  | `output/pixel-perfect/`               |
|                            | against its reference (or the design)  |                                       |
|                            | pixel by pixel and per element; tells  |                                       |
|                            | what shifted and by how much, what is  |                                       |
|                            | missing, what is new and what changed  |                                       |
|                            | style; HTML report with a slider       |                                       |
|                            | comparator                             |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `cross-browser`            | Tests on Chromium (Chrome, Edge),      | `output/cross-browser/`               |
|                            | Firefox and WebKit (Safari): the       |                                       |
|                            | k0lmena suite per browser or the       |                                       |
|                            | pages compared against the base        |                                       |
|                            | browser; HTML report with the matrix   |                                       |
|                            | and the differences                    |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `automation-repairer`      | Repairs broken locators and waits in   | `tools/k0lmena/web/` +                |
|                            | the web automation: diagnoses with     | `output/repairs/`                     |
|                            | the DOM saved on failure, proposes a   |                                       |
|                            | unique locator, applies it with a      |                                       |
|                            | backup and verifies; HTML report       |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `test-case-selector`       | Chooses which cases to run for a       | `output/case-selection/`              |
|                            | change (git, PR, Jira, release notes)  |                                       |
|                            | prioritized by risk, with the npm      |                                       |
|                            | test command and the uncovered         |                                       |
|                            | changes; HTML report                   |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `email-verifier`           | Verifies the app's emails with a       | `output/emails/`                      |
|                            | Mailpit test mailbox: that the         |                                       |
|                            | expected ones arrive, unreplaced       |                                       |
|                            | variables, links, compatibility and    |                                       |
|                            | desktop/mobile view; HTML report and   |                                       |
|                            | email steps for k0lmena                |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `translation-analyst`      | Reviews each page in each language:    | `output/translator/`                  |
|                            | untranslated text, visible keys,       |                                       |
|                            | broken characters, truncated text and  |                                       |
|                            | number and date formats; proposes      |                                       |
|                            | translations; HTML report              |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `case-reviewer`            | Reviews the quality of existing cases  | `output/case-review/`                 |
|                            | (score, issues, duplicates, stories    |                                       |
|                            | without negatives, manual execution    |                                       |
|                            | time) and proposes improved versions;  |                                       |
|                            | HTML report                            |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `charter-generator`        | Session-based exploratory testing      | `output/charters/`                    |
|                            | charters (printable sheets, notes      |                                       |
|                            | template) and the sessions report;     |                                       |
|                            | HTML report                            |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `ux-evaluator`             | Heuristic usability evaluation (10     | `output/ux/`                          |
|                            | Nielsen heuristics): automatic on      |                                       |
|                            | desktop and mobile plus manual review  |                                       |
|                            | of the flows; HTML report              |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `form-tester`              | Tests the validations of every form    | `output/forms/`                       |
|                            | field without submitting (required,    |                                       |
|                            | lengths, formats, limits, messages);   |                                       |
|                            | HTML report                            |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `permissions-tester`       | Logs in with each role (plus           | `output/permissions/`                 |
|                            | anonymous) and builds the role ×       |                                       |
|                            | route and role × endpoint matrix:      |                                       |
|                            | what opens, what is denied, access by  |                                       |
|                            | direct URL; compares with the          |                                       |
|                            | expected rule; HTML report             |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `resilience-tester`        | Browser chaos (API down or slow,       | `output/resilience/`                  |
|                            | offline, broken responses) and         |                                       |
|                            | server-side chaos with Toxiproxy       |                                       |
|                            | (latency/outage of real                |                                       |
|                            | dependencies); reviews how the system  |                                       |
|                            | degrades; HTML report                  |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `log-analyst`              | Analyzes the app's logs: groups        | `output/logs/`                        |
|                            | errors, builds the timeline and        |                                       |
|                            | cross-references them with the failed  |                                       |
|                            | npm test scenarios; HTML report        |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `security-analyst`         | Reviews the security of your own or    | `output/security/`                    |
|                            | an authorized website with a passive   |                                       |
|                            | OWASP ZAP scan (Docker), analyzes the  |                                       |
|                            | findings (prioritizes, discards false  |                                       |
|                            | positives, explains in plain English)  |                                       |
|                            | and builds the HTML report with risk,  |                                       |
|                            | evidence, fix and recommendations.     |                                       |
|                            | Only URLs in SECURITY_AUTHORIZED_URLS  |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `web-pentester`            | AUTHORIZED web pentest (ethical        | `output/security/`                    |
|                            | hacking): tries to break into your     |                                       |
|                            | own site or one with permission using  |                                       |
|                            | the OWASP ZAP active scan and manual   |                                       |
|                            | verification (OWASP Top 10) with       |                                       |
|                            | Playwright MCP; confirms each finding  |                                       |
|                            | and builds the report with risk,       |                                       |
|                            | steps to reproduce and fix. Only URLs  |                                       |
|                            | in SECURITY_AUTHORIZED_URLS and with   |                                       |
|                            | PENTEST_AUTHORIZED; non-destructive    |                                       |
| `streaming-tester`         | Tests video streaming and playback     | `output/streaming/`                   |
|                            | (RTSP/ONVIF IP cameras, live           |                                       |
|                            | RTMP/HLS/DASH, WebRTC and VOD) with    |                                       |
|                            | ffprobe/ffmpeg: properties (codec,     |                                       |
|                            | resolution, FPS, bitrate, audio) and   |                                       |
|                            | continuity (dropped frames, errors,    |                                       |
|                            | latency); HTML report. Only            |                                       |
|                            | STREAMING_AUTHORIZED_SOURCES           |                                       |
| `onvif-tester`             | ONVIF control of an IP camera: device  | `output/streaming/`                   |
|                            | info, profiles and stream URIs,        |                                       |
|                            | snapshot, PTZ (optional) and           |                                       |
|                            | event/motion capabilities. Returns     |                                       |
|                            | the RTSP URI for the                   |                                       |
|                            | streaming-tester. Only                 |                                       |
|                            | ONVIF_AUTHORIZED_HOSTS; PTZ moves the  |                                       |
|                            | camera and is confirmed                |                                       |
| `image-quality-analyst`    | Camera image quality: captures and     | `output/streaming/quality-*/`         |
|                            | detects with OpenCV black frames,      |                                       |
|                            | blur and freezing, and with vision     |                                       |
|                            | dirty lens, moved camera, backlight    |                                       |
|                            | and night IR; compares against a       |                                       |
|                            | reference. Only                        |                                       |
|                            | STREAMING_AUTHORIZED_SOURCES           |                                       |
| `recording-verifier`       | Recordings of a camera or NVR via      | `output/streaming/recordings-*/`      |
|                            | ONVIF (Recording/Search): what is      |                                       |
|                            | there, covered range, gaps and         |                                       |
|                            | whether the expected retention is      |                                       |
|                            | met. Warns if unsupported. Only        |                                       |
|                            | ONVIF_AUTHORIZED_HOSTS                 |                                       |
| `camera-security-analyst`  | PASSIVE security of IP cameras/NVRs:   | `output/streaming/camera-security-*/` |
|                            | open ports, insecure services          |                                       |
|                            | (Telnet, FTP, HTTP without TLS, RTSP   |                                       |
|                            | without auth) and firmware to check    |                                       |
|                            | for CVEs. Does not test credentials.   |                                       |
|                            | Only AUTHORIZED_CAMERAS                |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `project-researcher`       | Surveys the ENTIRE project via MCP     | `output/research/`                    |
|                            | (Jira, Azure DevOps, Confluence,       |                                       |
|                            | repo, Figma): summary, modules,        |                                       |
|                            | flows, integrations, team, backlog     |                                       |
|                            | status, ambiguities and                |                                       |
|                            | contradictions with their sources,     |                                       |
|                            | and prioritized questions for a new    |                                       |
|                            | QA; HTML and Markdown report           |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `salesforce-tester`        | Tests a Salesforce org (SANDBOX):      | `output/salesforce/`                  |
|                            | surveys access (profiles,              |                                       |
|                            | permissions, OWD, FLS), validations,   |                                       |
|                            | flows, triggers, Apex coverage and     |                                       |
|                            | limits with the sf CLI, derives and    |                                       |
|                            | runs tests per profile in Lightning;   |                                       |
|                            | HTML report. Never production; does    |                                       |
|                            | not touch metadata                     |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `wallet-tester`            | Tests digital wallets and payments in  | `output/wallets/`                     |
|                            | sandbox: balance conservation,         |                                       |
|                            | transaction statuses, idempotency,     |                                       |
|                            | double spending and concurrency,       |                                       |
|                            | limits, KYC/AML, reconciliation with   |                                       |
|                            | the gateway and token security; HTML   |                                       |
|                            | report. Test money and cards, never    |                                       |
|                            | real ones                              |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `shopify-tester`           | Tests a Shopify store: surveys in      | `output/shopify/`                     |
|                            | read-only mode the storefront (theme,  |                                       |
|                            | Liquid errors, policies, catalog) and  |                                       |
|                            | the Admin API (products and stock,     |                                       |
|                            | markets, shipping, discounts,          |                                       |
|                            | webhooks) and Theme Check; tests       |                                       |
|                            | checkout with Bogus Gateway or test    |                                       |
|                            | mode on mobile and desktop; HTML       |                                       |
|                            | report                                 |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `wordpress-tester`         | Tests WordPress / WooCommerce:         | `output/wordpress/`                   |
|                            | surveys in read-only mode the          |                                       |
|                            | storefront, the WooCommerce REST API   |                                       |
|                            | (outdated plugins and templates,       |                                       |
|                            | gateways and their mode, shipping,     |                                       |
|                            | coupons, webhooks, cron) and WP-CLI;   |                                       |
|                            | tests checkout, test payments,         |                                       |
|                            | shipping, coupons, emails and roles;   |                                       |
|                            | HTML report                            |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `prestashop-tester`        | Tests PrestaShop (1.6/1.7/8.x):        | `output/prestashop/`                  |
|                            | surveys in read-only mode the          |                                       |
|                            | storefront and the Webservice API      |                                       |
|                            | (products and stock, combinations,     |                                       |
|                            | carriers, zones, currencies,           |                                       |
|                            | vouchers, multistore and performance   |                                       |
|                            | configs) and, with --local, version    |                                       |
|                            | and dev mode; tests local smoke,       |                                       |
|                            | checkout, test payments, stock,        |                                       |
|                            | rounding and performance; HTML report  |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `vtex-tester`              | Tests VTEX: surveys in read-only mode  | `output/vtex/`                        |
|                            | the storefront and the public Catalog  |                                       |
|                            | System (SKUs, price, stock) and, with  |                                       |
|                            | a read app, sales channels, shipping   |                                       |
|                            | (SLAs) and promotions; tests smoke in  |                                       |
|                            | a QA workspace, checkout/orderForm,    |                                       |
|                            | sandbox payments, channels, promos     |                                       |
|                            | and OMS; HTML report                   |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `sap-tester`               | Tests SAP (S/4HANA or ECC) in a QA     | `output/sap/`                         |
|                            | client: SAP GUI (T-codes with the      |                                       |
|                            | Scripting API) and Fiori/UI5 (OData),  |                                       |
|                            | authorizations and roles               |                                       |
|                            | (PFCG/SU53/SoD), end-to-end            |                                       |
|                            | O2C/P2P/R2R processes; smoke,          |                                       |
|                            | regression after transport,            |                                       |
|                            | performance and security; HTML report  |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `desktop-tester`           | Tests Windows desktop apps             | `output/desktop/`                     |
|                            | (WinForms/WPF/UWP/Electron/Java/Qt):   |                                       |
|                            | surveys the control tree (pywinauto)   |                                       |
|                            | and tests with Appium+WinAppDriver,    |                                       |
|                            | pywinauto or Playwright (Electron);    |                                       |
|                            | functional, installation, files, OS,   |                                       |
|                            | regression, performance and security;  |                                       |
|                            | HTML report                            |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `mobile-tester`            | Tests mobile apps (Android/iOS;        | `output/mobile/`                      |
|                            | native/hybrid/web) live with Appium:   |                                       |
|                            | functional, permissions,               |                                       |
|                            | interruptions, offline, deep links     |                                       |
|                            | and push, lifecycle, OS/screen         |                                       |
|                            | compatibility, performance and mobile  |                                       |
|                            | security (MASVS); HTML report          |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `dependency-analyst`       | Dependency SCA: runs npm audit /       | `output/dependencies/`                |
|                            | pip-audit / osv-scanner, aggregates    |                                       |
|                            | CVEs by severity, direct vs.           |                                       |
|                            | transitive, available fix and          |                                       |
|                            | licenses; HTML report                  |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `secure-code-analyst`      | SAST and secrets: built-in secret      | `output/sast/`                        |
|                            | scanner + semgrep, false-positive      |                                       |
|                            | triage, mapping to OWASP/CWE;          |                                       |
|                            | redacted secrets to rotate; HTML       |                                       |
|                            | report                                 |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `ai-tester`                | Tests AI/LLM features (chatbot, RAG,   | `output/ai/`                          |
|                            | agent): golden set and evals,          |                                       |
|                            | hallucinations and grounding, prompt   |                                       |
|                            | security (injection/jailbreak),        |                                       |
|                            | format, robustness, latency and cost;  |                                       |
|                            | HTML report                            |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `messaging-tester`         | Tests messaging/events (Kafka,         | `output/messaging/`                   |
|                            | RabbitMQ, SQS/SNS, MQTT, WebSocket,    |                                       |
|                            | SSE): delivery, ordering,              |                                       |
|                            | idempotency, DLQ and retries,          |                                       |
|                            | schemas, consumer lag and outbox;      |                                       |
|                            | publishes/consumes with the tool;      |                                       |
|                            | HTML report                            |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `soap-tester`              | Tests SOAP services from the WSDL:     | `output/soap/`                        |
|                            | operations, XSD validation, SOAP       |                                       |
|                            | Faults, namespaces/SOAPAction,         |                                       |
|                            | WS-Security and idempotency; sends     |                                       |
|                            | the envelopes with api-runner; HTML    |                                       |
|                            | report                                 |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `contract-tester`          | Contract testing (Pact):               | `output/contracts/`                   |
|                            | consumer-driven and bi-directional     |                                       |
|                            | for REST, GraphQL, gRPC and events;    |                                       |
|                            | verification, can-i-deploy and         |                                       |
|                            | compatibility; report                  |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `seo-analyst`              | SEO and GEO: indexability, on-page,    | `output/seo/`                         |
|                            | structured data, hreflang and AI       |                                       |
|                            | crawler access; surveys with npm run   |                                       |
|                            | seo; HTML report                       |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `data-tester`              | Data and pipelines (ETL): quality,     | `output/data/`                        |
|                            | source↔target reconciliation, schema,  |                                       |
|                            | transformations and idempotency;       |                                       |
|                            | read-only with data-verifier; report   |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `dynamics-tester`          | Dynamics 365 and other CRM/ERP         | `output/dynamics/`                    |
|                            | (sandbox): roles, logic                |                                       |
|                            | (flows/plugins/BPF/roll-ups),          |                                       |
|                            | end-to-end processes; read Web API +   |                                       |
|                            | Playwright per role; report            |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `blockchain-tester`        | Blockchain/Web3 and smart contracts    | `output/blockchain/`                  |
|                            | (testnet/local): functional, tokens,   |                                       |
|                            | gas, security (reentrancy, access,     |                                       |
|                            | oracles), Hardhat/Foundry; report      |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `ivr-tester`               | Voice/IVR and voicebots: menu tree     | `output/ivr/`                         |
|                            | (DTMF/voice), prompts, routing and     |                                       |
|                            | queues, telephony and compliance       |                                       |
|                            | (PCI); HTML report                     |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `game-tester`              | Video games (Unity/Unreal/Godot/HTML5/ | `output/games/`                       |
|                            | mobile): mechanics, saving,            |                                       |
|                            | compatibility, performance,            |                                       |
|                            | multiplayer, monetization and          |                                       |
|                            | exploratory testing; HTML report       |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `pos-tester`               | Point of sale (POS) and hardware:      | `output/pos/`                         |
|                            | sales, payments and peripherals,       |                                       |
|                            | fiscal, offline and reconciliation,    |                                       |
|                            | cash register closings; report         |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `observability-analyst`    | Observability: validates logs (trace   | `output/observability/`               |
|                            | id, no PII), metrics (Prometheus,      |                                       |
|                            | RED/USE), traces (OTel), healthchecks  |                                       |
|                            | (liveness/readiness), SLOs and         |                                       |
|                            | alerts; HTML report                    |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `search-tester`            | Search and relevance                   | `output/search/`                      |
|                            | (Elastic/Algolia/Solr/DB): ranking,    |                                       |
|                            | typos, synonyms, facets, indexing and  |                                       |
|                            | golden set with precision@k/nDCG;      |                                       |
|                            | HTML report                            |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `document-tester`          | Generated documents (PDF/Excel/CSV):   | `output/documents/`                   |
|                            | data and totals, unreplaced            |                                       |
|                            | placeholders, format/locale, layout,   |                                       |
|                            | metadata and security; HTML report     |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `content-reviewer`         | Content and typos (main language):     | `output/content/`                     |
|                            | spelling, placeholders, visible i18n   |                                       |
|                            | keys, duplicates and microcopy         |                                       |
|                            | consistency; HTML report               |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
| `mutation-analyst`         | Mutation testing: measures the real    | `output/mutation/`                    |
|                            | quality of the suite                   |                                       |
|                            | (Stryker/mutmut/PITest), mutation      |                                       |
|                            | score per file, surviving vs.          |                                       |
|                            | equivalent mutants and the missing     |                                       |
|                            | test; HTML report                      |                                       |
+----------------------------+----------------------------------------+---------------------------------------+
```

---

## Project QA standards

These principles apply to **all** agents:

- **Don't make things up.** If information is missing to do the task well (a step, a piece of data, a business rule, an expected result), the agent **flags it and asks**; it never fills it in with assumptions disguised as facts. An artifact with flagged gaps is better than a complete but invented one.
- **Research before assuming.** Before analyzing, planning, writing cases or automating a story, its full context is reviewed with the `context-research` skill: first the project documentation in `input/documentation/` (built by the `project-documenter`: index, story dossier, code rules, messages, functional map), and then the Jira story with **all** its comments, subtasks, epic and linked issues, the related Confluence pages and Figma designs, contracts and `input/`. The result goes into a reusable sheet `output/context/context-US-XXX.md`.
- **Flag what is missing.** Whatever doesn't appear in any source is recorded as **Missing information** with a per-story ID (`MI-01`, `MI-02`, …) and travels with that ID to every artifact: cases (highlighted, `@missing-info` tag, *Missing information* sheet), `.feature` files (`@missing-info @MI-01`), coverage reports, mappings, run reports, the closure report and whatever is published to Xray/QMetry/AIO. In the `analysis.json` and `_results-*.json` files of the HTML reports it goes as `missing_info: [{"id": "MI-01", "what_is_missing": "…", "question": "…"}]`.
- **Respect the formats.** The fields, their order and their allowed values are defined by the template (or the script), not by the agent.
- **Traceability.** Every artifact references the story (`US-XXX`) or the contract it comes from.
- **Thought-out coverage.** Cases cover positive, negative and edge scenarios and field validations, not just the happy path.
- **Clarity.** Descriptive titles, actionable and unambiguous steps, clear and professional language.

## ID conventions

- User stories: `US-001`, `US-002`, …
- Acceptance criteria: `AC1`, `AC2`, … (within each story)
- Manual test cases: `TC-001`, `TC-002`, … (numbered **per story**; if the story already has cases —manual, BDD, automation or management—, their IDs are kept and the new ones continue from the last one). BDD scenarios use the **same** numbering as the `@TC-XXX` tag, and the `Feature` carries `@US-XXX`: the `@US` + `@TC` pair identifies each case in automation, management and results. A `Scenario Outline` is a single case (a single `@TC`).
- API test cases: `TC-API-001`, `TC-API-002`, … (numbered per story, or per contract if there is no story)
- Bugs: `BUG-001`, `BUG-002`, …
- Missing information: `MI-01`, `MI-02`, … (per story; tags `@missing-info @MI-01`)
- Story in file names: the `US-XXX` if it exists (`context-US-001.md`, `cases-US-001…`, the **Story** field of bugs); if the story only has a tool key, the key (`context-PROJ-12.md`). The dossier in `input/documentation/stories/` goes by key and carries both IDs in its `story:` header.

## Scales

- **Severity / Criticality:** `Critical` · `High` · `Medium` · `Low`
- **Priority:** `Critical` · `High` · `Medium` · `Low`
- **Case status:** `N/A` · `Pending` · `In progress` · `Passed` · `Failed` · `Blocked`

## Table format in `.md` files

**Every table in a `.md` must look aligned and with the same format.** To guarantee it without depending on building each table by hand:

1. Write the tables as **normal Markdown** (`| col | col |`), in any section.
2. **When you finish writing the `.md`, normalize the file once:**

```bash
python scripts/format_tables.py <file.md>
```

It converts **all** the Markdown tables in the file into aligned ASCII tables (inside code blocks), regardless of the section or how much text they have. It doesn't touch what is already in code blocks, so it is safe to run more than once.

Rules (they apply to **all** agents and any section, including the ones you build on the fly):

- Never leave a raw Markdown table in the deliverable: always run the `.md` through `format_tables.py`.
- **No emojis inside cells** (they misalign the ASCII): use text (`Covered`, `Yes`, `No`, `Partial`).
- Whatever is **code** (a JSON body or response) goes in separate ```` ```json ```` blocks; the normalizer doesn't touch it.
- Exception: the **test cases** `.md` is built by `scripts/generate_cases.py` (it already comes out aligned, with the same style).

## Environment requirements

**Versions**: Python 3.10+, Node.js 20+ (22 LTS recommended; mobile needs 22+). Optional: Java 8+ (JMeter), Docker (web security with ZAP), JDK + Android SDK or Xcode (mobile). To check everything at once: `npm run doctor` (or `python scripts/doctor.py`), which tells you what is missing and how to fix it.

**Python**: on Windows the command is `python`; on Mac and Linux, `python3` (and `pip3`). The agents use whichever matches the system. The scripts install `openpyxl`/`tabulate`/`requests` only if they are missing; or install them with `pip install -r requirements.txt`. If a library is missing and can't be installed, the script warns with a clear message (it doesn't fail silently).

- `scripts/generate_cases.py` → builds the `.xlsx` spreadsheet and the test cases `.md`. Accepts `--clean` to delete its input JSON when done (cross-platform, without depending on `rm`).
- `scripts/format_tables.py` → aligns the tables of any `.md` (used by every agent that generates reports).
- `scripts/run_newman.py` → runs a Postman, Bruno or Insomnia collection with the token and URL from the `.env` (`--data` to iterate with a CSV/JSON) and generates its report (`api-runner`); a request without `pm.test` ends up Blocked ("No validations").
- `scripts/collect_results.py` → gathers the results of a story (live runs, `npm test` with its `history/`, bugs, performance and security) for the closure report; each case (story + ID) counts by its most recent result.
- `scripts/doctor.py` → checks the environment and the configuration by section (Python, Node and k0lmena, tools, fonts, `.env`, integrations, connectors, git and extras), without showing secrets. `--section env,integrations`, `--quick` (no network or Docker) and `--json`.
- `scripts/generate_exploratory_report.py` → builds the exploratory testing HTML report from the `exploration.json` of `npm run explore` (`web-explorer`).
- `scripts/generate_accessibility_report.py` → builds the accessibility HTML report from the `audit.json` of `npm run accessibility` (`accessibility-analyst`).
- `scripts/generate_web_performance_report.py` → builds the web performance HTML report from the `web-performance.json` of `npm run web-performance` (`web-performance-auditor`).
- `scripts/analyze_failures.py` → classifies the `npm test` failures, compares with retries and generates the report (`failure-analyst`).
- `scripts/analyze_coverage.py` → builds the coverage and traceability matrix per story and generates the report (`coverage-analyst`).
- `scripts/generate_emails_report.py` and `generate_translation_report.py` → the HTML reports of `npm run emails` (Mailpit) and `npm run translator` (`email-verifier`, `translation-analyst`).
- `scripts/estimation.py` → **estimated manual execution time** of each case (formula in `templates/time-estimation.md`): it goes in the cases spreadsheet, in the management tool when uploading them (description and Original Estimate / estimatedTime / estimatedEffort), in the selection and in the review.
- `scripts/review_cases.py`, `generate_charters.py` and `analyze_logs.py` (with their `generate_*_report`) → case review, exploratory charters and log analysis; `generate_ux_report.py` and `generate_forms_report.py` → the reports of `npm run ux` and `npm run forms`.
- `scripts/_history.py` (and `tools/k0lmena/tools/history/`) → keep the last 5 runs of each tool and build the evolution section of the reports.
- `scripts/documentation_index.py` → builds `input/documentation/INDEX.md` (what documentation there is, its sources and whether it is current); `npm run functional-map`, the functional map of the website (`project-documenter`).
- `scripts/documentation_changes.py` → incremental documentation: saves in `input/documentation/.status.json` what was documented (commit per repository, sources of each document, date of each story) and, with the files that changed, tells which documents to redo and which cases to review (`changes.md`).
- `scripts/generate_permissions_report.py` and `generate_resilience_report.py` → the reports of `npm run permissions` and `npm run resilience` (`permissions-tester`, `resilience-tester`).
- `tools/resilience/toxiproxy.py` (`npm run toxiproxy`) → server-side chaos with Toxiproxy (latency, outage and slowness of real dependencies through its REST API; stdlib only) for the `resilience-tester`; it complements the browser-side chaos. QA only, with `reset` when done.
- `scripts/generate_streaming_report.py` and `generate_onvif_report.py` → the reports of `npm run streaming` (ffprobe/ffmpeg: properties, continuity, stability and load) and `npm run onvif` (ONVIF control: profiles, snapshot, PTZ, events) (`streaming-tester`, `onvif-tester`).
- `scripts/generate_quality_report.py`, `generate_recordings_report.py` and `generate_camera_security_report.py` → the reports of `npm run image-quality` (OpenCV + vision), `npm run recordings` (ONVIF Recording) and `npm run camera-security` (passive scan) (`image-quality-analyst`, `recording-verifier`, `camera-security-analyst`).
- `tools/salesforce/inventory.py` (`npm run salesforce`) and `scripts/generate_salesforce_report.py` → read-only QA inventory of a Salesforce org (sandbox) with the `sf` CLI (profiles, validations, flows, triggers, Apex coverage, sharing, limits) and HTML report (`salesforce-tester`).
- `scripts/generate_wallets_report.py` → HTML report for wallets and payments (findings, tests, balance conservation and reconciliation) from the `analysis.json` built by the agent (`wallet-tester`).
- `tools/ecommerce/shopify.py` (`npm run shopify`), `tools/ecommerce/wordpress.py` (`npm run wordpress`), `tools/ecommerce/prestashop.py` (`npm run prestashop`), `tools/ecommerce/vtex.py` (`npm run vtex`) and `scripts/generate_ecommerce_report.py` → read-only functional survey of Shopify stores (storefront, read Admin API, Theme Check), WordPress / WooCommerce (storefront, read REST API, WP-CLI), PrestaShop (storefront, read Webservice API, version and dev mode of the local install) and VTEX (storefront, public Catalog System, and sales channels, shipping and promotions with a read app), with findings, test suggestions and HTML report (`shopify-tester`, `wordpress-tester`, `prestashop-tester`, `vtex-tester`). Only `ECOMMERCE_AUTHORIZED_URLS`.
- `tools/sap/sap_gui.py` (`npm run sap`) and `scripts/generate_sap_report.py` → read-only survey of a SAP GUI for Windows session through the Scripting API (system, client, user, transaction) and HTML report of the SAP tester (GUI and Fiori): findings, tests, authorizations and business processes (`sap-tester`). Requires `pywin32` (optional, Windows only).
- `tools/desktop/controls.py` (`npm run desktop`) and `scripts/generate_desktop_report.py` → read-only survey of the control tree of a Windows desktop app (pywinauto, UI Automation) and HTML report of the desktop tester: findings, tests and compatibility (`desktop-tester`). Requires `pywinauto` (optional, Windows only).
- `scripts/generate_mobile_report.py` → HTML report of the mobile app tester (Android/iOS): findings, tests per device and compatibility, from the `analysis.json` built by the agent with Appium (`mobile-tester`, `appium` connector).
- `tools/security/dependencies.py` (`npm run dependencies`) and `scripts/generate_dependencies_report.py` → read-only dependency SCA (npm audit / pip-audit / osv-scanner), CVEs by severity and HTML report (`dependency-analyst`).
- `tools/security/sast.py` (`npm run sast`) and `scripts/generate_sast_report.py` → read-only SAST and secret search (built-in secret scanner + semgrep if available) and HTML report (`secure-code-analyst`). They complement the dynamic analysis of `tools/zap` (DAST).
- `scripts/generate_ai_report.py` → HTML report of the AI/LLM feature tester (golden set/evals, hallucinations and grounding, prompt security, metrics), from the `analysis.json` built by the agent (`ai-tester`).
- `tools/messaging/messaging.py` (`npm run messaging`) and `scripts/generate_messaging_report.py` → messaging/event tests (Kafka, RabbitMQ, MQTT, WebSocket, SSE): publish/consume/inspect and verify ordering, duplicates and schema, with HTML report (`messaging-tester`). Optional broker libraries (lazy import).
- `tools/soap/wsdl.py` (`npm run soap`) and `scripts/generate_soap_report.py` → survey of a SOAP service through its WSDL (operations, endpoint, version, sample envelope; only the stdlib `xml`) and HTML report of the SOAP tester (`soap-tester`).
- `scripts/summarize_graphql.py` and the `graphql-testing` and `grpc-testing` skills → **GraphQL and gRPC** support for the API family (`api-runner`, `api-mapper`, `api-case-generator`): introspection/schema, partial errors, per-field authorization and, in gRPC, Protobuf, RPC modes, status codes and compatibility; WebSocket is covered in `async-testing` (`messaging-tester`).
- `scripts/generate_generic_report.py` → generic HTML report (same house style) for the testers without their own report: used by `contract-tester`, `seo-analyst`, `data-tester`, `dynamics-tester`, `blockchain-tester`, `ivr-tester`, `game-tester` and `pos-tester`, from their `analysis.json`.
- `tools/mutation/mutation.py` (`npm run mutation`) → reads the mutation testing report (Stryker JSON): global and per-file mutation score, surviving mutants and files under the threshold (`mutation-analyst`); the report, with `generate_generic_report.py`.
- `tools/observability/observability.py` (`npm run observability`) → healthchecks and metrics (Prometheus) of a service, read-only (`observability-analyst`); the report, with `generate_generic_report.py`.
- `tools/documents/documents.py` (`npm run documents`) → extracts text/metadata from a PDF (pypdf) and sheets/cells from an Excel file (openpyxl) and detects unreplaced placeholders (`document-tester`).
- `tools/content/content.py` (`npm run content`) → heuristic content/typo review (placeholders, duplicates, visible i18n keys, Lorem ipsum) and optional LanguageTool (`content-reviewer`).
- `tools/seo/seo.py` (`npm run seo`) → SEO/GEO survey of a page (stdlib `urllib`/regex only): on-page, structured data, hreflang, robots/sitemap and AI crawler access (`seo-analyst`).
- `scripts/generate_research_report.py` → the package of a full project survey: HTML website with **concept maps** (architecture and how it works) and the epics/stories/tasks tree, a brief `summary.md` and `research-presentation.html` (prints to PDF), with a comparison against the previous survey (`project-researcher`).
- `scripts/find_duplicates.py` → similarity between bugs for the `bug-triager` (duplicates, regressions, related).
- `scripts/token_metrics.py` → agent **token usage**: reads the project's Claude Code transcripts (counts only, never the text), attributes the usage to each agent and estimates the cost per agent, day and model with opportunities (what is worth automating in k0lmena); the quality dashboard includes it.
- `scripts/generate_onboarding.py` → the `onboarding-guide` onboarding plan (HTML with checklist and Markdown).
- `scripts/quality_dashboard.py` → quality dashboard per sprint or release (`quality-dashboard`).
- `scripts/reports_portal.py` → `output/index.html` with the latest report of each tool, search and filters by tool, story, status and date, and a view by tool or by story; it regenerates on its own whenever any report finishes (`K0LMENIA_PORTAL=0` disables it).
- `scripts/notify.py` → Slack and Teams notifications by webhook (`SLACK_WEBHOOK_URL`, `TEAMS_WEBHOOK_URL`); `--from-cucumber` summarizes an `npm test`. Without a webhook it sends nothing.
- `npm run monitor` (k0lmena `tools/monitoring`) and `scripts/generate_monitoring_report.py` → read-only synthetic monitoring (URLs, texts, times, certificate and `@synthetic` scenarios); it notifies only when something breaks or recovers. Schedule it with `.github/workflows/monitoring.yml`, cron or Task Scheduler.
- `scripts/convert_collection.py` → converts Bruno (folder with `bruno.json`) and Insomnia (v4 `.json` / v5 `.yaml`) collections to Postman v2.1, with warnings about what couldn't be converted (`run_newman.py` uses it on its own). `scripts/summarize_graphql.py` → summarizes a GraphQL schema (introspection by URL, SDL or JSON). `scripts/summarize_openapi.py` → summarizes a Swagger 2.0 / OpenAPI 3.x (JSON or YAML): `API_BASEURL` with its basePath, the authentication step of each securityScheme, parameters, sample body and documented status codes.
- `scripts/evaluate_agents.py` → **agent evals** (`evals/`): cases with deliberate traps that run in an isolated workspace with `claude -p` and are verified with deterministic checks; report with the score per agent and the regressions. **They spend tokens** (cap per case); `--verify-only` checks outputs already generated.
- `scripts/select_cases.py` → chooses and prioritizes the cases to run for a change and generates the report (`test-case-selector`).
- `scripts/generate_pixel_perfect_report.py`, `generate_cross_browser_report.py` and `generate_repair_report.py` → the HTML reports of `npm run pixel-perfect`, `npm run cross-browser` and `npm run repair` (`pixel-perfect`, `cross-browser`, `automation-repairer`).
- **Repo tests**: `python -m pytest tests` and `npm run test:repo` (they also run in CI, on Ubuntu and Windows).

---

## Output file names (suggestion)

- Project documentation (`project-documenter`, not versioned): `input/documentation/` with `INDEX.md`, `project/` (summary, repository, business rules, messages, statuses and permissions, functional map, links), `api/` and `stories/<US or key>/dossier.md`.
- Context sheet: `output/context/context-US-001.md` (sources consulted, findings and Missing information)
- Story analysis: `analysis-US-001.md`
- Manual cases: `cases-US-001.xlsx` + `cases-US-001.md` + `cases-US-001-coverage.md` (each case with its estimated manual execution time)
- BDD cases: `US-001-signup.feature` + `US-001-coverage.md`
- Bug report: `BUG-001.md`
- Web security: `output/security/<US or host>/<date>/` with `zap.json`, `analysis.json` and `security-report.html`
- Exploratory testing: `output/exploratory/<US or host>/` with `exploration.json`, `analysis.json`, `exploratory-report.html`, `screenshots/` and `videos/`. The previous run moves to `history/` (last 5).
- Accessibility: `output/accessibility/<US or host>/` with `audit.json`, `analysis.json`, `accessibility-report.html`, `screenshots/` and `videos/`. The previous run moves to `history/` (last 5).
- Web performance: `output/web-performance/<US or host>/` with `web-performance.json`, `analysis.json`, `web-performance-report.html`, `screenshots/` and `lighthouse/`. The previous run moves to `history/` (last 5).
- Failure analysis: `output/failures/<US or suite>/` with `failures.json`, `failures-report.html`, `runs/` and `evidence/`.
- Coverage and traceability: `output/coverage/<US or all>/` with `coverage.json` and `coverage-report.html`.
- Visual regression: `output/pixel-perfect/<US or host>/` with `reference/` (kept between runs), `actual/`, `diffs/`, `crops/`, `pixel-perfect.json`, `analysis.json` and `pixel-perfect-report.html`. The previous comparison moves to `history/` (last 5).
- Cross-browser: `output/cross-browser/<US, host or suite>/` with `cross-browser.json`, `cross-browser-report.html`, `screenshots/`, `diffs/` and `suite/` (the Cucumber report for each browser).
- Automation repair: `output/repairs/<US or suite>/` with `repairs.json`, `repair-report.html`, `screenshots/`, `changes.diff` and `backup/`.
- Case review: `output/case-review/<US or name>/` with `review.json` and `review-report.html`.
- Exploratory charters: `output/charters/<US or name>/` with `charters.json`, `charters.html`, `charters.md`, `sessions/CH-XX.md` and `sessions-report.html`.
- Usability: `output/ux/<US or host>/` with `ux.json`, `analysis.json`, `ux-report.html`, `screenshots/` and `crops/`. The previous run moves to `history/` (last 5).
- Forms: `output/forms/<US or host>/` with `forms.json`, `analysis.json`, `forms-report.html` and `screenshots/`. The previous run moves to `history/` (last 5).
- Logs: `output/logs/<name>/` with `logs.json`, `analysis.json` and `logs-report.html` (the input logs, in `input/logs/`). The previous analysis moves to `history/` (last 5).
- Emails: `output/emails/<US or mailbox>/` with `emails.json`, `analysis.json`, `emails-report.html`, `screenshots/` (desktop and mobile) and `eml/`. The previous run moves to `history/` (last 5).
- Translations: `output/translator/<US or host>/` with `translator.json`, `analysis.json`, `translator-report.html`, `screenshots/` and `crops/`. The previous run moves to `history/` (last 5).
- **History**: Each tool keeps its **last 5 runs** with their evidence in `history/` (inside its output folder; the one for `npm test`, in `tools/k0lmena/reports/<suite>/history/`) and each report includes the **Run evolution** section: what is new, what was resolved, what persists and how the indicators evolve, with the link to each run's report.
- Role permissions: `output/permissions/<US or host>/` with `permissions.json`, `analysis.json`, `permissions-report.html` and `screenshots/`. The previous run moves to `history/` (last 5).
- Resilience: `output/resilience/<US or host>/` with `resilience.json`, `resilience-report.html` and `screenshots/`. The previous run moves to `history/` (last 5).
- Bug triage: `output/triage/<bug or batch>/` with `candidates.json`, `triage.json` and `triage.md`. Consultations: `output/consultations/<topic>.md` (optional).
- Quality dashboard: `output/dashboard/<name>/` with `dashboard.json`, `analysis.json` and `dashboard-report.html`. Reports portal: `output/index.html`.
- Synthetic monitoring: `output/monitoring/<name>/` with `monitoring.json`, `monitoring-report.html` and `history/` (30 runs).
- Evals: `evals/results/<date>/` with `results.json` and `evals-report.html` (not versioned).
- Token usage: `output/token-metrics/<name>/` with `metrics.json` and `metrics-report.html`. Onboarding: `output/onboarding/<person>/` (name in lowercase, without accents and with hyphens) with `plan.json`, `onboarding-plan.html` and `onboarding-plan.md`.
- E-commerce: `output/shopify/<US or host>/` and `output/wordpress/<US or host>/` with `<platform>.json`, `analysis.json`, `<platform>-report.html` and `screenshots/`. The previous run moves to `history/` (last 5).
- Case selection: `output/case-selection/<name>/` with `selection.json`, `selection.csv` (the manual ones) and `selection-report.html`; the change built by the agent goes in `output/case-selection/_changes-<name>.json` (outside the run folder, which is archived when it is repeated).
- Test data: `data-US-001.md` (or `.csv`)
- API cases: `api-cases-US-001.md` (or `api-cases-<topic>.md` if they don't come from a story)
- Automation mapping: `tools/k0lmena/<web|api|mobile>/features/US-001-<slug>.feature` + `steps/US-001.steps.ts` + `locators/US-001.locators.ts`, and the report `output/mappings/mapping-US-001-<web|api|mobile>.md`.
- Performance: plan `output/performance/US-001/performance-plan-US-001.md` + report `performance-report-US-001.html` (and its `.json`) in the same folder; each run also leaves its report in `tools/k0lmena/reports/performance/`.
- E2E run (one report per run): `report-US-001-<date-time>.html` (dashboard, dark mode) + `_results-US-001-<date-time>.json` (data), in `output/runs/`; evidence in `output/runs/evidence/`. Each report covers only the cases of that run.
- API run (`api-runner`): `report-US-001-<date-time>.html` + `_results-US-001-<date-time>.json` in `output/runs/` (or `API` instead of the story if the run isn't for one).
- E2E evidence: `output/runs/evidence/<date-time>-<id>.png` (the same timestamp as the run: they don't overwrite each other).
- Test plan: `output/test-plans/plan-US-001-<date>.html` (date `YYYY-MM-DD`) and its `plan-US-001-<date>.json`.
- Closure report: `output/closure-reports/closure-US-001-<date>.html`, with its collected data in `data-US-001.json` (`scripts/collect_results.py`).
- Performance mapping: `output/mappings/mapping-US-001-performance.md`.

---

## Architecture (how the repo grows)

The repo rests on these pieces: **agents** (`.claude/agents/`, the who), **skills** (`.claude/skills/`, the how, loaded on demand), **MCP** (`.mcp.json`, connections to external systems — a single file that scales to many connections: Jira, Xray, Playwright…), **tools** (`tools/`, external testing tools, one subfolder per tool: Newman, **k0lmena**, OWASP ZAP, **streaming** (ffmpeg/ONVIF), **salesforce** (`sf` CLI), **ecommerce** (Shopify/WooCommerce/PrestaShop/VTEX), **sap** (SAP GUI Scripting), **desktop** (pywinauto), **security** (SCA/SAST: dependencies and code), **messaging** (Kafka/RabbitMQ/MQTT/WebSocket/SSE), **soap** (WSDL), **seo** (SEO/GEO), **resilience** (server-side chaos with Toxiproxy), **observability**, **documents** (PDF/Excel), **content** (typos) and **mutation** (mutation testing)) and **scripts** (`scripts/`, deterministic internal utilities). The details and how to extend each one are in `ARCHITECTURE.md`.

### Model per agent (token cost)

Each agent sets its model in the frontmatter (`model:`) so as not to overspend. Criteria by tier:

- **`haiku`** — mechanical work that mostly runs a script and builds the JSON/HTML (quality-dashboard, coverage-analyst, log-analyst, html-report-generator, test-case-selector, results-publisher, charter-generator, onboarding-guide).
- **`sonnet`** — most of the QA work (mappers, runners, case and data generators, testers —including `salesforce-tester`, `wallet-tester`, `shopify-tester`, `wordpress-tester`, `prestashop-tester`, `vtex-tester`, `sap-tester`, `desktop-tester`, `mobile-tester`, `ai-tester`, `messaging-tester`, `soap-tester`, `dependency-analyst`, `contract-tester`, `seo-analyst`, `data-tester`, `dynamics-tester`, `ivr-tester`, `game-tester`, `pos-tester`, `observability-analyst`, `search-tester`, `document-tester`, `content-reviewer` and `mutation-analyst`—, auditors, documenter, `project-researcher`, triager, failure analysis, repairer, manager, consultant, bug and closure reports…).
- **`opus`** — whatever requires the most reasoning or is sensitive: `story-analyst`, `security-analyst`, `web-pentester`, `camera-security-analyst`, `secure-code-analyst`, `blockchain-tester`.

A new agent gets its `model:` according to these criteria. The real cost per agent is measured by `scripts/token_metrics.py` (summarized by the quality dashboard): if one falls short on Haiku/Sonnet, move it up; if another doesn't need Opus, move it down.

## APIs: REST and GraphQL; Postman, Bruno and Insomnia

`api-runner` runs **Postman, Bruno or Insomnia** collections with Newman (`run_newman.py` converts Bruno and Insomnia with `scripts/convert_collection.py` and warns about whatever has no equivalent). `api-mapper` also automates **GraphQL** in k0lmena, with generic steps (`I send the GraphQL query:`, `the GraphQL response has no errors`, …) and the schema summarized by `scripts/summarize_graphql.py`; `api-case-generator` includes GraphQL cases (invalid variables, nonexistent fields, per-field authorization, partial errors, depth and pagination).

## Notifications, portal and monitoring

- **Notifications**: `scripts/notify.py` posts to Slack and Teams through the webhook in the `.env`. It is used by the triager (critical bug), the quality dashboard and monitoring, whenever requested or configured.
- **Portal**: `output/index.html` shows the latest report of each tool and regenerates on its own.
- **Synthetic monitoring**: `npm run monitor`, read-only, against any environment; it notifies when something breaks or recovers.

## Test management tools

`scripts/management/management.py` integrates **Xray Cloud, Xray Server/DC, QTM4J and AIO Tests** with the same commands (configured in the root `.env` with `MANAGEMENT_TOOL` and `MANAGEMENT_PROJECT`). **Azure DevOps** (Boards and Test Plans) is integrated through the `azure-devops` MCP connector, also configured in the `.env` (`ADO_ORGANIZATION`, `ADO_PAT`, `ADO_PROJECT`); the case steps are built by `scripts/management/to_azure_devops.py`. The local traceability file `output/management/<US>-<tool>.json` records which `TC-XXX` is which remote key. Details in `scripts/management/README.md`.

## Automation with k0lmena (token savings)

`tools/k0lmena/` is the automation framework (web, api, mobile and performance). The **mapper** agents write the automation **only once** (`k0lmena-automation` skill); after that the suite runs **with no agents and no tokens** with `cd tools/k0lmena && npm test` (performance: `npm run perf -- <script> <profile>`). To run already automated tests, prefer `npm test` over the live runners (`e2e-runner` / `api-runner`), which spend tokens on every run.

Secrets (tokens, credentials): they go in the local `.env` (gitignored) or in environment variables, **never** committed; there is a `.env.example` template. `.mcp.json` is versioned with the connectors that come enabled for everyone (Playwright and Atlassian: Jira and Confluence), so Claude Code starts without asking for approvals. The optional ones (Azure DevOps, Figma, GitHub, GitLab, Linear, ClickUp, monday.com, Asana, Trello, Notion, YouTrack, Shortcut, QMetry/QTM4J, AIO Tests, k0lmenaTMT, Appium) are enabled by each person with `npm run connector -- activate <name>`. None of them carries secrets: the ones that need a token read it from the `.env` with the scripts in `scripts/mcp/`. If an agent needs a connector that isn't enabled, or the person wants to connect a tool or configure the project, tell them to run **`npm run configure`** in a terminal (the VS Code one): it asks everything in English and enables the connectors. **Don't ask for tokens or passwords in the chat**: they go only in that wizard or in the `.env`. Details in `CONNECTORS.md`.

**Application repository:** the `project-documenter` reads it in read-only mode with its provider's connector (`github`, `gitlab`, `azure-devops` for Azure Repos or `atlassian` for Bitbucket Cloud), configured in the *Application repository* block of the `.env` (`REPO_PROVIDER`, `REPO_NAME`, `REPO_BRANCH`, `REPO_LOCAL_PATH`).

**External sources via MCP:** if the person gives a Jira key, an Azure DevOps work item, a Linear, ClickUp, monday.com, Asana, Trello, Notion, YouTrack or Shortcut task, a Confluence or Azure DevOps Wiki page, or a Figma link and the connector (`atlassian`, `azure-devops` or `figma`) is enabled, any agent can read them as input, just like a file in `input/` (traceability: cite the key, the page or the link). If the connector isn't enabled, ask for the content or explain how to enable it (`CONNECTORS.md`); don't assume it.
