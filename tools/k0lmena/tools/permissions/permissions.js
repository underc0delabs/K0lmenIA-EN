// Permissions matrix by role (permissions-tester agent).
//
// Usage (from the repo root):
//   npm run permissions -- [--url https://my-app.com] [--story US-001] [--pages url1,url2]
//                       [--max-pages 25] [--depth 2] [--roles admin,operator]
//                       [--endpoints "GET /api/users,GET /api/orders/1"] [--api-base https://api.my-app.com]
//                       [--map yes|no] [--screenshots 60] [--pause-ms 300] [--output <folder>] [--headed]
//
// For each role (always "anonymous", with no session, plus those in PERMISSIONS_ROLES in the .env) it logs in, crawls
// the site and records which paths it sees in its navigation. Then it visits ALL the paths found (those of all
// roles, those in --pages and, with --map yes, those in the project-documenter's functional map) with each
// role, as if typing the URL by hand, and records: HTTP status, whether it asks for login, whether it shows "access
// denied", where it redirects, title, visible menus and buttons. With --endpoints, it requests each endpoint with each
// role's session (cookies) and token and records the status.
//
// Roles in the root .env:
//   PERMISSIONS_ROLES=admin,operator,guest
//   PERMISSIONS_<ROLE>_USER / PERMISSIONS_<ROLE>_PASSWORD   (web login)
//   PERMISSIONS_<ROLE>_TOKEN                                (optional: Authorization: Bearer for --endpoints)
//   PERMISSIONS_LOGIN_URL                                   (optional: login page; by default the start URL)
//   PERMISSIONS_SELECTOR_USER / _PASSWORD / _SUBMIT         (optional: otherwise they are detected automatically)
// Without PERMISSIONS_ROLES and with APP_USER/APP_PASSWORD, it tests "anonymous" and "user".
//
// Read-only: it navigates with GET. The only submit allowed is the login form; any other
// navigation that is not GET is aborted. Endpoints only with GET, HEAD or OPTIONS. It does not follow
// logout or delete links. It never stores users, passwords or tokens in the JSON.
//
// It leaves everything in output/permissions/<US or host>/: permissions.json, permissions-report.html and screenshots/. The previous
// run moves to history/ (the last 5 are kept).
const fs = require('fs');
const path = require('path');
const { normalize, slug, stamp, load } = require('../explorer/explore.js');
const { discover } = require('../pixel-perfect/pixel-perfect.js');
const { archive } = require('../history/history.js');

const ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const fromCwd = (p) => path.resolve(process.env.INIT_CWD || process.cwd(), p);
const GENERATED = ['permissions.json', 'analysis.json', 'permissions-report.html', 'screenshots'];
const SEV_ORDER = { 'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3 };
const ANONYMOUS = 'anonymous';
const slugRole = (x) => x.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'role';
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);
// Texts that indicate the page denied access (even if it responds 200).
const DENIED = /(access denied|not authori[sz]ed|unauthori[sz]ed|forbidden|permission denied|you do(?:n't| not) have (?:permission|access)|insufficient permissions?|not allowed|acceso denegado|no autorizado|sin permiso|no ten[eé]s permiso|no tiene permiso|permiso insuficiente|prohibido)/i;
// Paths that are usually the login screen.
const LOGIN_PATH = /(log-?in|sign-?in|auth|ingres|iniciar-?sesion|acceso)/i;

function parseArgs(argv) {
  const a = { maxPages: 25, depth: 2, screenshots: 60, pauseMs: 300, map: true, headed: false };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    const v = () => argv[++i];
    if (k === '--url') a.url = v();
    else if (k === '--story') a.story = v();
    else if (k === '--pages') a.pages = v().split(',').map((x) => x.trim()).filter(Boolean);
    else if (k === '--max-pages') a.maxPages = parseInt(v(), 10);
    else if (k === '--depth') a.depth = parseInt(v(), 10);
    else if (k === '--roles') a.roles = v().split(',').map((x) => x.trim()).filter(Boolean);
    else if (k === '--endpoints') a.endpoints = v();
    else if (k === '--api-base') a.apiBase = v();
    else if (k === '--map') a.map = !/^(no|false|0)$/i.test(v());
    else if (k === '--screenshots') a.screenshots = parseInt(v(), 10);
    else if (k === '--pause-ms') a.pauseMs = parseInt(v(), 10);
    else if (k === '--output') a.output = v();
    else if (k === '--headed') a.headed = true;
    else if (k === '-h' || k === '--help') a.help = true;
    else throw new Error(`Unknown option: ${k}`);
  }
  if (a.story && !/^[A-Za-z]+-\d+$/.test(a.story)) throw new Error('--story must be an ID like US-001.');
  if (!(a.maxPages >= 1 && a.maxPages <= 200)) throw new Error('--max-pages must be between 1 and 200.');
  if (!(a.depth >= 0 && a.depth <= 5)) throw new Error('--depth must be between 0 and 5.');
  return a;
}

// Name of a role's environment variable: "area manager" → PERMISSIONS_AREA_MANAGER_USER.
function envKey(role, suffix) {
  const base = role.normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase().replace(/[^A-Z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  return `PERMISSIONS_${base}_${suffix}`;
}

// Roles to test from the environment. It never returns the passwords: only whether they are set.
function rolesFromEnv(env, filter) {
  let names = (env.PERMISSIONS_ROLES || '').split(',').map((x) => x.trim()).filter(Boolean);
  let useApp = false;
  if (!names.length && env.APP_USER && env.APP_PASSWORD) { names = ['user']; useApp = true; }
  const roles = [{ id: ANONYMOUS, name: 'Anonymous (no session)', authenticated: false, has_credentials: false, has_token: false }];
  for (const n of names) {
    if (n.toLowerCase() === ANONYMOUS) continue;
    const user = useApp ? env.APP_USER : env[envKey(n, 'USER')];
    const password = useApp ? env.APP_PASSWORD : env[envKey(n, 'PASSWORD')];
    roles.push({ id: n, name: n, authenticated: true, has_credentials: Boolean(user && password), has_token: Boolean(env[envKey(n, 'TOKEN')]),
      source: useApp ? 'APP_USER/APP_PASSWORD' : `${envKey(n, 'USER')}/${envKey(n, 'PASSWORD')}` });
  }
  if (filter && filter.length) return roles.filter((r) => r.id === ANONYMOUS || filter.includes(r.id));
  return roles;
}

function credentials(env, role) {
  if (role.source === 'APP_USER/APP_PASSWORD') return { user: env.APP_USER, password: env.APP_PASSWORD, token: env[envKey(role.id, 'TOKEN')] };
  return { user: env[envKey(role.id, 'USER')], password: env[envKey(role.id, 'PASSWORD')], token: env[envKey(role.id, 'TOKEN')] };
}

// "GET /api/x, /api/y" → [{method, path}]. No method = GET.
function parseEndpoints(text) {
  if (!text) return [];
  return text.split(',').map((x) => x.trim()).filter(Boolean).map((x) => {
    const m = x.match(/^([A-Za-z]+)\s+(\S+)$/);
    const method = (m ? m[1] : 'GET').toUpperCase();
    const route = m ? m[2] : x;
    if (!SAFE_METHODS.has(method)) throw new Error(`"${x}": only endpoints with GET, HEAD or OPTIONS are tested (no side effects).`);
    return { method, path: route };
  });
}

// How a visit turned out: allowed | requires-login | denied | not-found | error.
function classifyAccess({ status, requestedUrl, finalUrl, requiresPassword, text, loginUrl }) {
  if (!status) return 'error';
  if (status === 404 || status === 410) return 'not-found';
  if (status === 401 || status === 403) return 'denied';
  const route = (u) => { try { const x = new URL(u); return x.pathname + x.search; } catch { return u || ''; } };
  const isLogin = (u) => (loginUrl && normalize(u) === normalize(loginUrl)) || LOGIN_PATH.test(route(u));
  if (!isLogin(requestedUrl) && finalUrl && route(finalUrl) !== route(requestedUrl) && isLogin(finalUrl)) return 'requires-login';
  if (requiresPassword && !isLogin(requestedUrl)) return 'requires-login';
  if (DENIED.test(text || '')) return 'denied';
  if (status >= 500) return 'error';
  return 'allowed';
}

const REFUSED = new Set(['denied', 'requires-login']);

// Automatic findings: those with their own evidence in the matrix. The comparison against what is expected
// (which role SHOULD see what) is done by the agent in its analysis.
function buildFindings({ roles, paths, matrix, endpoints }) {
  const h = [];
  const add = (severity, type, title, detail, extra = {}) => h.push({ severity, type, title, detail, ...extra });
  const cell = (role, url) => matrix.find((m) => m.role === role && m.url === url);
  for (const r of roles) {
    if (r.authenticated && !r.has_credentials) add('High', 'Configuration', `The credentials for the role "${r.id}" are missing`, `Set ${r.source} in the root .env.`, { role: r.id });
    else if (r.authenticated && r.login_ok === false) add('High', 'Configuration', `Could not log in with the role "${r.id}"`, r.login_error || 'Check the credentials and the login selectors.', { role: r.id });
  }
  const active = roles.filter((r) => !r.authenticated || r.login_ok);
  for (const route of paths) {
    const deniedTo = active.filter((r) => r.authenticated && REFUSED.has((cell(r.id, route.url) || {}).access)).map((r) => r.id);
    const anon = cell(ANONYMOUS, route.url);
    const onlyWithSession = route.discovered_by.length && !route.discovered_by.includes(ANONYMOUS);
    if (anon && anon.access === 'allowed' && onlyWithSession) {
      if (deniedTo.length) {
        add('Critical', 'No login', 'Protected path accessible without logging in', `${route.path} denies access to ${deniedTo.join(', ')} but opens without a session.`, { url: route.url, role: ANONYMOUS });
      } else {
        add('High', 'No login', 'Path that only appears with a session opens without logging in', `${route.path} is only visible in the navigation of ${route.discovered_by.join(', ')}, but it opens without a session. Confirm whether it is public.`, { url: route.url, role: ANONYMOUS });
      }
    }
    for (const r of active) {
      const c = cell(r.id, route.url);
      if (!c) continue;
      if (route.discovered_by.includes(r.id) && REFUSED.has(c.access)) {
        add('Medium', 'Option without permission', `The role "${r.id}" sees a link that then denies it access`, `${route.path}: it appears in its navigation but responds ${c.access === 'denied' ? 'access denied' : 'with the login'}.`, { url: route.url, role: r.id });
      }
      if (r.authenticated && c.access === 'allowed' && !route.discovered_by.includes(r.id) && deniedTo.length && !deniedTo.includes(r.id)) {
        add('High', 'Direct URL', `The role "${r.id}" gets into a restricted path by direct URL`, `${route.path} is not in its navigation and is denied to ${deniedTo.join(', ')}, but it opens for "${r.id}". Confirm whether it should.`, { url: route.url, role: r.id });
      }
      if (c.access === 'error') add('Medium', 'Error', `${route.path} fails for the role "${r.id}"`, c.error || `It responds ${c.status}.`, { url: route.url, role: r.id });
    }
  }
  for (const ep of endpoints) {
    const st = (role) => (ep.results[role] || {}).status || 0;
    const rejecting = active.filter((r) => r.authenticated && [401, 403].includes(st(r.id))).map((r) => r.id);
    if (st(ANONYMOUS) >= 200 && st(ANONYMOUS) < 300 && rejecting.length) {
      add('Critical', 'API without authentication', `${ep.method} ${ep.path} responds without authentication`, `Without a session it responds ${st(ANONYMOUS)}, but it rejects ${rejecting.join(', ')}.`, { url: ep.url, role: ANONYMOUS });
    }
    for (const r of active) if (st(r.id) >= 500) add('Medium', 'Error', `${ep.method} ${ep.path} fails for the role "${r.id}"`, `It responds ${st(r.id)}.`, { url: ep.url, role: r.id });
  }
  h.sort((x, y) => SEV_ORDER[x.severity] - SEV_ORDER[y.severity]);
  h.forEach((x, i) => { x.id = `P-${String(i + 1).padStart(2, '0')}`; });
  return h;
}

function summarize({ roles, paths, matrix, endpoints, findings }) {
  const count = (acc) => matrix.filter((m) => m.access === acc).length;
  return { roles: roles.length, roles_with_session: roles.filter((r) => r.login_ok).length, paths: paths.length, visits: matrix.length,
    allowed: count('allowed'), denied: count('denied'), require_login: count('requires-login'), errors: count('error'), not_found: count('not-found'),
    endpoints: endpoints.length, findings: findings.length,
    by_severity: Object.fromEntries(['Critical', 'High', 'Medium', 'Low'].map((s) => [s, findings.filter((x) => x.severity === s).length])) };
}

// Runs in the browser: what the role sees on the page.
function _view() {
  const visible = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const text = (el) => (el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
  const unique = (xs) => [...new Set(xs.filter(Boolean))];
  const menus = unique([...document.querySelectorAll('nav a[href], [role=navigation] a[href], [role=menuitem], header a[href], aside a[href]')].filter(visible).map((x) => text(x).slice(0, 50))).slice(0, 60);
  const buttons = unique([...document.querySelectorAll('button, [role=button], input[type=submit], input[type=button]')].filter((b) => visible(b) && !b.closest('nav'))
    .map((b) => text(b).slice(0, 50))).slice(0, 40);
  const password = [...document.querySelectorAll('input[type=password]')].some(visible);
  return { title: document.title.trim(), menus, buttons, requires_password: password, text: (document.body ? document.body.innerText : '').slice(0, 3000) };
}

// Generic login: the visible password field, the user field before it and its form's button.
async function logIn(page, role, cred, cfg) {
  const loginUrl = cfg.loginUrl;
  cfg.allowSubmit(true);
  try {
    await load(page, loginUrl);
    const sel = (envVar, defaultValue) => process.env[envVar] || defaultValue;
    const password = page.locator(sel('PERMISSIONS_SELECTOR_PASSWORD', 'input[type=password]')).first();
    await password.waitFor({ state: 'visible', timeout: 10000 });
    let user = process.env.PERMISSIONS_SELECTOR_USER ? page.locator(process.env.PERMISSIONS_SELECTOR_USER).first() : null;
    if (!user) {
      const marked = await page.evaluate(() => {
        const visible = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
        const c = [...document.querySelectorAll('input[type=password]')].find(visible);
        const fields = [...(c.form || document).querySelectorAll('input:not([type=hidden]):not([type=password]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button])')].filter(visible);
        const before = fields.filter((x) => x.compareDocumentPosition(c) & Node.DOCUMENT_POSITION_FOLLOWING);
        const u = before[before.length - 1] || fields[0];
        if (!u) return false;
        u.setAttribute('data-k0-user', '1');
        return true;
      });
      if (!marked) throw new Error('could not find the user field (set PERMISSIONS_SELECTOR_USER)');
      user = page.locator('[data-k0-user="1"]').first();
    }
    await user.fill(cred.user);
    await password.fill(cred.password);
    const submit = process.env.PERMISSIONS_SELECTOR_SUBMIT
      ? page.locator(process.env.PERMISSIONS_SELECTOR_SUBMIT).first()
      : page.locator('form:has(input[type=password]) button[type=submit], form:has(input[type=password]) input[type=submit], form:has(input[type=password]) button:not([type])').first();
    if (await submit.count()) await submit.click({ timeout: 5000 });
    else await password.press('Enter');
    await page.waitForLoadState('load', { timeout: 15000 }).catch(() => {});
    await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {});
    const still = await page.locator('input[type=password]').first().isVisible().catch(() => false);
    if (still) {
      const err = await page.evaluate(() => [...document.querySelectorAll('[role=alert], .error, .alert, .invalid-feedback')].map((x) => x.innerText.trim()).filter(Boolean).join(' · ').slice(0, 200)).catch(() => '');
      throw new Error(`after submitting the login the login screen is still there${err ? ` (${err})` : ''}`);
    }
    return page.url();
  } finally {
    cfg.allowSubmit(false);
  }
}

function mapPaths() {
  const file = path.join(ROOT, 'input', 'documentation', 'project', 'functional-map.json');
  try { return (JSON.parse(fs.readFileSync(file, 'utf8')).pages || []).map((p) => p.url).filter(Boolean); } catch { return []; }
}

function generateReport(folder) {
  const py = process.platform === 'win32' ? 'python' : 'python3';
  const r = require('child_process').spawnSync(py, [path.join(ROOT, 'scripts', 'generate_permissions_report.py'), path.join(folder, 'permissions.json'),
    path.join(folder, 'permissions-report.html')], { encoding: 'utf8' });
  if (r.status !== 0) {
    const reason = (r.stderr || r.error || '').toString().trim().split(/\r?\n/).pop();
    console.log(`Could not generate the HTML report (${reason}). Generate it with: python scripts/generate_permissions_report.py <folder>/permissions.json <folder>/permissions-report.html`);
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
  const url = a.url || (a.pages && a.pages[0]) || process.env.APP_URL || process.env.BASEURL;
  if (!url) throw new Error('No URL: pass it with --url or set APP_URL in the root .env.');
  if (!/^https?:\/\//i.test(url)) throw new Error(`The URL must start with http:// or https:// (got "${url}").`);
  const endpoints = parseEndpoints(a.endpoints);
  const start = normalize(url);
  const host = new URL(start).hostname;
  const loginUrl = process.env.PERMISSIONS_LOGIN_URL || start;
  const roles = rolesFromEnv(process.env, a.roles);
  const folder = a.output ? fromCwd(a.output) : path.join(ROOT, 'output', 'permissions', a.story || host);
  archive(folder, GENERATED, 'permissions.json');
  for (const n of GENERATED) fs.rmSync(path.join(folder, n), { recursive: true, force: true });
  const shotsDir = path.join(folder, 'screenshots');
  fs.mkdirSync(shotsDir, { recursive: true });
  const rel = (p) => path.relative(folder, p).split(path.sep).join('/');
  const relRoot = (p) => path.relative(ROOT, p).split(path.sep).join('/');
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));

  const { chromium } = require('playwright');
  const browser = await chromium.launch({ headless: !a.headed });
  const t0 = Date.now();
  console.log(`Permissions of ${start} · roles: ${roles.map((r) => r.id).join(', ')} · output ${relRoot(folder)}`);

  // One context (session) per role, with submits blocked.
  const sessions = {};
  for (const r of roles) {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, locale: process.env.LOCALE || 'en-US' });
    const page = await ctx.newPage();
    let submitting = false;
    await page.route('**/*', (route) => {
      const rq = route.request();
      if (!submitting && rq.isNavigationRequest() && rq.method() !== 'GET') return route.abort();
      return route.continue();
    });
    sessions[r.id] = { ctx, page, allowSubmit: (x) => { submitting = x; } };
    if (r.authenticated) {
      if (!r.has_credentials) { r.login_ok = false; r.login_error = 'missing credentials'; continue; }
      try {
        r.url_after_login = await logIn(page, r, credentials(process.env, r), { loginUrl, allowSubmit: sessions[r.id].allowSubmit });
        r.login_ok = true;
      } catch (e) {
        r.login_ok = false;
        r.login_error = String(e.message || e).split('\n')[0].slice(0, 300);
      }
      console.log(`  login ${r.id}: ${r.login_ok ? 'ok' : `failed (${r.login_error})`}`);
    }
  }

  // 1) Which paths each role sees in its navigation.
  const pathsMap = new Map();
  const addRoute = (u, role) => {
    let n;
    try { n = normalize(u); } catch { return; }
    if (new URL(n).hostname !== host) return;
    if (!pathsMap.has(n)) pathsMap.set(n, { url: n, path: new URL(n).pathname + new URL(n).search, discovered_by: [] });
    if (role && !pathsMap.get(n).discovered_by.includes(role)) pathsMap.get(n).discovered_by.push(role);
  };
  for (const r of roles) {
    if (r.authenticated && !r.login_ok) continue;
    const roleStart = r.url_after_login && new URL(r.url_after_login).hostname === host ? normalize(r.url_after_login) : start;
    const urls = await discover(sessions[r.id].page, roleStart, { maxPages: a.maxPages, depth: a.depth }).catch(() => [roleStart]);
    for (const u of urls) addRoute(u, r.id);
    console.log(`  ${r.id}: ${urls.length} path(s) in its navigation`);
  }
  for (const u of a.pages || []) addRoute(u, null);
  if (a.map) for (const u of mapPaths()) addRoute(u, null);
  const paths = [...pathsMap.values()];

  // 2) Each role against all the paths (direct URL).
  const matrix = [];
  let shots = 0;
  for (const r of roles) {
    if (r.authenticated && !r.login_ok) continue;
    const { page } = sessions[r.id];
    for (const [i, route] of paths.entries()) {
      const c = { role: r.id, url: route.url };
      try {
        const { resp } = await load(page, route.url);
        c.status = resp ? resp.status() : 0;
        c.final_url = page.url();
        const v = await page.evaluate(_view);
        Object.assign(c, { title: v.title, menus: v.menus, buttons: v.buttons });
        c.access = classifyAccess({ status: c.status, requestedUrl: route.url, finalUrl: c.final_url, requiresPassword: v.requires_password, text: v.text, loginUrl });
        if (c.access === 'denied' && c.status < 400) c.reason = 'the page shows an access denied message';
      } catch (e) {
        c.status = 0;
        c.access = 'error';
        c.error = String(e.message || e).split('\n')[0].slice(0, 300);
      }
      if (shots < a.screenshots) {
        const file = path.join(shotsDir, `${slugRole(r.id)}-${String(i + 1).padStart(2, '0')}-${slug(route.url)}.png`);
        await page.screenshot({ path: file }).catch(() => {});
        if (fs.existsSync(file)) { c.screenshot = rel(file); shots++; }
      }
      matrix.push(c);
      process.stdout.write(`  [${r.id}] ${route.path} → ${c.access} (${c.status})\n`);
      if (a.pauseMs) await wait(a.pauseMs);
    }
  }

  // 3) API endpoints with each role's session and token.
  const base = a.apiBase || process.env.API_BASEURL || start;
  const eps = [];
  for (const ep of endpoints) {
    const urlEp = /^https?:\/\//i.test(ep.path) ? ep.path : new URL(ep.path, base).href;
    const row = { method: ep.method, path: ep.path, url: urlEp, results: {} };
    for (const r of roles) {
      if (r.authenticated && !r.login_ok && !r.has_token) continue;
      const token = r.authenticated ? credentials(process.env, r).token : null;
      try {
        const resp = await sessions[r.id].ctx.request.fetch(urlEp, { method: ep.method, headers: token ? { Authorization: `Bearer ${token}` } : {}, failOnStatusCode: false, maxRedirects: 0, timeout: 20000 });
        row.results[r.id] = { status: resp.status(), with_token: Boolean(token) };
      } catch (e) {
        row.results[r.id] = { status: 0, error: String(e.message || e).split('\n')[0].slice(0, 200) };
      }
    }
    eps.push(row);
    console.log(`  ${ep.method} ${ep.path}: ${Object.entries(row.results).map(([k, v]) => `${k}=${v.status}`).join(' ')}`);
  }
  await browser.close();

  const rolesOutput = roles.map(({ source, ...r }) => ({ ...r, variables: source || null }));
  const findings = buildFindings({ roles: rolesOutput, paths, matrix, endpoints: eps });
  const result = { url: start, host, story: a.story || null, date: new Date().toISOString(), stamp: stamp(), duration_s: Math.round((Date.now() - t0) / 1000),
    tool: `Playwright ${require('playwright/package.json').version}`, login_url: loginUrl, roles: rolesOutput, paths, matrix, endpoints: eps, findings };
  result.summary = summarize({ ...result, roles: rolesOutput });
  const output = path.join(folder, 'permissions.json');
  fs.writeFileSync(output, JSON.stringify(result, null, 2), 'utf8');
  const s = result.summary;
  console.log(`\nRoles: ${s.roles} · paths: ${s.paths} · visits: ${s.visits} (${s.allowed} allowed, ${s.denied + s.require_login} refused) · findings: ${s.findings}`);
  console.log(`Data: ${relRoot(output)}`);
  if (generateReport(folder)) console.log(`Report: ${relRoot(path.join(folder, 'permissions-report.html'))}`);
}

if (require.main === module) {
  main().catch((e) => { console.error(`Error: ${e.message}`); process.exit(1); });
}

module.exports = { parseArgs, envKey, rolesFromEnv, parseEndpoints, classifyAccess, buildFindings, summarize, GENERATED, ANONYMOUS };
