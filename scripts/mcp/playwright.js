#!/usr/bin/env node
// Launcher for the playwright and playwright-headless MCP connectors (see CONNECTORS.md).
// Starts Playwright's official server with the repo's evidence folder and, if the root .env exists,
// with --secrets .env: Playwright hides those values (passwords, tokens) in the responses the model
// sees. Without a .env it starts anyway (the server fails if the file doesn't exist).
//
// With SESSION in the .env (see tools/k0lmena/tools/login/session.js) it starts with the session
// saved by npm run login: --isolated --storage-state .auth/session[-<name>].json.
//
// Usage (in .mcp.json): node scripts/mcp/playwright.js [--headless]
const fs = require('fs');
const path = require('path');
const { launchNpx, ROOT } = require('./launch');
const { variable } = require('./read-env');
const { activeSession } = require('../../tools/k0lmena/tools/login/session');

const args = ['--output-dir', 'output/runs/evidence'];
if (process.argv.includes('--headless')) args.push('--headless');
if (fs.existsSync(path.join(ROOT, '.env'))) args.push('--secrets', '.env');

let session = null;
try {
  session = activeSession(variable('SESSION'), (msg) => console.error(`playwright: ${msg}`));
} catch (e) {
  console.error(`playwright: ${e.message}; continuing without a session.`);
}
if (session) {
  // Relative to the root (the server runs there) and with /: the npx command line only accepts simple paths.
  args.push('--isolated', '--storage-state', path.relative(ROOT, session).split(path.sep).join('/'));
}
launchNpx('playwright', '@playwright/mcp', args);
