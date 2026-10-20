// UI resilience testing (resilience-tester agent).
//
// Usage (from the repo root):
//   npm run resilience -- [--url https://my-app.com] [--pages url1,url2] [--max-pages 5] [--depth 1]
//                          [--scenarios api-500,timeout,slow,offline,empty,malformed,static]
//                          [--api-pattern "/api/"] [--timeout-ms 8000] [--story US-001] [--headed]
//
// For each page, it first loads it normally (the baseline) and then, in a clean context per scenario,
// simulates that what is "below" the UI fails and watches how it reacts:
//   api-500 · api-503 · api-404   API calls respond with that error
//   timeout                       API calls never respond (hung response)
//   slow                          slow network: 2 s latency and little bandwidth (Chromium, via CDP)
//   offline                       the page loads and then the connection is cut (and it tries to navigate)
//   empty · malformed · nulls     the API responds 200 with an empty body, broken JSON or all fields null
//   static                        CSS, JS, images and fonts do not load
// Per scenario: screenshot, JavaScript errors, console errors, visible error messages, whether it went
// blank, whether a spinner was left spinning, retries (the same call repeated), visible technical messages and
// whether the page recovers when the network comes back. It builds findings with severity.
//
// Safety: it only intercepts and responds FROM THE BROWSER. It does not attack the server or generate load: at most
// it makes the same number of requests as a normal visit (and in the failure scenarios, they do not even arrive).
// It does not submit forms: any navigation that is not GET is aborted.
// API calls are the fetch/XHR ones (or those matching --api-pattern). If a page makes no
// calls, the API scenarios are marked as "Not applicable".
//
// It leaves everything in output/resilience/<US or host>/ (resilience.json, resilience-report.html, screenshots/); the
// previous run moves to history/ (the last 5 are kept).
const fs = require('fs');
const path = require('path');
const { normalize, slug, stamp, load } = require('../explorer/explore.js');
const { discover } = require('../pixel-perfect/pixel-perfect.js');
const { archive } = require('../history/history.js');

const ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const fromCwd = (p) => path.resolve(process.env.INIT_CWD || process.cwd(), p);
const GENERATED = ['resilience.json', 'analysis.json', 'resilience-report.html', 'screenshots'];
const SEV_ORDER = { 'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3 };

const SCENARIOS = {
  'api-500': { name: 'The API responds 500', type: 'api', status: 500 },
  'api-503': { name: 'The API responds 503 (unavailable)', type: 'api', status: 503 },
  'api-404': { name: 'The API responds 404', type: 'api', status: 404 },
  timeout: { name: 'The API does not respond (timeout)', type: 'api' },
  slow: { name: 'Slow network (2 s latency)', type: 'network' },
  offline: { name: 'The connection is cut', type: 'network' },
  empty: { name: 'The API responds empty', type: 'api' },
  malformed: { name: 'The API responds broken JSON', type: 'api' },
  nulls: { name: 'The API responds with null fields', type: 'api' },
  static: { name: 'CSS, JS, images and fonts do not load', type: 'static' },
};
const STATIC = new Set(['stylesheet', 'script', 'image', 'font']);
// Technical messages that should not reach the person.
const TECHNICAL = /(Internal Server Error|Service Unavailable|SyntaxError|Unexpected (token|end of JSON)|TypeError|ReferenceError|\bundefined\b|\bNaN\b|\[object Object\]|stack ?trace|Traceback|Exception\b|at [\w.$]+ \(.*:\d+:\d+\))/;

function parseArgs(argv) {
  const a = { maxPages: 5, depth: 1, headed: false, timeoutMs: 8000, scenarios: Object.keys(SCENARIOS), apiPattern: null };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    const v = () => argv[++i];
    if (k === '--url') a.url = v();
    else if (k === '--pages') a.pages = v().split(',').map((x) => x.trim()).filter(Boolean);
    else if (k === '--max-pages') a.maxPages = parseInt(v(), 10);
    else if (k === '--depth') a.depth = parseInt(v(), 10);
    else if (k === '--scenarios') a.scenarios = v().split(',').map((x) => x.trim()).filter(Boolean);
    else if (k === '--api-pattern') a.apiPattern = v();
    else if (k === '--timeout-ms') a.timeoutMs = parseInt(v(), 10);
    else if (k === '--story') a.story = v();
    else if (k === '--output') a.output = v();
    else if (k === '--headed') a.headed = true;
    else if (k === '-h' || k === '--help') a.help = true;
    else throw new Error(`Unknown option: ${k}`);
  }
  const bad = a.scenarios.filter((x) => !SCENARIOS[x]);
  if (bad.length) throw new Error(`Unknown scenario: ${bad.join(', ')}. Options: ${Object.keys(SCENARIOS).join(', ')}`);
  if (!a.scenarios.length) throw new Error('--scenarios cannot be empty.');
  if (!(a.maxPages >= 1 && a.maxPages <= 50)) throw new Error('--max-pages must be between 1 and 50.');
  if (!(a.timeoutMs >= 1000 && a.timeoutMs <= 120000)) throw new Error('--timeout-ms must be between 1000 and 120000.');
  if (a.story && !/^[A-Za-z]+-\d+$/.test(a.story)) throw new Error('--story must be an ID like US-001.');
  if (a.apiPattern) new RegExp(a.apiPattern); // validates (throws if invalid)
  return a;
}

// Third-party analytics and telemetry: they are not the app's API (if they fail, nothing changes for the person).
const TELEMETRY = /(\/cdn-cgi\/|google-analytics|googletagmanager|doubleclick|analytics\.|\/collect\b|sentry|hotjar|segment\.(io|com)|clarity\.ms|newrelic|nr-data|datadoghq|mixpanel|amplitude|facebook\.com\/tr|fullstory|intercom)/i;

// Is the request an API call? By pattern (if one was passed) or by type (fetch / XHR), excluding telemetry.
function isApi(url, resourceType, pattern) {
  if (pattern) return new RegExp(pattern).test(url);
  return (resourceType === 'fetch' || resourceType === 'xhr') && !TELEMETRY.test(url);
}

// All leaf values set to null, keeping the structure (keys and list lengths).
function nullFields(v) {
  if (Array.isArray(v)) return v.map(nullFields);
  if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, nullFields(x)]));
  return null;
}

// Simulated response for an API scenario (null = no response: timeout; or the real response is needed).
function mockResponse(scenario, realBody) {
  const json = { 'Content-Type': 'application/json; charset=utf-8' };
  const e = SCENARIOS[scenario];
  if (e && e.status) return { status: e.status, headers: json, body: JSON.stringify({ error: e.status === 404 ? 'Not Found' : e.status === 503 ? 'Service Unavailable' : 'Internal Server Error' }) };
  if (scenario === 'empty') return { status: 200, headers: json, body: '' };
  if (scenario === 'malformed') return { status: 200, headers: json, body: '{"data": [{"id": 1, "name": "' };
  if (scenario === 'nulls') {
    let d = null;
    try { d = JSON.parse(realBody); } catch { return { status: 200, headers: json, body: 'null' }; }
    return { status: 200, headers: json, body: JSON.stringify(nullFields(d)) };
  }
  return null;
}

// The same call repeated: retries = extra times the most repeated URL was requested.
function countRetries(urls) {
  const c = new Map();
  for (const u of urls) c.set(u, (c.get(u) || 0) + 1);
  let max = 0;
  let url = null;
  for (const [u, n] of c) if (n > max) { max = n; url = u; }
  return { retries: Math.max(0, max - 1), url: max > 1 ? url : null };
}

// Runs in the browser: what the person sees.
function _observe() {
  const visible = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' && cs.opacity !== '0'; };
  const text = (el) => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  const body = document.body;
  const all = body ? text(body) : '';
  const elements = body ? [...body.querySelectorAll('*')].filter(visible).length : 0;
  const ERR = /(error|failed|could not|couldn't|unable to|try again|something went wrong|no connection|offline|problem|unavailable|retry|fall[oó]|no se pudo|no pudimos|intent[aá] (de nuevo|nuevamente|m[aá]s tarde)|sin conexi[oó]n|no disponible|algo sali[oó] mal|reintentar)/i;
  const candidates = [...document.querySelectorAll('[role=alert], [role=alertdialog], [role=status], [aria-live], .alert, .error, .toast, .notification, .snackbar, .message, h1, h2, h3, p, span, div')]
    .filter((el) => visible(el) && el.children.length <= 3);
  const messages = [...new Set(candidates.map(text).filter((t) => t.length > 3 && t.length < 220 && ERR.test(t)))].slice(0, 8);
  const SPIN = /(spin|loader|loading|cargando|skeleton|progress|busy)/i;
  const spinners = [...document.querySelectorAll('[aria-busy=true], [role=progressbar], progress, [class*=spin], [class*=load], [class*=skeleton], [class*=progress]')]
    .filter((el) => visible(el) && (el.getAttribute('aria-busy') === 'true' || el.getAttribute('role') === 'progressbar' || el.tagName === 'PROGRESS' || SPIN.test(el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className || ''))).length;
  return { url: location.href, title: document.title, text_len: all.length, elements, messages, spinners, sample: all.slice(0, 4000) };
}

// Findings of a scenario from the baseline and what was observed.
function evaluate(base, r) {
  const h = [];
  const add = (severity, type, title, detail) => h.push({ severity, type, title, detail });
  const e = SCENARIOS[r.scenario];
  if (r.status === 'not-applicable' || r.status === 'error') return h;
  const o = r.observed || {};
  const errorScreen = /^chrome-error:|^about:blank/.test(o.url || '');
  const textThreshold = Math.max(30, Math.round((base.text_len || 0) * 0.15));
  const elemThreshold = Math.max(5, Math.round((base.elements || 0) * 0.15));
  const blank = !errorScreen && ((o.text_len || 0) < textThreshold || (o.elements || 0) < elemThreshold);
  const technical = (o.sample || '').match(TECHNICAL);
  const newJs = (r.js_errors || []).filter((x) => !(base.js_errors || []).includes(x));

  if (r.scenario === 'offline') {
    if (errorScreen) add('Low', 'No connection', 'Without a connection, the app does not warn: the browser error page appears', 'When the connection is cut and you navigate, the browser error page shows up. If the app must work or warn without a connection, that handling is missing (service worker, its own message).');
    else if (!(o.messages || []).length && r.navigated) add('Medium', 'Silent failure', 'Without a connection, the app does not warn that there is no network', 'The connection was cut and navigation was attempted: the page shows no warning.');
  } else if (blank) {
    add(e.type === 'static' ? 'Medium' : 'High', 'Blank screen', `${e.name}: the screen is left almost empty`,
      `${o.text_len || 0} characters of text and ${o.elements || 0} visible elements remain (on the normal load: ${base.text_len} and ${base.elements}).`
      + ((o.messages || []).length ? '' : ' There is no message explaining what happened either.'));
  } else if (e.type === 'api' && r.intercepted > 0 && !(o.messages || []).length && r.content_change) {
    add('Medium', 'Silent failure', `${e.name}: the page changes but does not warn that something failed`,
      'Content that appears on the normal load is missing and there is no visible error message: the person does not know something went wrong or what to do.');
  }
  if ((o.spinners || 0) > 0 && (base.spinners || 0) === 0 && ['timeout', 'slow', 'api-500', 'api-503', 'api-404', 'malformed', 'empty', 'nulls'].includes(r.scenario)) {
    add(r.scenario === 'slow' ? 'Low' : 'Medium', 'Infinite loading', `${e.name}: a loading indicator is left spinning`,
      `After ${Math.round((r.wait_ms || 0) / 1000)} s a loading indicator is still visible (${o.spinners}). If the response never arrives, the person waits forever.`);
  }
  if (technical && !(base.sample || '').match(TECHNICAL)) {
    add('Medium', 'Technical message', `${e.name}: a technical message is visible`, `“${technical[0]}” appears on the screen. The person should see a clear message, not the internal error.`);
  }
  if (newJs.length) {
    add(e.type === 'static' ? 'Low' : 'Medium', 'JavaScript error', `${e.name}: uncaught JavaScript errors`,
      `${newJs.length} error(s) that do not appear on the normal load, for example: ${newJs[0]}`);
  }
  if (r.retries > 3) {
    add('Medium', 'Uncontrolled retries', `${e.name}: the same call is repeated ${r.retries + 1} times`,
      `${r.url_retries} was requested ${r.retries + 1} times in ${Math.round((r.wait_ms || 0) / 1000)} s. Without a limit or a wait between attempts, a server outage gets worse with the load of every user.`);
  }
  if (r.recovery && r.recovery.recovers === false) {
    add('High', 'Does not recover', `${e.name}: when the network comes back the page does not recover`,
      `After removing the failure and reloading, the page still has ${r.recovery.text_len} characters of text (normal: ${base.text_len}).`);
  }
  return h;
}

// Did the content change compared with the baseline? (an important part of the text is missing)
function contentChange(base, o) {
  if (!base || !o) return false;
  return (o.text_len || 0) < (base.text_len || 0) * 0.85;
}

function summarize(pages, findings) {
  const res = pages.flatMap((p) => p.results);
  return {
    pages: pages.length, scenarios: [...new Set(res.map((r) => r.scenario))].length, tests: res.length,
    ok: res.filter((r) => r.status === 'ok').length, with_findings: res.filter((r) => r.status === 'finding').length,
    not_applicable: res.filter((r) => r.status === 'not-applicable').length, errors: res.filter((r) => r.status === 'error').length,
    findings: findings.length, blank_screens: findings.filter((h) => h.type === 'Blank screen').length,
    no_recovery: findings.filter((h) => h.type === 'Does not recover').length,
    silent_failures: findings.filter((h) => h.type === 'Silent failure').length,
    by_severity: Object.fromEntries(Object.keys(SEV_ORDER).map((s) => [s, findings.filter((h) => h.severity === s).length])),
  };
}

function generateReport(folder) {
  const py = process.platform === 'win32' ? 'python' : 'python3';
  const r = require('child_process').spawnSync(py, [path.join(ROOT, 'scripts', 'generate_resilience_report.py'), path.join(folder, 'resilience.json'),
    path.join(folder, 'resilience-report.html')], { encoding: 'utf8' });
  if (r.status !== 0) {
    const reason = (r.stderr || r.error || '').toString().trim().split(/\r?\n/).pop();
    console.log(`Could not generate the HTML report (${reason}). Generate it with: python scripts/generate_resilience_report.py <folder>/resilience.json <folder>/resilience-report.html`);
    return false;
  }
  return true;
}

// Clean context with: submits blocked, error and request logging.
async function newContext(browser, reg) {
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, locale: process.env.LOCALE || 'en-US', serviceWorkers: 'block' });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => reg.js_errors.push(String(e.message || e).split('\n')[0].slice(0, 300)));
  page.on('console', (m) => { if (m.type() === 'error') reg.console.push(m.text().slice(0, 300)); });
  return { ctx, page };
}

async function observe(page) {
  return page.evaluate(_observe).catch(() => ({ url: page.url(), title: '', text_len: 0, elements: 0, messages: [], spinners: 0, sample: '' }));
}

async function baseline(browser, u, a) {
  const reg = { js_errors: [], console: [], api: [] };
  const { ctx, page } = await newContext(browser, reg);
  await page.route('**/*', (route) => {
    const rq = route.request();
    if (rq.isNavigationRequest() && rq.method() !== 'GET') return route.abort();
    if (isApi(rq.url(), rq.resourceType(), a.apiPattern)) reg.api.push(`${rq.method()} ${rq.url()}`);
    return route.continue();
  });
  const t0 = Date.now();
  let error = null;
  try { await load(page, u); } catch (e) { error = String(e.message || e).split('\n')[0]; }
  await page.waitForTimeout(800);
  const o = await observe(page);
  await ctx.close();
  return { ...o, time_ms: Date.now() - t0, js_errors: reg.js_errors, console: reg.console, api_calls: [...new Set(reg.api)], error };
}

async function runScenario(browser, u, scenario, base, a, shotsDir, n) {
  const e = SCENARIOS[scenario];
  const reg = { js_errors: [], console: [], api: [] };
  const r = { scenario, name: e.name, status: 'ok', intercepted: 0, retries: 0, url_retries: null, js_errors: [], console: [] };
  if (e.type === 'api' && !base.api_calls.length) {
    return { ...r, status: 'not-applicable', reason: 'The page makes no API calls on load (fetch/XHR).' };
  }
  const { ctx, page } = await newContext(browser, reg);
  const hung = [];
  let failing = true;
  await page.route('**/*', async (route) => {
    const rq = route.request();
    if (rq.isNavigationRequest() && rq.method() !== 'GET') return route.abort();
    if (!failing) return route.continue();
    const api = isApi(rq.url(), rq.resourceType(), a.apiPattern);
    if (api) reg.api.push(rq.url());
    if (e.type === 'static' && STATIC.has(rq.resourceType())) { r.intercepted++; return route.abort('failed'); }
    if (e.type !== 'api' || !api) return route.continue();
    r.intercepted++;
    if (scenario === 'timeout') { hung.push(route); return undefined; } // never responds
    let real = null;
    if (scenario === 'nulls') {
      const resp = await route.fetch().catch(() => null);
      real = resp ? await resp.text().catch(() => null) : null;
    }
    return route.fulfill(mockResponse(scenario, real)).catch(() => {});
  });
  let cdp = null;
  if (scenario === 'slow') {
    cdp = await ctx.newCDPSession(page).catch(() => null);
    if (cdp) await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 2000, downloadThroughput: 50 * 1024, uploadThroughput: 20 * 1024 }).catch(() => {});
    else r.note = 'The slow network uses CDP: it only works in Chromium.';
  }
  const t0 = Date.now();
  try {
    await page.goto(u, { waitUntil: 'domcontentloaded', timeout: a.timeoutMs * 3 });
    if (scenario === 'offline') {
      await page.waitForLoadState('load', { timeout: a.timeoutMs }).catch(() => {});
      await ctx.setOffline(true);
      // Tries to navigate to an internal link (or reload) to see what happens without a network.
      const href = await page.evaluate(() => { const l = [...document.querySelectorAll('a[href]')].find((x) => x.host === location.host && x.href !== location.href && !/logout|log-out|sign-?out|salir|delete|borrar/i.test(x.href)); return l ? l.href : null; }).catch(() => null);
      r.navigated = true;
      await page.goto(href || u, { timeout: a.timeoutMs }).catch(() => {});
    }
    await page.waitForTimeout(Math.min(a.timeoutMs, scenario === 'slow' ? a.timeoutMs : 6000));
  } catch (err) {
    r.load_error = String(err.message || err).split('\n')[0].slice(0, 200);
  }
  r.wait_ms = Date.now() - t0;
  r.observed = await observe(page);
  const cap = path.join(shotsDir, `${n}-${scenario}.png`);
  await page.screenshot({ path: cap, fullPage: false }).catch(() => {});
  if (fs.existsSync(cap)) r.screenshot = `screenshots/${path.basename(cap)}`;
  const rt = countRetries(reg.api);
  r.retries = e.type === 'api' ? rt.retries : 0;
  r.url_retries = rt.url;
  r.content_change = contentChange(base, r.observed);

  // Recovery: the failure is removed, the network comes back and the page is reloaded.
  failing = false;
  for (const c of hung) await c.abort('timedout').catch(() => {});
  if (scenario === 'offline') await ctx.setOffline(false).catch(() => {});
  if (cdp) await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 }).catch(() => {});
  try {
    await page.goto(u, { waitUntil: 'load', timeout: a.timeoutMs * 3 });
    await page.waitForTimeout(800);
    const o2 = await observe(page);
    r.recovery = { text_len: o2.text_len, elements: o2.elements, recovers: o2.text_len >= (base.text_len || 0) * 0.6 };
    const cap2 = path.join(shotsDir, `${n}-${scenario}-recovery.png`);
    if (!r.recovery.recovers) {
      await page.screenshot({ path: cap2 }).catch(() => {});
      if (fs.existsSync(cap2)) r.recovery_screenshot = `screenshots/${path.basename(cap2)}`;
    }
  } catch { r.recovery = { recovers: null }; }
  r.js_errors = [...new Set(reg.js_errors)];
  r.console = [...new Set(reg.console)].slice(0, 10);
  await ctx.close().catch(() => {});
  if (e.type === 'api' && r.intercepted === 0) return { ...r, status: 'not-applicable', reason: 'In this scenario the page never called the API.' };
  if (scenario === 'static' && r.intercepted === 0) return { ...r, status: 'not-applicable', reason: 'The page does not load static resources.' };
  return r;
}

async function main() {
  const a = parseArgs(process.argv.slice(2));
  if (a.help) {
    console.log(fs.readFileSync(__filename, 'utf8').split('\n').filter((l) => l.startsWith('//')).map((l) => l.slice(3)).join('\n'));
    return;
  }
  const url = a.url || (a.pages && a.pages[0]) || process.env.APP_URL || process.env.BASEURL;
  if (!url) throw new Error('No URL: pass it with --url or set APP_URL in the root .env.');
  if (!/^https?:\/\//i.test(url)) throw new Error(`The URL must start with http:// or https:// (got "${url}").`);
  const start = normalize(url);
  const host = new URL(start).hostname;
  const folder = a.output ? fromCwd(a.output) : path.join(ROOT, 'output', 'resilience', a.story || host);
  archive(folder, GENERATED, 'resilience.json');
  for (const n of GENERATED) fs.rmSync(path.join(folder, n), { recursive: true, force: true });
  const shotsDir = path.join(folder, 'screenshots');
  fs.mkdirSync(shotsDir, { recursive: true });
  const relRoot = (p) => path.relative(ROOT, p).split(path.sep).join('/');
  const { chromium } = require('playwright'); // here and not at the top: the tests use the functions without installing k0lmena
  const browser = await chromium.launch({ headless: !a.headed });
  const t0 = Date.now();
  const ctx0 = await browser.newContext();
  const p0 = await ctx0.newPage();
  await p0.route('**/*', (route) => (route.request().isNavigationRequest() && route.request().method() !== 'GET' ? route.abort() : route.continue()));
  const urls = await discover(p0, start, a);
  await ctx0.close();
  console.log(`Resilience: ${urls.length} page(s) × ${a.scenarios.length} scenario(s) · output ${relRoot(folder)}`);

  const pages = [];
  const findings = [];
  for (const [i, u] of urls.entries()) {
    const n = `${String(i + 1).padStart(2, '0')}-${slug(u)}`;
    const base = await baseline(browser, u, a);
    const capBase = path.join(shotsDir, `${n}-base.png`);
    {
      const c = await browser.newContext({ viewport: { width: 1366, height: 900 } });
      const pg = await c.newPage();
      await pg.goto(u, { waitUntil: 'load', timeout: 30000 }).catch(() => {});
      await pg.screenshot({ path: capBase }).catch(() => {});
      await c.close();
    }
    console.log(`[${i + 1}/${urls.length}] ${u} · ${base.api_calls.length} API call(s) · ${base.text_len} characters`);
    const page = { url: u, id: n, base: { ...base, sample: undefined }, baseline_screenshot: fs.existsSync(capBase) ? `screenshots/${path.basename(capBase)}` : null, results: [] };
    for (const sc of a.scenarios) {
      let r;
      try { r = await runScenario(browser, u, sc, base, a, shotsDir, n); } catch (err) {
        r = { scenario: sc, name: SCENARIOS[sc].name, status: 'error', reason: String(err.message || err).split('\n')[0] };
      }
      const hs = evaluate(base, r).map((h) => ({ ...h, scenario: sc, page: u, screenshot: r.recovery_screenshot || r.screenshot || null }));
      if (r.status === 'ok' && hs.length) r.status = 'finding';
      r.findings = hs;
      if (r.observed) delete r.observed.sample;
      findings.push(...hs);
      page.results.push(r);
      process.stdout.write(`    ${sc.padEnd(11)} ${r.status}${hs.length ? ` (${hs.map((h) => h.type).join(', ')})` : ''}\n`);
    }
    pages.push(page);
  }
  await browser.close();
  findings.sort((x, y) => SEV_ORDER[x.severity] - SEV_ORDER[y.severity]);
  findings.forEach((h, i) => { h.id = `R-${String(i + 1).padStart(2, '0')}`; });
  for (const p of pages) for (const r of p.results) r.findings = (r.findings || []).map((h) => h.id);
  const result = {
    url: start, host, story: a.story || null, date: new Date().toISOString(), stamp: stamp(), duration_s: Math.round((Date.now() - t0) / 1000),
    tool: `Playwright ${require('playwright/package.json').version}`, timeout_ms: a.timeoutMs, api_pattern: a.apiPattern,
    scenarios: a.scenarios.map((id) => ({ id, name: SCENARIOS[id].name, type: SCENARIOS[id].type })),
    summary: summarize(pages, findings), findings, pages,
  };
  const output = path.join(folder, 'resilience.json');
  fs.writeFileSync(output, JSON.stringify(result, null, 2), 'utf8');
  const r = result.summary;
  console.log(`\nTests: ${r.tests} · with findings: ${r.with_findings} · not applicable: ${r.not_applicable} · findings: ${r.findings}`);
  console.log(`Data: ${relRoot(output)}`);
  if (generateReport(folder)) console.log(`Report: ${relRoot(path.join(folder, 'resilience-report.html'))}`);
}

if (require.main === module) {
  main().catch((e) => { console.error(`Error: ${e.message}`); process.exit(1); });
}

module.exports = { parseArgs, isApi, nullFields, mockResponse, countRetries, evaluate, contentChange, summarize, SCENARIOS, GENERATED };
