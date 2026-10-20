<p align="center">
<img src="https://i.imgur.com/jrStTTp.png" width="400px">
</p>

<h1 align="center">k0lmena Automation Framework</h1>

<p align="center">
<b>All-in-one</b> automation framework (web, API, mobile and performance), integrated into k0lmenIA.<br>
A copy of the original repo <a href="https://github.com/underc0delabs/k0lmena">underc0delabs/k0lmena</a>, reorganized by test type.
</p>

---

## How it fits into k0lmenIA

The **mapper** agents write the automation only once, and from then on the suite runs **without agents and without consuming tokens**:

```
test cases (output/test-cases/)
        │
        ├── web-mapper     → walks the website (Playwright MCP)  → web/features + steps + locators
        ├── api-mapper     → reads Postman / Swagger             → api/features
        ├── mobile-mapper  → walks the app (Appium MCP)          → mobile/features + steps + locators
        │                                                                │
        │                                                          npm test  (no tokens)
        └── performance-mapper → load and thresholds (asks)      → performance/k6 · artillery · jmeter
                                                                         │
                                                               npm run perf  (no tokens)
```

## Structure

```
tools/k0lmena/
├── web/            Playwright + Cucumber
│   ├── features/   .feature (one per story: US-001-<slug>.feature)
│   ├── steps/      step definitions (US-001.steps.ts)
│   ├── locators/   locators (US-001.locators.ts)
│   ├── hooks/ config/ utils/   framework: browser, helpers, auto-healing
├── api/            axios + Cucumber
│   ├── features/
│   └── steps/      common.steps.ts = generic steps in English
├── mobile/         WebdriverIO + Appium (Android / iOS)
│   ├── features/ steps/ locators/
│   ├── support/    wdio.conf.ts (device, emulator or BrowserStack) and hooks
│   └── apps/       your .apk / .ipa (not versioned)
├── performance/    k6 (k6/http/), Artillery + Playwright (artillery/) and JMeter (jmeter/)
├── reports/        HTML reports for each type
├── tools/          locator crawler, link tester, recorder, debug
├── cucumber.js     web / api / debug profiles
├── run-tests.js    npm test runner
└── env.js          loads the single .env at the k0lmenIA root
```

## Installation

Requires **Node.js 20+** (22+ if you are going to use the mobile-mapper). It includes the PostgreSQL, MySQL / MariaDB, SQL Server and MongoDB drivers for the database checks.

```bash
cd tools/k0lmena
npm install
npx playwright install chromium     # or: npx playwright install (all browsers)
# Variables: k0lmena uses the .env at the ROOT of the repo (there is no other one).
# If it does not exist yet, from the root:  cp .env.example .env
```

## Run

```
+---------------------+-----------------------------------+
| Command             | What it runs                      |
+=====================+===================================+
| npm test            | web + api                         |
+---------------------+-----------------------------------+
| npm run test:web    | web only                          |
+---------------------+-----------------------------------+
| npm run test:api    | api only                          |
+---------------------+-----------------------------------+
| npm run test:mobile | mobile only (per MOBILE_TARGET)   |
+---------------------+-----------------------------------+
| npm run test:all    | web + api + mobile                |
+---------------------+-----------------------------------+
```

**Filter by tag** with the `TAGS` variable (or by setting it in the root `.env`):

```bash
TAGS=@US-001 npm test                 # bash
$env:TAGS="@US-001"; npm test         # PowerShell
TAGS="@smoke and not @wip" npm run test:web
```

Scenarios tagged `@blocked` (steps the mapper could not verify in the app) **never run**. Those tagged `@missing-info @MI-XX` depend on data that is not defined in the story or its sources: they run normally and the report adds a **Missing information** note to them (details in `output/context/`).

### Saved session (`npm run login`)

To avoid logging in on every scenario (or when the login has a captcha, 2FA or SSO):

```bash
npm run login                        # opens the browser: you log in by hand and press Enter in the terminal
npm run login -- --name admin        # one session per role: .auth/session-admin.json
npm run login -- --url https://my-app.com/login
```

The session (cookies, localStorage and IndexedDB) is stored in `.auth/` at the root (gitignored: it is equivalent to a password). To use it, set `SESSION=yes` (or `SESSION=admin`) in the `.env`: every web scenario starts logged in, and so does the agents' browser (Playwright MCP) after restarting Claude Code. Scenarios tagged `@no-session` (the ones that test the login) always start without a session. If the session expires, run `npm run login` again.

### Mobile: device, emulator or BrowserStack

It is chosen in the root `.env`, without touching code:

```
+-----------------+-----------------------------------------+
| MOBILE_TARGET   | Needs                                   |
+=================+=========================================+
| device          | USB device with debugging enabled,      |
|                 | MOBILE_UDID (adb devices), app in       |
|                 | mobile/apps/                            |
+-----------------+-----------------------------------------+
| emulator        | Emulator/simulator running,             |
|                 | MOBILE_DEVICE_NAME, app in mobile/apps/ |
+-----------------+-----------------------------------------+
| browserstack    | BROWSERSTACK_USER, BROWSERSTACK_KEY and |
|                 | BROWSERSTACK_APP (bs://...)             |
+-----------------+-----------------------------------------+
```

`MOBILE_PLATFORM` sets Android (UiAutomator2) or iOS (XCUITest).

### Performance

```bash
npm run bootstrap:k6                       # once: downloads k6 into tools/k6 (or have it in the PATH)
npm run bootstrap:jmeter                   # once: downloads JMeter into tools/jmeter (needs Java 8+)
npm run perf                               # lists the scripts (k6, Artillery and JMeter)
npm run perf -- <script> smoke             # validates the script with minimal load
npm run perf -- <script> load              # target load: asks for confirmation
npm run perf -- <script> stress --confirm  # no prompt (CI or an agent with authorization)
npm run perf -- <script> load --vus 20 --duration 2m   # k6 and JMeter: overrides the script's load
```

- **Profiles**: `smoke` (minimal load, validates the script), `load` (sustained target load), `stress` (1x, 2x and 3x), `soak` (long duration) and `spike` (sudden peak). Profiles with load ask for confirmation.
- **Scripts**: k6 in `performance/k6/http/<script>.ts` (base in `performance/k6/lib/k0lmena.ts`: `loadOptions({...})` and `request()`); Artillery in `performance/artillery/<script>.yaml` + `.ts` processor; JMeter in `performance/jmeter/<script>.jmx` + `<script>.json` (`target`, load per profile in `profiles` and `thresholds`; template in `performance/jmeter/template/`). Templates in the `k0lmena-automation` skill.
- **Unique names**: the same script name cannot exist in two tools (for example, `US-001-login.ts` in k6 and `US-001-login.jmx` in JMeter): `npm run perf` stops and asks you to rename one, so the wrong one is not run.
- **Thresholds**: in the script (`thresholds` in k6, `ensure` in Artillery) or in the `.jmx`'s `.json` (JMeter). If any of them is not met, the run ends with exit code 1.
- **Output** in `reports/performance/<k6|artillery|jmeter>/`: HTML report (dashboard), JSON summary, raw result and the tool's log; with JMeter, also its native dashboard (`<run>-dashboard/`). The console only shows the summary.

## Database

Read-only checks on **PostgreSQL, MySQL / MariaDB, SQL Server and MongoDB**, with the connections from the root `.env` (`DB_CONNECTIONS` + `DB_<NAME>_*`, see `.env.example`).

```bash
npm run db -- connections                              # lists and tests the connections
npm run db -- schema --table users                     # columns of a table (or fields of a collection)
npm run db -- exists --table users --where email=ana@test.com
npm run db -- query --sql "SELECT id, status FROM users WHERE email = ?" --param ana@test.com
```

The agents add these checks to a `.feature` **only when asked to**; without `DB_CONNECTIONS` in the `.env`, the suite runs as always. In the `.feature` files (web, API or mobile) the steps from `tools/db/db.steps.ts` are available: `the database has a record in "users" where "email" is "…"`, `the "users" record where "id" is "{userId}" has:` (field/value table), `I query the database:` (SQL or, in MongoDB, JSON) and more; the full list is in the `k0lmena-automation` skill. Reads run in read-only transactions that are discarded, and sensitive data is masked in the report. Writing is only possible from the CLI (`write … --confirm`), with `DB_<NAME>_WRITE=yes` and never on connections marked `DB_<NAME>_PRODUCTION=yes`.

## Reports

```
+--------------------------+--------------------------+
| Command                  | Report                   |
+==========================+==========================+
| npm run report:web       | HTML of the web suite    |
+--------------------------+--------------------------+
| npm run report:api       | HTML of the api suite    |
+--------------------------+--------------------------+
| npm run report:mobile    | HTML of the mobile suite |
+--------------------------+--------------------------+
| npm run perf -- <script> | Perf. HTML (automatic)   |
+--------------------------+--------------------------+
```

`npm test` builds the web and api report on its own (`reports/<suite>/index.html`) at the end of each suite, and that is the one the reports portal links to; `npm run report:web` / `report:api` regenerate it. It reflects **only the last run** (the previous one moves to `history/`).

### Attached evidence

```
+---------+------------------------------+------------------------------------------+
| Suite   | Passing scenario             | Failing scenario                         |
+=========+==============================+==========================================+
| web     | Final screenshot (+ opt. GIF)| Full video, screenshot, error with       |
|         |                              | stack, URL and page title, browser logs  |
|         |                              | (console, JS errors, failed requests,    |
|         |                              | HTTP responses >= 400), Node logs and    |
|         |                              | Playwright trace                         |
+---------+------------------------------+------------------------------------------+
| api     | Full request and response    | The same, plus the error of the          |
|         |                              | validation that failed                   |
+---------+------------------------------+------------------------------------------+
| mobile  | Final screenshot (+ opt. GIF)| Full video, screenshot, page source and  |
|         |                              | device logs (logcat / syslog)            |
+---------+------------------------------+------------------------------------------+
```

They are controlled from the root `.env`:

- `EVIDENCE`: what is saved from passing scenarios. `screenshot` (final screenshot), `both` (screenshot + **walkthrough GIF**, one screenshot per step; adds ~0.5 s per scenario) or `off`. **If it is empty, `npm test` asks for it at startup**; in CI or without an interactive terminal it uses `screenshot`.
- `VIDEO`: `on-failure` (default), `on` or `off`.
- `TRACE`: `on-failure`, `on` or `off`.

In the report, the GIF and the video open from the scenario's attachments, and the trace is downloaded to open it at [trace.playwright.dev](https://trace.playwright.dev). In API the `Authorization` header is masked.

Loose files: `reports/web/videos/`, `traces/`, `screenshots/` and `evidence/` (mobile: `reports/mobile/html/videos/`, `screenshots/` and `evidence/`).

## Locator auto-healing (web)

With `K0LMENA_AUTO_HEALING=on`, every successful action saves alternative locators for the element (`learn`) and, if the original locator fails, it tries those candidates (`heal`). When it heals one, it reports it in the console as `HEALED: <original> -> <candidate>`. Modes: `off`, `learn`, `heal`, `on` (recommended).

## Tools

```
+------------------------+------------------------------------------+
| Command                | What for                                 |
+========================+==========================================+
| npm run crawler [url]  | Generates a locators file by crawling a  |
|                        | page                                     |
+------------------------+------------------------------------------+
| npm run link-tester    | Looks for broken links and images        |
|                        | (APP_URL)                                |
+------------------------+------------------------------------------+
| npm run explore        | Exploratory crawl with a browser: links, |
|                        | images, errors and responsive (agent     |
|                        | web-explorer)                            |
+------------------------+------------------------------------------+
| npm run accessibility  | WCAG 2.2 audit with axe-core, keyboard   |
|                        | and reflow at 320px (agent               |
|                        | accessibility-analyst)                   |
+------------------------+------------------------------------------+
| npm run                | Lighthouse on mobile and desktop: Core   |
| web-performance        | Web Vitals and improvement opportunities |
|                        | (agent web-performance-auditor)          |
+------------------------+------------------------------------------+
| npm run pixel-perfect  | Visual regression against a reference:   |
|                        | pixel by pixel and per element (agent    |
|                        | pixel-perfect)                           |
+------------------------+------------------------------------------+
| npm run cross-browser  | Suite or pages in Chromium, Firefox and  |
|                        | WebKit (agent cross-browser)             |
+------------------------+------------------------------------------+
| npm run repair         | Diagnoses, proposes, applies and         |
|                        | verifies broken locators (agent          |
|                        | automation-repairer)                     |
+------------------------+------------------------------------------+
| npm run emails         | Checks the emails in the Mailpit test    |
|                        | mailbox (agent email-verifier)           |
+------------------------+------------------------------------------+
| npm run translator     | Every page in every language:            |
|                        | translation, truncation and formats      |
|                        | (agent translation-analyst)              |
+------------------------+------------------------------------------+
| npm run ux             | Nielsen heuristics on desktop and mobile |
|                        | (agent ux-evaluator)                     |
+------------------------+------------------------------------------+
| npm run forms          | Validations of each field without        |
|                        | submitting the form (agent form-tester)  |
+------------------------+------------------------------------------+
| npm run functional-map | Pages, menus, forms and messages of the  |
|                        | site, for the documentation (agent       |
|                        | project-documenter)                      |
+------------------------+------------------------------------------+
| npm run permissions    | Role × route and role × endpoint matrix  |
|                        | (agent permissions-tester)               |
+------------------------+------------------------------------------+
| npm run resilience     | Simulated API, network and resource      |
|                        | failures (agent resilience-tester)       |
+------------------------+------------------------------------------+
| npm run monitor        | Read-only synthetic monitoring, with an  |
|                        | alert if something breaks or recovers    |
+------------------------+------------------------------------------+
| npm run record         | Records a flow with Playwright codegen   |
+------------------------+------------------------------------------+
| npm run debug          | Runs web in debug mode (sequential, with |
|                        | logs)                                    |
+------------------------+------------------------------------------+
```

## Credits

k0lmena is an open source project (ISC license) by **Danilo Vezzoni**. Video: https://youtu.be/n7plezXinZ8
