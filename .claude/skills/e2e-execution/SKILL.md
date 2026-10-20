---
name: e2e-execution
description: How to run end-to-end tests in the browser with Playwright MCP robustly — choose headed or headless mode, locate elements via the accessibility snapshot, wait to avoid flakiness, capture evidence, and translate a test case or BDD scenario into browser actions. Use it when running live web tests with Playwright MCP (e2e-runner and web-mapper).
---

# E2E Execution with Playwright MCP

The "how" for running tests in a real browser with Playwright MCP, reliably and reproducibly.

## Headed vs headless mode

Playwright MCP runs the browser **headed (visible) by default**; with `--headless` it runs in the background. This repo has two servers in `.mcp.json`:

- **`playwright`** → headed (you see the browser; ideal for demos and for following the run).
- **`playwright-headless`** → headless (background; faster, good for CI).

Use the mode the request asks for (if it doesn't say, return it under "I need you to confirm"; recommended: headless) and the tools of the matching server. All actions (navigate, click, screenshot) work the same in both modes.

## Locating elements (no brittle selectors)

Playwright MCP exposes the page as an **accessibility snapshot**: each element has a role and an accessible name (e.g. textbox "Email", button "Sign up", combobox "Country"). Locate elements by role + name, not by brittle CSS/XPath. That makes the run more stable against UI changes.

## Waits (avoiding flakiness)

- Before acting, make sure the element is present and stable.
- If an element doesn't show up, take a **new snapshot** and retry with a short wait before declaring a failure. Many "failures" are timing, not bugs.

## Translating a test case into actions

- **BDD (`.feature`)**: each `Given/When/Then` → navigate / fill in / click / select / verify.
- **Manual test case**: the **Steps** field → the sequence of actions; **Expected result** → the final verification.

## Login and credentials

If the app under test requires login, the credentials **do not go in the code or the repo**: they go in a **`.env`** file at the root (it's in `.gitignore`, never committed). There is a **`.env.example`** template with the variable names; copy it to `.env` and fill in the real values:

```bash
cp .env.example .env   # then edit .env with your data
```

Typical variables: `APP_URL`, `APP_USER`, `APP_PASSWORD`. The agent reads them from `.env` (or receives them in the prompt) and uses them **only** to log in: it never writes them in the report, the JSON or the screenshots, and never commits them. Use credentials from a **test/staging** environment, not production.

**Saved session (`npm run login`):** the person runs `npm run login` (or `npm run login -- --name <role>`), logs in by hand in the browser that opens (works for captcha, 2FA or SSO) and the session is stored in `.auth/` (gitignored). With `SESSION=yes` (or `SESSION=<role>`) in `.env`, the Playwright servers start with that session (`--isolated --storage-state`) and the app opens already logged in: **there's no need to go through the login**, unless the test case is precisely about the login. If the login screen shows up anyway while navigating, the session expired: don't replace it with the credentials without saying so; report it in the result and suggest running `npm run login` again. `npm run login` is interactive: the person runs it, not the agent.

## Evidence

- Take a screenshot **on every failure** and **one at the end**; avoid screenshots at every step (fewer screenshots = faster).
- Name each screenshot `<date-time>-<id>.png` (e.g. `20260618-1432-tc-004.png`, with the same timestamp as the run: that way runs don't overwrite each other) and put it in `output/runs/evidence/`. Playwright MCP saves to its `--output-dir` (in this repo it already points there); by default, without that option, it uses `.playwright-mcp/`. If the screenshot ended up somewhere else, move it to `evidence/` using the path the tool returns.
- In the report, the `evidence` is referenced **relative to the HTML** (`evidence/<date-time>-<id>.png`), which is why the report and the `evidence/` folder live together in `output/runs/`. (In some versions `--output-dir` may be ignored; it's worth confirming the file landed in `evidence/`.)

## Report

For each test case: status (**Passed / Failed / Blocked**) and, on a failure, the step that failed, expected vs. actual, and the link to the screenshot.

When the run finishes, the HTML report (dark mode) is **generated automatically** with `scripts/generate_report.py`: it is the output of the run, nobody has to ask for it. It's **one report per run** —it covers only the executed test cases— and it carries `<date-time>` in the name so it doesn't overwrite previous ones.

## When you finish

- **Close the browser** with `browser_close` (don't leave the window open).
- **Don't leave junk behind**: the output is the HTML report, the `_results-*.json` and the screenshots. Don't save snapshots as `.yml`/`.yaml` or `.log` logs (use the in-memory snapshots). If anything is left lying around in `output/runs/` or `.playwright-mcp/`, delete it.

## Speed and permissions

- The repo ships `.claude/settings.json`, which **pre-approves the servers** (`enabledMcpjsonServers`) —so Claude Code doesn't ask about Playwright **when the project starts**— and also their **tools** (`mcp__playwright__*`), so it doesn't ask for permission on every action. If a prompt shows up anyway, choose *Always allow*.
- **Headless** (`playwright-headless`) runs faster than headed (it doesn't render the window).
- **Fewer screenshots**: capture only on failure and at the end.
- The server version is already pinned (`scripts/mcp/launch.js`), so startups are consistent; the first time `npx` downloads it and afterwards it uses the cache.
- **Be specific** in the request (URL, data, what to validate): fewer exploratory steps = faster.

## Prerequisites

- The **app running** (reachable URL).
- Browsers installed: `npx playwright install` (on Linux, also `npx playwright install-deps`).

The details of the Playwright MCP tools, robustness tips and a worked example are in [`references/playwright-mcp.md`](references/playwright-mcp.md).
