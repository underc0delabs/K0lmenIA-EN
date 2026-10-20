// Cross-browser testing: Chromium (Chrome and Edge), Firefox and WebKit (Safari) (cross-browser agent).
//
// Usage (from the repo root):
//   npm run cross-browser -- [--mode suite|pages] [--browsers chromium,firefox,webkit]
//                            [--resolutions 1366x768,390x844] [--tags "@US-001"] [--story US-001]
//                            [--url https://my-app.com] [--pages url1,url2] [--max-pages 6]
//                            [--base chromium] [--tolerance-px 6] [--threshold 0.1] [--hide ".banner"] [--headed]
//                            [--retries 2]
//
// Two modes (by default, suite if there are .feature files in web/features; otherwise, pages):
//   suite   → runs the k0lmena web suite (npm test) once per browser and resolution, each one
//             in its own folder (it does not overwrite the last npm test), and builds the scenario × browser matrix:
//             what passes in all, what fails in all (not a browser problem) and what fails only
//             in some (difference between browsers: what this test looks for). Runs against the
//             environment like npm test: it may create data.
//   pages   → walks the site's pages in each browser and resolution (GET only) and compares
//             against the base browser: JavaScript errors, console errors and resources that fail only
//             in one browser, horizontal overflow, elements that are missing or shift, style
//             changes and percent of the screen that looks different.
//
// Against false positives: what fails only in one browser is confirmed before reporting it.
// In suite, the scenario is repeated in that browser (--retries, 2 by default): if it passes, it is
// "Flaky" and not a difference. In pages, the page is reloaded in all the browsers: if the
// error does not repeat it is intermittent, and if it shows up in another one, it is discarded. Also errors are
// compared by their source and their own words (each engine words them differently), each engine's console
// noise is ignored, scrollbars are hidden and shifts caused by text measurement
// weigh little (they matter if something ends up off screen).
//
// Browsers that are not installed are reported with the command to install them
// (npx playwright install firefox webkit). WebKit is Safari's engine; on Windows and Linux it is a
// very good approximation, but it does not replace testing on a real Safari on Mac or iPhone.
//
// Leaves everything in output/cross-browser/<US, host or suite>/ and each run REPLACES the previous one:
// cross-browser.json, cross-browser-report.html, screenshots/, diffs/, crops/ and suite/.
const fs = require('fs');
const path = require('path');
const { archive } = require('../history/history.js');
const { spawnSync } = require('child_process');
const { normalize, slug, stamp, walkScroll, load } = require('../explorer/explore.js');
const { parseResolutions, discover } = require('../pixel-perfect/pixel-perfect.js');
const visual = require('../visual/compare.js');

const ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const fromCwd = (p) => path.resolve(process.env.INIT_CWD || process.cwd(), p); // npm run changes the cwd to tools/k0lmena
const K0 = path.resolve(__dirname, '..', '..');
const GENERATED = ['cross-browser.json', 'analysis.json', 'cross-browser-report.html', 'screenshots', 'diffs', 'crops', 'suite'];
const BROWSERS = ['chromium', 'firefox', 'webkit'];
const NAME = { chromium: 'Chromium (Chrome, Edge)', firefox: 'Firefox', webkit: 'WebKit (Safari)' };
const SEV_ORDER = { Critical: 0, High: 1, Medium: 2, Low: 3 };

// ------------------------------------------------------------------ errors and resources across engines
// Each engine words the SAME error differently: Chromium "Cannot read properties of undefined (reading
// 'total')", Firefox "can't access property \"total\", e is undefined", WebKit "undefined is not an
// object (evaluating 'e.total')". Comparing the exact text flagged as "only in Firefox" errors that
// happen in all of them. They are compared by the code location (file:line:column) or by the error's
// own words (names of variables, properties and URLs), without each engine's vocabulary.
const GENERIC = new Set(('cannot can not read properties property access accessing undefined null is are of the to on in at for from with ' +
  'reading setting set get function object objects not defined uncaught error typeerror referenceerror syntaxerror rangeerror evaluating ' +
  'invalid unexpected token failed execute because was has been this that its value values type too much recursion maximum call stack ' +
  'size exceeded promise rejection unhandled script line column constructor instance assignment const variable before initialization ' +
  'lexical declaration').split(' '));

/** URL without query or hash: the same resource with another cache-buster is the same resource. */
function resourceKey(u) {
  try { const x = new URL(u); return `${x.origin}${x.pathname}`; } catch { return String(u).split(/[?#]/)[0]; }
}

/** Own words of an error message (without each engine's generic ones) and its URLs. */
function errorTokens(text) {
  const s = new Set();
  const URLS = /(?:https?|file):\/\/[^\s'"`)]+/g;
  for (const u of String(text).match(URLS) || []) s.add(resourceKey(u.replace(/:\d+(:\d+)?$/, '')));
  for (const w of String(text).replace(URLS, ' ').match(/[A-Za-z_$][\w$]*/g) || []) {
    const l = w.toLowerCase();
    if (l.length >= 3 && !GENERIC.has(l)) s.add(l);
  }
  return s;
}

/** file:line:column of the first frame with a URL in a stack (Chromium "at f (url:l:c)", Firefox/WebKit "f@url:l:c"). */
function sourceOf(stack) {
  const m = String(stack || '').match(/((?:https?|file):\/\/[^\s)]+?):(\d+):(\d+)/);
  return m ? `${resourceKey(m[1])}:${m[2]}:${m[3]}` : null;
}

/** Are they the same error (or console message) in two engines? */
function sameError(a, b) {
  if (a.source && b.source && a.source === b.source) return true;
  if (a.message === b.message) return true;
  const ta = errorTokens(a.message);
  const tb = errorTokens(b.message);
  return [...ta].some((t) => tb.has(t));
}

// Console messages that depend on the engine and not on the app: they are not incompatibilities.
const CONSOLE_NOISE = [
  /^Failed to load resource/i, // Chromium and WebKit write it for every failing resource (Firefox does not); resources are checked separately
  /source ?map/i,
  /downloadable font/i,
  /^Cookie\b.*(rejected|expired|SameSite)/i,
  /Partitioned cookie|storage access/i,
  /Feature Policy|Permissions[- ]Policy/i,
  /Quirks Mode|Layout was forced|character encoding/i,
  /preload(ed)?\b.*\bnot used/i,
];
const isConsoleNoise = (t) => CONSOLE_NOISE.some((r) => r.test(t));

// Canceled requests (the browser aborted the download: navigation, lazy load, preload): they are not failures.
const isCanceled = (t) => /ABORT|cancel/i.test(String(t || ''));
// Resources each browser requests on its own (Firefox requests /favicon.ico even if the page does not declare it).
const isBrowserOwnResource = (u) => /\/favicon\.ico$|apple-touch-icon/i.test(resourceKey(u)) || /^(data|blob):/i.test(u);

// The errors of the two engines (or of the two reloads) are compared for these finding types.
const RUNTIME = new Set(['JavaScript error', 'Console error', 'Failed resource', 'Different response']);
const VISUAL = new Set(['Missing element', 'Shifted block', 'Shifted element', 'Different style', 'Looks different']);

/** Maximum per-channel distance between two #rrggbb colors (or Infinity if one is not a color). */
function colorDistance(a, b) {
  const p = (c) => (/^#[0-9a-f]{6}$/i.test(c) ? [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16)) : null);
  const x = p(a);
  const y = p(b);
  if (!x || !y) return a === b ? 0 : Infinity;
  return Math.max(...x.map((v, i) => Math.abs(v - y[i])));
}

function parseArgs(argv) {
  const a = { browsers: BROWSERS, base: 'chromium', maxPages: 6, depth: 1, tolerance: 6, threshold: 0.1, hide: [], headed: false, retries: 2 };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    const v = () => argv[++i];
    if (k === '--mode') a.mode = v().toLowerCase();
    else if (k === '--browsers') a.browsers = v().split(',').map((x) => x.trim().toLowerCase()).filter(Boolean);
    else if (k === '--resolutions') a.resolutions = v();
    else if (k === '--tags') a.tags = v();
    else if (k === '--story') a.story = v();
    else if (k === '--url') a.url = v();
    else if (k === '--pages') a.pages = v().split(',').map((x) => x.trim()).filter(Boolean);
    else if (k === '--max-pages') a.maxPages = parseInt(v(), 10);
    else if (k === '--depth') a.depth = parseInt(v(), 10);
    else if (k === '--base') a.base = v().toLowerCase();
    else if (k === '--tolerance-px') a.tolerance = parseInt(v(), 10);
    else if (k === '--threshold') a.threshold = parseFloat(v());
    else if (k === '--hide') a.hide = v().split(',').map((x) => x.trim()).filter(Boolean);
    else if (k === '--output') a.output = v();
    else if (k === '--headed') a.headed = true;
    else if (k === '--retries') a.retries = parseInt(v(), 10);
    else if (k === '-h' || k === '--help') a.help = true;
    else throw new Error(`Unknown option: ${k}`);
  }
  const bad = a.browsers.filter((n) => !BROWSERS.includes(n));
  if (bad.length) throw new Error(`Unknown browser: ${bad.join(', ')}. Options: ${BROWSERS.join(', ')}.`);
  if (a.mode && !['suite', 'pages'].includes(a.mode)) throw new Error('--mode: suite or pages.');
  if (!a.browsers.includes(a.base)) a.base = a.browsers[0];
  if (!Number.isInteger(a.retries) || a.retries < 0 || a.retries > 5) throw new Error('--retries: a number from 0 to 5.');
  return a;
}

// Is it installed and does it start? Returns the version or the reason.
async function testBrowser(name) {
  const pw = require('playwright');
  try {
    const b = await pw[name].launch();
    const version = b.version();
    await b.close();
    return { name, ok: true, version };
  } catch (e) {
    const msg = String(e.message || e);
    const missing = /Executable doesn't exist|browserType\.launch.*install|Please run the following command/i.test(msg);
    return { name, ok: false, error: missing ? 'Not installed' : msg.split('\n')[0].slice(0, 200),
      install: missing ? `cd tools/k0lmena && npx playwright install ${name}` : null };
  }
}

function hasFeatures() {
  const dir = path.join(K0, 'web', 'features');
  return fs.existsSync(dir) && fs.readdirSync(dir).some((f) => f.endsWith('.feature'));
}

// ------------------------------------------------------------------ suite mode
// Playwright errors carry terminal color codes: they are stripped to read them.
const stripAnsi = (s) => String(s).replace(/\x1b\[[0-9;]*m/g, '');

function readCucumber(file) {
  let features = [];
  try { features = JSON.parse(fs.readFileSync(file, 'utf8') || '[]'); } catch { return []; }
  const output = new Map();
  for (const f of features) {
    for (const sc of f.elements || []) {
      if (sc.type === 'background') continue;
      const tags = [...new Set([...(f.tags || []), ...(sc.tags || [])].map((t) => t.name.replace(/^@/, '')))];
      let status = 'Passed';
      let step = null;
      let error = '';
      let dur = 0;
      const screenshots = [];
      for (const p of sc.steps || []) {
        const r = p.result || {};
        dur += r.duration || 0;
        const kw = (p.keyword || '').trim();
        if (r.status === 'failed' || r.status === 'ambiguous') {
          status = 'Failed';
          if (!step) step = `${kw} ${p.name || ''}`.trim();
          if (!error) error = stripAnsi(r.error_message || '').trim();
        } else if (['undefined', 'pending'].includes(r.status) && status !== 'Failed') {
          status = 'Failed';
          step = step || `${kw} ${p.name || ''}`.trim();
          error = error || `Step ${r.status === 'undefined' ? 'undefined' : 'pending'}`;
        } else if (r.status === 'skipped' && status === 'Passed' && !['Before', 'After'].includes(kw)) status = 'Skipped';
        for (const emb of p.embeddings || []) if (emb.mime_type === 'image/png') screenshots.push(emb.data);
      }
      const key = `${f.uri}:${sc.line}`;
      // With retry, the same scenario appears more than once: the last attempt counts.
      output.set(key, { key, scenario: sc.name, feature: f.name, uri: f.uri, line: sc.line, tags,
        story: tags.find((t) => /^US-\d+$/i.test(t)) || null, case: tags.find((t) => /^TC(-API)?-\d+$/.test(t)) || null,
        status, step, error: error.slice(0, 3000), duration_s: Math.round(dur / 1e7) / 100, _screenshot: screenshots[screenshots.length - 1] });
    }
  }
  return [...output.values()];
}

// cucumber-js with node directly (no shell: .feature names with spaces or & do not break anything).
function runCucumber(env, extra = []) {
  let bin = null;
  try {
    const pkg = require.resolve('@cucumber/cucumber/package.json', { paths: [K0] });
    const b = require(pkg).bin;
    bin = path.join(path.dirname(pkg), typeof b === 'string' ? b : b['cucumber-js']);
  } catch { /* no exported package.json: npx is used */ }
  const options = { cwd: K0, env, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 };
  if (bin && fs.existsSync(bin)) return spawnSync(process.execPath, [bin, '--profile', 'web', ...extra], options);
  return spawnSync('npx cucumber-js --profile web', { ...options, shell: true });
}

function envSuite(a, c, dir) {
  const env = { ...process.env, BROWSER: c.browser, REPORT_DIR: dir, VIEWPORT_WIDTH: String(c.res.width),
    VIEWPORT_HEIGHT: String(c.res.height), EVIDENCE: 'screenshot', HEADLESS: a.headed ? 'false' : 'true' };
  if (a.tags) env.TAGS = a.tags;
  return env;
}

function runSuite(a, combos, folder, rel) {
  const dirSuite = path.join(folder, 'suite');
  const dirShots = path.join(folder, 'screenshots');
  const runs = [];
  for (const c of combos) {
    const dir = path.join(dirSuite, c.id);
    fs.mkdirSync(dir, { recursive: true });
    process.stdout.write(`Web suite on ${c.id.padEnd(18)} `);
    const t0 = Date.now();
    const r = runCucumber(envSuite(a, c, dir));
    const scenarios = readCucumber(path.join(dir, 'cucumber-report.json'));
    for (const e of scenarios) {
      if (e._screenshot) {
        const file = path.join(dirShots, `${c.id}-${slug(`http://x/${e.case || ''}-${e.scenario}`)}.png`);
        fs.writeFileSync(file, Buffer.from(e._screenshot, 'base64'));
        e.screenshot = rel(file);
      }
      delete e._screenshot;
    }
    const passed = scenarios.filter((e) => e.status === 'Passed').length;
    const out = `${r.stdout || ''}\n${r.stderr || ''}`;
    const generalFailure = !scenarios.length ? out.trim().split(/\r?\n/).filter(Boolean).slice(-6).join('\n') : null;
    console.log(scenarios.length ? `→ ${passed}/${scenarios.length} passed (${Math.round((Date.now() - t0) / 1000)} s)` : '→ no results');
    runs.push({ ...c, res: c.res.id, scenarios, duration_s: Math.round((Date.now() - t0) / 1000), error: generalFailure,
      report: fs.existsSync(path.join(dir, 'front-report.html')) ? rel(path.join(dir, 'front-report.html')) : null });
  }
  return runs;
}

// A scenario that fails only in one browser is repeated there (a.retries times, until it passes):
// a one-time failure is flakiness (timing, data, network), not an incompatibility.
// Stores `retries` in each scenario: the status of each repetition.
function confirmSuite(a, combos, runs, folder) {
  if (!a.retries) return 0;
  const { rows } = analyzeSuite(runs);
  let repeated = 0;
  for (const f of rows.filter((x) => x.class === 'Browser difference')) {
    for (const [comboId, r] of Object.entries(f.results)) {
      if (r.status !== 'Failed') continue;
      const c = combos.find((x) => x.id === comboId);
      const sc = runs.find((x) => x.id === comboId).scenarios.find((e) => e.key === f.key);
      sc.retries = [];
      for (let i = 1; i <= a.retries; i++) {
        const dir = path.join(folder, 'suite', `${comboId}-retry`, String(repeated + 1));
        fs.mkdirSync(dir, { recursive: true });
        process.stdout.write(`Retrying on ${comboId.padEnd(18)} ${f.scenario.slice(0, 50)} (${i}/${a.retries}) `);
        runCucumber(envSuite(a, c, dir), [`${f.uri}:${f.line}`]);
        const other = readCucumber(path.join(dir, 'cucumber-report.json')).find((e) => e.key === f.key);
        const status = other ? other.status : 'No result';
        sc.retries.push(status);
        repeated++;
        console.log(`→ ${status}`);
        if (status === 'Passed') break;
      }
    }
  }
  return repeated;
}

const comboTxt = (id) => { const [n, r] = id.split('-'); return `${NAME[n] ? NAME[n].split(' ')[0] : n} ${r || ''}`.trim(); };
const listTxt = (ids) => ids.map(comboTxt).join(', ');

const BY_TIMEOUT = /timeout|timed out|exceeded/i;

function analyzeSuite(runs) {
  const keys = new Map();
  for (const c of runs) for (const e of c.scenarios) if (!keys.has(e.key)) keys.set(e.key, e);
  const rows = [];
  const findings = [];
  for (const [key, e0] of keys) {
    const res = {};
    for (const c of runs) {
      const e = c.scenarios.find((x) => x.key === key);
      // It failed, but passed when repeated: flaky in that browser, not incompatible.
      const status = e && e.status === 'Failed' && (e.retries || []).includes('Passed') ? 'Flaky' : e && e.status;
      res[c.id] = e ? { status, step: e.step, error: e.error, screenshot: e.screenshot, duration_s: e.duration_s, ...(e.retries ? { retries: e.retries } : {}) }
        : { status: c.error ? 'No result' : 'Did not run' };
    }
    const statuses = Object.values(res).map((x) => x.status);
    const failing = Object.entries(res).filter(([, x]) => x.status === 'Failed').map(([k]) => k);
    const passing = Object.entries(res).filter(([, x]) => x.status === 'Passed').map(([k]) => k);
    const flaky = Object.entries(res).filter(([, x]) => x.status === 'Flaky').map(([k]) => k);
    let cls;
    if (statuses.every((s) => s === 'Passed')) cls = 'Passes in all';
    else if (failing.length && !passing.length && !flaky.length) cls = 'Fails in all';
    else if (failing.length) cls = 'Browser difference';
    else if (flaky.length && statuses.every((s) => s === 'Passed' || s === 'Flaky')) cls = 'Flaky';
    else cls = 'Incomplete result';
    rows.push({ key, scenario: e0.scenario, feature: e0.feature, uri: e0.uri, line: e0.line, story: e0.story,
      case: e0.case, class: cls, results: res });
    const ident = [e0.story, e0.case].filter(Boolean).join(' · ');
    if (cls === 'Browser difference') {
      const err = res[failing[0]];
      const allPass = [...passing, ...flaky];
      const repeated = failing.every((k) => (res[k].retries || []).length);
      const byTimeout = BY_TIMEOUT.test(err.error || '');
      const notes = [];
      if (repeated) notes.push(`It was repeated and failed again (${failing.map((k) => `${comboTxt(k)}: ${res[k].retries.length + 1} of ${res[k].retries.length + 1}`).join(', ')}).`);
      else notes.push('It failed only once: without repeating it you cannot tell whether it is the browser or flakiness.');
      if (byTimeout) notes.push('It fails by timeout: that engine may just be slower (check the step waits) and not an incompatibility.');
      findings.push({ type: 'Fails only in some browsers', severity: repeated && !byTimeout ? 'High' : 'Medium', confirmed: repeated,
        title: `${ident ? `${ident} · ` : ''}${e0.scenario}: fails in ${listTxt(failing)} and passes in ${listTxt(allPass)}`,
        detail: `Failing step: ${err.step || '—'}. ${(err.error || '').split('\n')[0].slice(0, 220)} ${notes.join(' ')}`.trim(),
        scenario: key, failing, passing: allPass, error: err.error, step: err.step,
        evidence: [...failing, ...allPass.slice(0, 1)].map((k) => ({ combo: k, status: res[k].status, screenshot: res[k].screenshot })).filter((x) => x.screenshot) });
    } else if (cls === 'Flaky') {
      const err = res[flaky[0]];
      findings.push({ type: 'Flaky', severity: 'Low', confirmed: false,
        title: `${ident ? `${ident} · ` : ''}${e0.scenario}: failed in ${listTxt(flaky)} and passed when repeated`,
        detail: 'It is not a difference between browsers: the scenario is flaky (timing, data or network). Analyze it with the failure-analyst. ' +
          `First attempt: ${err.step || '—'}. ${(err.error || '').split('\n')[0].slice(0, 200)}`,
        scenario: key, failing: [], passing: Object.keys(res), flaky, error: err.error, step: err.step,
        evidence: flaky.map((k) => ({ combo: k, status: 'Flaky', screenshot: res[k].screenshot })).filter((x) => x.screenshot) });
    } else if (cls === 'Fails in all') {
      const err = res[failing[0]];
      findings.push({ type: 'Fails in all browsers', severity: 'Medium',
        title: `${ident ? `${ident} · ` : ''}${e0.scenario}: fails in all browsers`,
        detail: 'It is not a difference between browsers: it is a bug or a broken test in any browser (analyze it with the failure-analyst). ' +
          `Step: ${err.step || '—'}. ${(err.error || '').split('\n')[0].slice(0, 200)}`,
        scenario: key, failing, passing: [], error: err.error, step: err.step,
        evidence: failing.slice(0, 1).map((k) => ({ combo: k, status: 'Failed', screenshot: res[k].screenshot })).filter((x) => x.screenshot) });
    }
  }
  return { rows, findings };
}

// ------------------------------------------------------------------ pages mode
// Context of each combination. Firefox does not support isMobile: on mobile it only emulates the size and the
// touch screen, and its visual differences on mobile weigh less (see analyzePages).
function contextOptions(c) {
  const mobile = c.res.width < 768;
  return { viewport: { width: c.res.width, height: c.res.height }, deviceScaleFactor: 1, locale: process.env.LOCALE || 'en-US',
    ...(mobile ? { hasTouch: true, ...(c.browser !== 'firefox' ? { isMobile: true } : {}) } : {}) };
}

// What happens when running the page: JavaScript errors (with the code location), console errors
// (without each engine's own noise), failing resources and which resources were requested.
function listen(page, m) {
  m._errors = [];
  m._console = [];
  m._failed = [];
  m._requests = new Set();
  page.on('pageerror', (e) => m._errors.push({ message: String(e.message || e).split('\n')[0].slice(0, 300), source: sourceOf(e.stack) }));
  page.on('console', (msg) => {
    if (msg.type() !== 'error') return;
    const message = msg.text().slice(0, 300);
    if (isConsoleNoise(message)) return;
    const loc = msg.location() || {};
    m._console.push({ message, source: loc.url ? `${resourceKey(loc.url)}:${loc.lineNumber}:${loc.columnNumber}` : null });
  });
  page.on('request', (rq) => m._requests.add(resourceKey(rq.url())));
  page.on('requestfailed', (rq) => {
    const f = rq.failure();
    if (f && !isCanceled(f.errorText) && !isBrowserOwnResource(rq.url())) m._failed.push({ url: rq.url(), error: f.errorText });
  });
  page.on('response', (rs) => {
    if (rs.status() >= 400 && rs.request().resourceType() !== 'document' && !isBrowserOwnResource(rs.url())) {
      m._failed.push({ url: rs.url(), error: `HTTP ${rs.status()}` });
    }
  });
}

// Leaves in m what was heard, without duplicates (the details to compare and the texts for the report).
function closeListener(m) {
  const unique = (xs) => [...new Map(xs.map((x) => [x.message, x])).values()];
  m.js_errors_det = unique(m._errors);
  m.console_errors_det = unique(m._console);
  m.js_errors = m.js_errors_det.map((x) => x.message);
  m.console_errors = m.console_errors_det.map((x) => x.message);
  m.failed_resources = [...new Map(m._failed.map((r) => [resourceKey(r.url), r])).values()];
  delete m._errors; delete m._console; delete m._failed;
}

// Opens the page in a new context and measures only the runtime part (for the confirmation reload).
async function measureRun(browser, c, u) {
  const ctx = await browser.newContext(contextOptions(c));
  const m = { url: u, combo: c.id };
  try {
    const page = await ctx.newPage();
    listen(page, m);
    const { resp } = await load(page, u);
    m.status = resp ? resp.status() : 0;
    await walkScroll(page);
  } catch (e) {
    m.error = String(e.message || e).split('\n')[0].slice(0, 200);
  } finally {
    if (m._errors) closeListener(m);
    await ctx.close().catch(() => {});
  }
  return m;
}

async function walkPages(a, combos, pages, folder, rel) {
  const pw = require('playwright');
  const dirShots = path.join(folder, 'screenshots');
  const measures = {}; // `${page}|${combo}` → data
  for (const c of combos) {
    const browser = await pw[c.browser].launch({ headless: !a.headed });
    try {
      for (const [i, u] of pages.entries()) {
        const id = `${String(i + 1).padStart(2, '0')}-${slug(u)}`;
        process.stdout.write(`[${c.id.padEnd(18)}] ${u} `);
        const ctx = await browser.newContext(contextOptions(c));
        const page = await ctx.newPage();
        const m = { page: id, url: u, combo: c.id, browser: c.browser, resolution: c.res.id };
        listen(page, m);
        try {
          const { resp, ms } = await load(page, u);
          m.status = resp ? resp.status() : 0;
          m.time_ms = ms;
          // Same usable width in all engines (see CSS_NO_SCROLLBAR).
          await page.addStyleTag({ content: visual.CSS_NO_SCROLLBAR }).catch(() => {});
          await walkScroll(page);
          await page.evaluate(() => window.scrollTo(0, 0));
          await visual.stabilize(page, { hide: a.hide });
          const med = await visual.measureElements(page);
          m.elements = med.elements;
          m.height = med.height;
          m.overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
          const file = path.join(dirShots, `${id}-${c.id}.png`);
          const height = Math.min(med.height, 10000);
          await page.screenshot({ path: file, fullPage: height === med.height, timeout: 30000,
            ...(height < med.height ? { clip: { x: 0, y: 0, width: c.res.width, height } } : {}) });
          m.screenshot = rel(file);
          m._file = file;
          console.log(`→ ${m.status} · ${m._errors.length} JS error(s)`);
        } catch (e) {
          m.error = String(e.message || e).split('\n')[0].slice(0, 200);
          console.log(`→ error: ${m.error}`);
        }
        closeListener(m);
        measures[`${id}|${c.id}`] = m;
        await ctx.close().catch(() => {});
      }
    } finally {
      await browser.close().catch(() => {});
    }
  }
  return measures;
}

const textEl = (e) => (e.text ? `“${e.text.slice(0, 50)}”` : e.desc);
const box = (e) => ({ x: e.x, y: e.y, w: e.w, h: e.h });
const lowerTo = (sev, cap) => (SEV_ORDER[sev] < SEV_ORDER[cap] ? cap : sev);

function analyzePages(a, combos, pages, measures, folder, rel) {
  const dirDiff = path.join(folder, 'diffs');
  const dirCrop = path.join(folder, 'crops');
  const findings = [];
  const rows = [];
  const resols = [...new Set(combos.map((c) => c.res.id))];
  for (const [i, u] of pages.entries()) {
    const id = `${String(i + 1).padStart(2, '0')}-${slug(u)}`;
    for (const res of resols) {
      const cs = combos.filter((c) => c.res.id === res);
      const base = cs.find((c) => c.browser === a.base) || cs[0];
      const mb = measures[`${id}|${base.id}`];
      const row = { page: id, url: u, resolution: res, base: base.id, results: {} };
      for (const c of cs) {
        const m = measures[`${id}|${c.id}`];
        const r = { state: 'OK', screenshot: m && m.screenshot, js_errors: m ? m.js_errors.length : 0, overflow: m ? m.overflow : null,
          time_ms: m && m.time_ms, status: m && m.status };
        row.results[c.id] = r;
        if (!m || m.error) { r.state = 'Error'; r.error = m ? m.error : 'no data'; continue; }
        // It is only compared against the browsers that loaded the page: if one did not load, what the
        // rest have does not become "exclusive".
        const others = cs.filter((x) => x.id !== c.id).map((x) => measures[`${id}|${x.id}`]).filter((x) => x && !x.error);
        if (!others.length) continue;
        const mobileFirefox = c.browser === 'firefox' && c.res.width < 768;
        const own = [];
        const h = (x) => {
          if (mobileFirefox && VISUAL.has(x.type)) {
            x.severity = 'Low';
            x.detail += ' Firefox does not emulate a phone (no isMobile): it may show parts of the desktop version. Confirm it in Firefox for Android before reporting it.';
          }
          own.push(x);
          findings.push({ page: id, url: u, resolution: res, browser: c.browser, combo: c.id, ...x });
        };

        // JavaScript and console errors: exclusive if no other engine had the same error
        // (same code location or same own words). If the others also had unpaired errors,
        // it may be the same one with another message: it weighs less.
        const checkErrors = (field, type, severity) => {
          const fromOthers = others.flatMap((o) => o[field] || []);
          const unpaired = (m[field] || []).filter((e) => !fromOthers.some((x) => sameError(e, x)));
          const othersUnpaired = fromOthers.filter((x) => !(m[field] || []).some((e) => sameError(e, x)));
          for (const err of unpaired.slice(0, 5)) {
            const doubtful = othersUnpaired.length > 0;
            h({ type, severity: doubtful ? 'Low' : severity, title: `${type} only in ${NAME[c.browser]}`,
              detail: err.message + (doubtful ? ' (The other browsers also had errors on this page with another text: it may be the same error worded by another engine.)' : ''),
              error_det: err, screenshot: m.screenshot });
          }
        };
        checkErrors('js_errors_det', 'JavaScript error', 'High');
        checkErrors('console_errors_det', 'Console error', 'Medium');

        // Resources: fails in this one and another browser loaded it fine → browser-related. If no other one
        // requested it, each engine chose another file (srcset, font format, preload): it weighs less.
        for (const rf of m.failed_resources.slice(0, 8)) {
          const k = resourceKey(rf.url);
          const failsOn = (o) => o.failed_resources.some((x) => resourceKey(x.url) === k);
          if (others.every(failsOn)) continue;
          const nobodyElseRequested = others.every((o) => o._requests && !o._requests.has(k));
          h({ type: 'Failed resource', severity: nobodyElseRequested ? 'Low' : 'Medium', title: `Does not load in ${NAME[c.browser]}: ${k.split('/').pop() || k}`,
            detail: `${rf.url} → ${rf.error}` + (nobodyElseRequested ? ' (The other browsers did not request this file: each engine chooses its own version of images, fonts or preloads.)' : ''),
            resource: k, screenshot: m.screenshot });
        }

        const othersOverflow = others.map((x) => x.overflow || 0);
        if (m.overflow > 4 && othersOverflow.some((d) => d <= 4)) {
          h({ type: 'Horizontal overflow', severity: 'Medium', title: `The page overflows ${m.overflow} px in width only in ${NAME[c.browser]}`,
            detail: 'Horizontal scroll appears in this browser and not in the others: an element renders wider.', screenshot: m.screenshot });
        }
        if (m.status && mb && !mb.error && mb.status && m.status !== mb.status) {
          const blocked = [403, 429, 503].includes(m.status);
          h({ type: 'Different response', severity: blocked ? 'Medium' : 'High', title: `Responds ${m.status} in ${NAME[c.browser]} and ${mb.status} in ${NAME[base.browser]}`,
            detail: blocked
              ? 'It may be a bot protection (Cloudflare, WAF) that blocks that automated browser, not people: confirm it by hand.'
              : 'The server responds differently depending on the browser (user agent detection).',
            status_nav: m.status, screenshot: m.screenshot });
        }
        if (c.id !== base.id && mb && !mb.error && m._file && mb._file) {
          const cmp = visual.comparePng(mb._file, m._file, { threshold: a.threshold });
          const dif = path.join(dirDiff, `${id}-${c.id}.png`);
          fs.writeFileSync(dif, cmp.diff);
          r.pct = cmp.pct;
          r.diff = rel(dif);
          const el = visual.compareElements(mb.elements, m.elements, { tolerance: a.tolerance });
          const navName = NAME[c.browser];
          const withCrop = (x, baseBox, navBox) => {
            const boxes = [baseBox, navBox].filter(Boolean);
            const v = visual.windowOf(boxes, 70);
            const pref = path.join(dirCrop, `${id}-${c.id}-${findings.length + 1}`);
            if (baseBox) { fs.writeFileSync(`${pref}-base.png`, visual.markedCrop(mb._file, v, baseBox)); x.base_screenshot = rel(`${pref}-base.png`); }
            if (navBox) { fs.writeFileSync(`${pref}-nav.png`, visual.markedCrop(m._file, v, navBox, [20, 168, 149])); x.nav_screenshot = rel(`${pref}-nav.png`); }
            return x;
          };
          for (const f of filterMissing(el.missing, m.elements).filter((x) => ['a', 'button', 'input', 'select', 'textarea', 'img', 'h1', 'h2', 'h3', 'form'].includes(x.tag)).slice(0, 8)) {
            h(withCrop({ type: 'Missing element', severity: ['a', 'button', 'input', 'select', 'textarea', 'form'].includes(f.tag) ? 'High' : 'Medium',
              title: `${textEl(f)} does not appear in ${navName}`, detail: `${f.desc} is in ${NAME[base.browser]} and is not visible in ${navName}.` }, box(f), null));
          }
          // Shifts: each engine measures text differently (fonts, line height, antialiasing), so
          // something shifting a few pixels is normal. It matters when it ends up off screen.
          const offScreen = (e) => e.x + e.w > c.res.width + 2 || e.x < -2;
          for (const b of el.blocks.filter((x) => Math.hypot(x.dx, x.dy) >= 12).slice(0, 3)) {
            h(withCrop({ type: 'Shifted block', severity: 'Low',
              title: `${b.elements} elements shifted ${b.dx ? `${b.dx} px in X ` : ''}${b.dy ? `${b.dy} px in Y` : ''} in ${navName}`,
              detail: `From ${textEl(b.from)}: something above renders at another size in ${navName}. It is usually each engine's text measurement; it matters if it covers or cuts something.` }, box(b.from),
            { ...box(b.from), x: b.from.x + b.dx, y: b.from.y + b.dy }));
          }
          for (const mv of el.moved.filter((x) => Math.hypot(x.dx, x.dy) >= 12).slice(0, 8)) {
            const goesOffScreen = offScreen(mv.actual) && !offScreen(mv);
            h(withCrop({ type: 'Shifted element', severity: goesOffScreen ? 'High' : lowerTo(mv.severity, 'Medium'),
              title: goesOffScreen
                ? `${textEl(mv)} ends up off screen in ${navName}`
                : `${textEl(mv)} shifts ${mv.dx >= 0 ? '+' : ''}${mv.dx} px in X and ${mv.dy >= 0 ? '+' : ''}${mv.dy} px in Y in ${navName}`,
              detail: `${mv.desc}: (${mv.x}, ${mv.y}) in ${NAME[base.browser]} and (${mv.actual.x}, ${mv.actual.y}) in ${navName}.`,
              delta: { dx: mv.dx, dy: mv.dy, dw: mv.dw, dh: mv.dh } }, box(mv), box(mv.actual)));
          }
          // Colors: engines convert and round differently; less than 8 per channel is not visible.
          for (const s of (el.styles || []).filter((x) => (x.prop === 'background' || x.prop === 'color') && colorDistance(x.from, x.to) > 8).slice(0, 4)) {
            const ex = s.elements[0];
            h(withCrop({ type: 'Different style', severity: 'Medium', title: `${s.elements.length === 1 ? textEl(ex) : `${s.elements.length} elements`}: ${s.name} ${s.from} → ${s.to} in ${navName}`,
              detail: `The ${s.name} is computed differently in ${navName} (an unsupported CSS property or one with another default value).`,
              style: { property: s.prop, from: s.from, to: s.to } }, box(ex), box(ex.actual)));
          }
          if (cmp.pct > 15 && !own.some((x) => ['Missing element', 'Shifted block', 'Shifted element'].includes(x.type))) {
            h({ type: 'Looks different', severity: 'Low', title: `${cmp.pct} % of the screen looks different in ${navName}`,
              detail: 'The rendering changes (fonts, antialiasing, images or styles) even though the elements are in place: it is normal between engines; look at the screenshots only if something looks broken.',
              screenshot: m.screenshot, base_screenshot: mb.screenshot, nav_screenshot: m.screenshot });
          }
        }
        if (own.some((x) => SEV_ORDER[x.severity] <= 1)) r.state = 'With issues';
        else if (own.length) r.state = 'Minor differences';
        r.findings = own.length;
      }
      rows.push(row);
    }
  }
  for (const k of Object.keys(measures)) { delete measures[k]._file; delete measures[k].elements; delete measures[k]._requests; }
  return { rows, findings };
}

// An element is "missing" only if in the other browser there is none with the same tag and the same
// text: keys are numbered by order of appearance and an element higher up shifts the numbering.
function filterMissing(missing, navElements) {
  const present = new Set(navElements.filter((e) => e.text).map((e) => `${e.tag}|${e.text}`));
  return missing.filter((f) => !(f.text && present.has(`${f.tag}|${f.text}`)));
}

// Does the runtime finding appear in this measurement?
function appears(hz, m) {
  if (!m || m.error) return false;
  if (hz.type === 'JavaScript error') return m.js_errors_det.some((x) => sameError(hz.error_det, x));
  if (hz.type === 'Console error') return m.console_errors_det.some((x) => sameError(hz.error_det, x));
  if (hz.type === 'Failed resource') return m.failed_resources.some((x) => resourceKey(x.url) === hz.resource);
  if (hz.type === 'Different response') return m.status === hz.status_nav;
  return true;
}

// The errors, resources and responses that showed up only in one browser are confirmed by reloading the
// page in all the browsers of that resolution: if it does not repeat, it was intermittent (network,
// timing); if it now also appears in another one, it was not browser-related.
async function confirmPages(a, combos, findings) {
  const toConfirm = findings.filter((hz) => RUNTIME.has(hz.type) && hz.severity !== 'Low');
  if (!toConfirm.length || !a.retries) return { confirmed: 0, intermittent: 0, discarded: [] };
  const screens = new Map(); // `${url}|${resolution}` → combos of that resolution
  for (const hz of toConfirm) screens.set(`${hz.url}|${hz.resolution}`, combos.filter((c) => c.res.id === hz.resolution));
  const fresh = {};
  const pw = require('playwright');
  for (const nav of [...new Set(combos.map((c) => c.browser))]) {
    const browser = await pw[nav].launch({ headless: !a.headed });
    try {
      for (const [key, cs] of screens) {
        const url = key.slice(0, key.lastIndexOf('|'));
        for (const c of cs.filter((x) => x.browser === nav)) {
          process.stdout.write(`Confirming [${c.id.padEnd(18)}] ${url} `);
          const m = await measureRun(browser, c, url);
          fresh[`${url}|${c.id}`] = m;
          console.log(m.error ? `→ error: ${m.error}` : '→ ok');
        }
      }
    } finally {
      await browser.close().catch(() => {});
    }
  }
  return applyConfirmation(toConfirm, combos, fresh, findings);
}

// Separate from confirmPages so it can be tested without a browser.
function applyConfirmation(toConfirm, combos, fresh, findings) {
  const discarded = [];
  let confirmed = 0;
  let intermittent = 0;
  for (const hz of toConfirm) {
    const other = fresh[`${hz.url}|${hz.combo}`];
    if (!other || other.error) continue; // without a second measurement, it stays as it was
    const others = combos.filter((c) => c.res.id === hz.resolution && c.id !== hz.combo).map((c) => fresh[`${hz.url}|${c.id}`]);
    if (!appears(hz, other)) {
      hz.confirmed = false;
      hz.severity = 'Low';
      hz.detail += ' It did not repeat when reloading the page: it was probably intermittent (network or timing), not the browser.';
      intermittent++;
    } else if (others.some((o) => appears(hz, o))) {
      discarded.push(hz);
    } else {
      hz.confirmed = true;
      hz.detail += ' Confirmed: it repeated when reloading and did not appear in the other browsers.';
      confirmed++;
    }
  }
  for (const d of discarded) findings.splice(findings.indexOf(d), 1);
  return { confirmed, intermittent, discarded: discarded.map((d) => ({ type: d.type, browser: d.browser, url: d.url, detail: d.detail,
    reason: 'When reloading it also appeared in another browser: it is not browser-related.' })) };
}

// The same error (or resource) on several pages and resolutions is a single finding with the list of
// screens where it appears: it is usually a single cause (a script or a style of the template).
const GROUPABLE = new Set(['JavaScript error', 'Console error', 'Failed resource', 'Different response']);
function group(findings) {
  const output = [];
  const groups = new Map();
  for (const h of findings) {
    if (!h.page) { output.push(h); continue; }
    const screen = { page: h.page, url: h.url, resolution: h.resolution, combo: h.combo, screenshot: h.screenshot };
    if (!GROUPABLE.has(h.type)) { output.push({ ...h, screens: [screen] }); continue; }
    const k = `${h.type}|${h.browser}|${h.detail}`;
    if (!groups.has(k)) { const g = { ...h, screens: [] }; groups.set(k, g); output.push(g); }
    groups.get(k).screens.push(screen);
  }
  for (const g of groups.values()) {
    const urls = new Set(g.screens.map((p) => p.url));
    if (g.screens.length > 1) g.title += ` · ${urls.size} page(s), ${g.screens.length} screen(s)`;
  }
  return output;
}

function generateReport(folder) {
  const py = process.platform === 'win32' ? 'python' : 'python3';
  const r = spawnSync(py, [path.join(ROOT, 'scripts', 'generate_cross_browser_report.py'),
    path.join(folder, 'cross-browser.json'), path.join(folder, 'cross-browser-report.html')], { encoding: 'utf8' });
  if (r.status !== 0) {
    const reason = (r.stderr || r.error || '').toString().trim().split(/\r?\n/).pop();
    console.log(`Could not generate the HTML report (${reason}). Generate it with: python scripts/generate_cross_browser_report.py ` +
      '<folder>/cross-browser.json <folder>/cross-browser-report.html');
    return false;
  }
  return true;
}

async function main() {
  const a = parseArgs(process.argv.slice(2));
  if (a.help) {
    console.log(fs.readFileSync(__filename, 'utf8').split('\n').filter((l) => l.startsWith('//')).map((l) => l.slice(3)).join('\n'));
    return;
  }
  const mode = a.mode || (hasFeatures() ? 'suite' : 'pages');
  if (mode === 'suite' && !hasFeatures()) throw new Error('There are no scenarios in tools/k0lmena/web/features: automate first (web-mapper) or use --mode pages.');
  if (a.story && !/^[A-Za-z]+-\d+$/.test(a.story)) throw new Error('--story must be an ID like US-001.');
  let start = null;
  let host = null;
  if (mode === 'pages') {
    const url = a.url || (a.pages && a.pages[0]) || process.env.APP_URL || process.env.BASEURL;
    if (!url) throw new Error('No URL: pass it with --url or set APP_URL in the root .env.');
    if (!/^https?:\/\//i.test(url)) throw new Error(`The URL must start with http:// or https:// (got "${url}").`);
    start = normalize(url);
    host = new URL(start).hostname;
  }
  if (mode === 'suite' && a.story && !a.tags) a.tags = `@${a.story}`;
  const name = a.story || (mode === 'pages' ? host : 'suite');
  const folder = a.output ? fromCwd(a.output) : path.join(ROOT, 'output', 'cross-browser', name);
  archive(folder, GENERATED, 'cross-browser.json'); // the previous run moves to history/ (last 5)
  for (const n of GENERATED) fs.rmSync(path.join(folder, n), { recursive: true, force: true });
  for (const d of ['screenshots', 'diffs', 'crops']) fs.mkdirSync(path.join(folder, d), { recursive: true });
  const rel = (p) => path.relative(folder, p).split(path.sep).join('/');
  const relRoot = (p) => path.relative(ROOT, p).split(path.sep).join('/');
  const t0 = Date.now();

  console.log(`Cross-browser · ${mode} mode · browsers: ${a.browsers.join(', ')}`);
  const browsers = [];
  for (const n of a.browsers) browsers.push(await testBrowser(n));
  for (const n of browsers) console.log(`  ${n.name.padEnd(9)} ${n.ok ? `OK (${n.version})` : `${n.error}${n.install ? ` → ${n.install}` : ''}`}`);
  const available = browsers.filter((n) => n.ok).map((n) => n.name);
  if (!available.length) throw new Error('No browser available. Install them with: cd tools/k0lmena && npx playwright install chromium firefox webkit');
  if (!available.includes(a.base)) a.base = available[0];
  const resolutions = parseResolutions(a.resolutions || (mode === 'suite' ? '1366x768' : '1366x768,390x844'));
  const combos = [];
  for (const res of resolutions) for (const n of available) combos.push({ id: `${n}-${res.id}`, browser: n, res });
  console.log(`Output: ${relRoot(folder)} (replaces the previous run)`);

  let data;
  if (mode === 'suite') {
    const runs = runSuite(a, combos, folder, rel);
    const repeated = confirmSuite(a, combos, runs, folder);
    const { rows, findings } = analyzeSuite(runs);
    const count = (c) => rows.filter((f) => f.class === c).length;
    data = { runs: runs.map((c) => ({ id: c.id, browser: c.browser, resolution: c.res, duration_s: c.duration_s, error: c.error,
      report: c.report, passed: c.scenarios.filter((e) => e.status === 'Passed').length,
      failed: c.scenarios.filter((e) => e.status === 'Failed').length, total: c.scenarios.length })),
    scenarios: rows, findings,
    summary: { scenarios: rows.length, pass_in_all: count('Passes in all'), differences: count('Browser difference'),
      fail_in_all: count('Fails in all'), flaky: count('Flaky'), incomplete: count('Incomplete result'),
      repetitions: repeated, confirmed: findings.filter((h) => h.confirmed).length } };
  } else {
    const pw = require('playwright');
    const b = await pw[a.base].launch();
    const ctx = await b.newContext();
    const pages = await discover(await ctx.newPage(), start, a);
    await b.close();
    console.log(`${pages.length} page(s) × ${combos.length} browser and resolution combination(s)`);
    const measures = await walkPages(a, combos, pages, folder, rel);
    const { rows, findings } = analyzePages(a, combos, pages, measures, folder, rel);
    const confirmation = await confirmPages(a, combos, findings);
    const withIssues = rows.filter((f) => Object.values(f.results).some((r) => r.state === 'With issues')).length;
    const pcts = rows.flatMap((f) => Object.values(f.results).map((r) => r.pct).filter((x) => x != null));
    data = { pages: rows, measurements: Object.values(measures), findings,
      summary: { pages: pages.length, screens: rows.length, comparisons: pcts.length,
        no_differences: rows.filter((f) => Object.values(f.results).every((r) => r.state === 'OK')).length,
        with_issues: withIssues, pct_max: pcts.length ? Math.max(...pcts) : 0, pct_avg: pcts.length ? Math.round(pcts.reduce((s, x) => s + x, 0) / pcts.length * 100) / 100 : 0,
        exclusive_js_errors: findings.filter((h) => h.type === 'JavaScript error' && h.severity !== 'Low').length,
        confirmed: confirmation.confirmed, intermittent: confirmation.intermittent, discarded_on_confirm: confirmation.discarded.length },
      discarded: confirmation.discarded };
  }
  for (const h of data.findings) { delete h.error_det; delete h.status_nav; }
  data.findings = group(data.findings);
  data.findings.sort((x, y) => SEV_ORDER[x.severity] - SEV_ORDER[y.severity] || (y.screens || []).length - (x.screens || []).length);
  data.findings.forEach((h, i) => { h.id = `X-${String(i + 1).padStart(2, '0')}`; });
  const byNav = {};
  for (const n of available) byNav[n] = data.findings.filter((h) => (h.browser ? h.browser === n : (h.failing || []).some((f) => f.startsWith(n)))).length;
  const result = {
    mode, url: start, host, story: a.story || null, tags: a.tags || null, date: new Date().toISOString(), stamp: stamp(),
    duration_s: Math.round((Date.now() - t0) / 1000), base: a.base, tool: `Playwright ${require('playwright/package.json').version}`,
    browsers: browsers.map((n) => ({ ...n, title: NAME[n.name] })), resolutions: resolutions.map((r) => r.id),
    config: { tolerance_px: a.tolerance, threshold: a.threshold, hide: a.hide },
    ...data,
  };
  result.summary.findings = data.findings.length;
  result.summary.by_browser = byNav;
  result.summary.by_severity = Object.fromEntries(['Critical', 'High', 'Medium', 'Low'].map((s) => [s, data.findings.filter((h) => h.severity === s).length]));
  result.summary.not_installed = browsers.filter((n) => !n.ok).map((n) => n.name);
  const out = path.join(folder, 'cross-browser.json');
  fs.writeFileSync(out, JSON.stringify(result, null, 2), 'utf8');
  const r = result.summary;
  if (mode === 'suite') console.log(`\nScenarios: ${r.scenarios} · pass in all: ${r.pass_in_all} · browser differences: ${r.differences} · flaky: ${r.flaky} · fail in all: ${r.fail_in_all}`);
  else console.log(`\nScreens: ${r.screens} · no differences: ${r.no_differences} · with issues: ${r.with_issues} · findings: ${r.findings} (confirmed on reload: ${r.confirmed}, intermittent: ${r.intermittent}, discarded: ${r.discarded_on_confirm})`);
  console.log(`Data: ${relRoot(out)}`);
  if (generateReport(folder)) console.log(`Report: ${relRoot(path.join(folder, 'cross-browser-report.html'))}`);
}

if (require.main === module) {
  main().catch((e) => { console.error(`Error: ${e.message}`); process.exit(1); });
}

module.exports = { parseArgs, readCucumber, analyzeSuite, analyzePages, applyConfirmation, filterMissing, stripAnsi, NAME, GENERATED,
  resourceKey, errorTokens, sourceOf, sameError, isConsoleNoise, isCanceled, isBrowserOwnResource, colorDistance, contextOptions };
