// Manual login and saved session (npm run login).
//
// Opens the browser on the app, you log in by hand (captcha, 2FA, SSO… whatever it asks for) and it saves the
// session (cookies, localStorage and IndexedDB) in .auth/ at the repo root. It is then used by:
//   - the k0lmena web suites (npm test), with SESSION=yes in the .env;
//   - the agents' browser (Playwright MCP), when writing or running cases, with the same variable.
//
// Usage (from the repo root):
//   npm run login                         -> .auth/session.json, on LOGIN_URL or APP_URL
//   npm run login -- --name admin         -> .auth/session-admin.json (one session per role)
//   npm run login -- --url https://my-app.com/sign-in
//
// When you finish logging in, go back to the terminal and press Enter (or close the browser).
// The session file is equivalent to a password: it is in .gitignore and is not shared.
const fs = require('fs');
const path = require('path');
const readline = require('readline');
const { sessionFile, ROOT } = require('./session');

function parseArgs(argv) {
  const opts = { url: '', name: '' };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--url' || a === '--name') {
      const v = argv[++i];
      if (!v || v.startsWith('--')) throw new Error(`missing value for ${a}`);
      opts[a.slice(2)] = v;
    } else if (a === '-h' || a === '--help') {
      opts.help = true;
    } else {
      throw new Error(`unknown option: ${a}`);
    }
  }
  if (opts.url && !/^https?:\/\//i.test(opts.url)) throw new Error(`invalid URL: ${opts.url}`);
  sessionFile(opts.name); // validates the name
  return opts;
}

/** Resolves when the person presses Enter in the terminal (if there is an interactive terminal). */
function waitForEnter() {
  if (!process.stdin.isTTY) return { promise: new Promise(() => {}), close: () => {} };
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  const promise = new Promise((resolve) => rl.once('line', () => resolve('enter')));
  return { promise, close: () => rl.close() };
}

/** Resolves when all the context's tabs are closed. */
function waitForClose(context) {
  return new Promise((resolve) => {
    const check = () => { if (context.pages().length === 0) resolve('close'); };
    const watch = (p) => p.on('close', check);
    context.pages().forEach(watch);
    context.on('page', watch);
  });
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (opts.help) {
    console.log('Usage: npm run login -- [--url https://my-app.com/login] [--name admin]');
    return;
  }
  const url = opts.url || process.env.LOGIN_URL || process.env.APP_URL;
  if (!url) throw new Error('no URL: pass --url or set APP_URL in the .env');
  const file = sessionFile(opts.name);
  const relative = path.relative(ROOT, file).split(path.sep).join('/');

  const { chromium } = require('playwright');
  const browser = await chromium.launch({ headless: false });
  const enter = waitForEnter();
  try {
    const context = await browser.newContext({
      viewport: null, // the window at its normal size, to log in comfortably
      locale: (process.env.LOCALE ?? 'en-US').trim(),
      timezoneId: (process.env.TIMEZONE ?? 'America/New_York').trim(),
    });
    const page = await context.newPage();
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });

    console.log(`\nThe browser opened on ${url}`);
    console.log('1. Log in as you normally would.');
    console.log(process.stdin.isTTY
      ? '2. Once you are in, come back here and press Enter (or close the browser).\n'
      : '2. Once you are in, close the browser.\n');

    const closed = new Promise((_, reject) =>
      browser.on('disconnected', () => reject(new Error('the browser was closed before the session was saved'))));
    await Promise.race([enter.promise, waitForClose(context), closed]);

    fs.mkdirSync(path.dirname(file), { recursive: true });
    const state = await context.storageState({ path: file, indexedDB: true });
    const cookies = state.cookies.length;
    const origins = state.origins.filter((o) => (o.localStorage?.length || 0) + (o.indexedDB?.length || 0) > 0).length;

    console.log(`Session saved to ${relative} (${cookies} cookies, ${origins} origins with data).`);
    if (cookies === 0 && origins === 0) {
      console.log('Warning: no cookie or local data was saved. Did you actually log in?');
    }
    const value = opts.name || 'yes';
    console.log(`To use it in npm test and in the agents' browser: SESSION=${value} in the .env`);
    console.log("(the agents' browser picks up the change when Claude Code restarts).");
    console.log('When the session expires, run this command again.');
  } finally {
    enter.close();
    await browser.close().catch(() => undefined);
  }
}

if (require.main === module) {
  main().catch((e) => {
    console.error(`login: ${e.message}`);
    process.exit(1);
  });
}

module.exports = { parseArgs };
