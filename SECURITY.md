# Security

## Scope

k0lmenIA is a set of **QA tools that run locally or in CI** (Playwright, Cucumber, WebdriverIO, Appium, k6/Artillery/JMeter, OWASP ZAP). **It is not an internet-facing service** that processes third-party input: the inputs (stories, URLs to test, collections, configs) belong to your own team.

Secrets (tokens, credentials, connection strings) go **only** in the local `.env` (gitignored) or in environment variables, never committed. There is a template in `.env.example`.

The `security-analyst` agent scans **only** the URLs in `SECURITY_AUTHORIZED_URLS`, in passive mode; the `web-pentester` runs active scans only with `PENTEST_AUTHORIZED=yes`, against your own site or with written authorization, and never against production without permission.

## Known vulnerabilities in dependencies (accepted risk)

As of **2026-10-18**, `npm audit` on `tools/k0lmena` reports 39 **transitive** vulnerabilities in dependencies of **development/test tools** (artillery, appium, webdriverio, lighthouse, percy, puppeteer). The safe `npm audit fix` (without `--force`) was applied; the rest **is not fixed** because the "fix" npm proposes breaks the framework:

| Advisory (package) | Severity | npm "fix" | Why it is not applied |
|---|---|---|---|
| `shell-quote` | critical | `appium@3.4.2` | Downgrades appium → breaks the mobile suite |
| `braces`, `csv-parse`, `sprintf-js` | high / moderate | `artillery@0.0.2` | Downgrades to an empty stub → breaks performance |
| `basic-ftp`, `extract-zip` | high | `webdriverio@10.0.2` | Jump to WebdriverIO 10 (see below) |

**Why the risk is low in this context:** almost all of them are DoS via malicious input (ReDoS in the `basic-ftp` FTP parser, nested patterns in `braces`, `csv-parse`, `sprintf-js`) or injection in `shell-quote`. Exploiting them requires an attacker to control that specific input (an FTP listing, a glob pattern, a CSV, a shell token); in normal k0lmena use those inputs come from the team, not from third parties, and nothing runs as a public service.

**Do not use `npm audit fix --force`:** it downgrades artillery and appium to unusable versions.

## How they will be resolved (without breaking anything)

When the upstream ecosystem publishes the patches:

- **WebdriverIO 10** — when `@wdio/browserstack-service` publishes its version 10 (it does not exist yet), the whole `@wdio/*` + `webdriverio` stack moves to 10: this clears `basic-ftp` and `extract-zip`.
- **artillery** with a patched release → clears `braces`, `csv-parse`, `sprintf-js`.
- **appium** with a patched `shell-quote` → clears the critical one.
- **TypeScript 7** — upgraded once `ts-node` supports it (today TS 7, the native rewrite, breaks `ts-node`, which the whole framework depends on).

**Next review: 2026-11-18.** Run `cd tools/k0lmena && npm audit` again and apply whatever already has a compatible patch; upgrade the majors (WDIO 10, TS 7) only when their dependencies catch up.

## Reporting an issue

If you find a security issue in this repository, email **info@underc0de.org** instead of opening a public issue.
