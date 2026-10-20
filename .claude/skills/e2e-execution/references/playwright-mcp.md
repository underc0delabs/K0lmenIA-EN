# Playwright MCP — execution reference

Details for the `e2e-execution` skill: setup, main tools, robustness, and a worked example.

## Setup (reminder)

- In this repo the server is already in `.mcp.json` (headed and headless): `scripts/mcp/playwright.js` starts it with Microsoft's official one (`@playwright/mcp`), the evidence folder and `--secrets .env` (hides those values in the responses).
- Browsers: `npx playwright install` (they take ~700 MB; on Linux also `npx playwright install-deps`).
- The version is pinned in `scripts/mcp/launch.js` (never `@latest`), to avoid failures caused by changes between versions; to try another one: `PLAYWRIGHT_MCP_MCP_VERSION=<version>`.
- Gotcha: the first time, name **"Playwright MCP"** in the request; otherwise it sometimes tries to run Playwright through Bash instead of the MCP.

## Main tools

- **Navigate**: open a URL, go back/forward, reload.
- **Accessibility snapshot**: get the page structure (roles + names) to locate elements.
- **Interaction**: click, type/fill fields, select from a dropdown, keys, hover.
- **Screenshot**: capture the page or an element.
- **Console / network**: read console messages and requests (useful for debugging a failure).

## Robustness

- **Selectors**: by role + accessible name (textbox "Email"), not brittle CSS/XPath.
- **Waits**: wait for visibility/stability before acting; retry with a new snapshot on "not found" before marking a failure.
- **Data**: never make it up; ask for the URL and data if they're missing.
- **Clean state**: for an isolated run, the server can run with `--isolated` (each session starts from scratch).

## Worked example — valid signup (AC1 of US-001)

Scenario: create an account with valid data at https://qarmy.ar/practica/automation/.

1. Navigate to the URL.
2. Snapshot → locate the fields by their name.
3. Fill in: First name "Mary", Last name "Johnson", Gender "Female", Email "mary.johnson@test.com", Country "United States", Username "mary_johnson", Password "Aa123456!".
4. Click "Sign up".
5. Verify the successful signup confirmation (whatever the page shows) and take a screenshot.
6. Result: **Passed** if the confirmation appears; otherwise, **Failed** with the details + screenshot.

Negative test cases (for example an invalid email, a password without a symbol, a 3-character username) follow the same flow, verifying that the **error message** of the corresponding field appears.
