// Synthetic monitoring: a light, READ-ONLY smoke test against an environment (production or another), meant
// to run on a schedule (GitHub Actions, cron or the Windows Task Scheduler).
//
// Usage (from the repo root):
//   npm run monitor -- [--urls https://my-app.com,https://my-app.com/login] [--config input/monitoring.json]
//                         [--name production] [--text "Sign in"] [--timeout-ms 15000] [--slow-ms 3000]
//                         [--tls-days 14] [--scenarios] [--notify-always] [--no-notify] [--runs 30]
//
// What each run checks:
//   - each URL (MONITORING_URLS in the .env, --urls or the "checks" in input/monitoring.json) with GET or HEAD:
//     expected status (2xx by default), response time (slow if it exceeds --slow-ms or the check's
//     max_ms), text that must be present and text that must not be present;
//   - the TLS certificate of each https host: it warns if it expires in less than --tls-days days;
//   - with --scenarios, the k0lmena web scenarios with the @synthetic tag (or the config's "tags").
//     THEY MUST BE READ-ONLY: navigate, search, look. Nothing that creates, changes or deletes data,
//     no logins with real users, no forms that get submitted: they run against production.
//
// Run state: Down (some check fails), Degraded (slow or a certificate about to expire) or OK.
// It compares with the previous run (what broke and what recovered) and ONLY notifies Slack and Teams
// (scripts/notify.py) when something changes, or always with --notify-always. MONITORING_LINK, if set, is used as
// the notification link (for example, the GitHub Actions run).
//
// It leaves output/monitoring/<name>/monitoring.json and monitoring-report.html; previous runs move to
// history/ (the last --runs are kept, 30 by default, for availability). It exits with 1 if
// the state is Down (useful in CI), 0 otherwise.
const fs = require('fs');
const path = require('path');
const tls = require('tls');
const { spawnSync } = require('child_process');
const { archive } = require('../history/history.js');

const ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const K0 = path.resolve(__dirname, '..', '..');
const fromCwd = (p) => path.resolve(process.env.INIT_CWD || process.cwd(), p);
const GENERATED = ['monitoring.json', 'monitoring-report.html', 'scenarios'];
const METHODS = new Set(['GET', 'HEAD']);

function parseArgs(argv) {
  const a = { timeoutMs: 15000, slowMs: 3000, tlsDays: 14, scenarios: false, notifyAlways: false, notify: true, runs: 30 };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    const v = () => argv[++i];
    if (k === '--urls') a.urls = v().split(',').map((x) => x.trim()).filter(Boolean);
    else if (k === '--config') a.config = v();
    else if (k === '--name') a.name = v();
    else if (k === '--text') a.text = v();
    else if (k === '--timeout-ms') a.timeoutMs = parseInt(v(), 10);
    else if (k === '--slow-ms') a.slowMs = parseInt(v(), 10);
    else if (k === '--tls-days') a.tlsDays = parseInt(v(), 10);
    else if (k === '--runs') a.runs = parseInt(v(), 10);
    else if (k === '--scenarios') a.scenarios = true;
    else if (k === '--notify-always') a.notifyAlways = true;
    else if (k === '--no-notify') a.notify = false;
    else if (k === '--output') a.output = v();
    else if (k === '-h' || k === '--help') a.help = true;
    else throw new Error(`Unknown option: ${k}`);
  }
  if (!(a.timeoutMs >= 1000)) throw new Error('--timeout-ms must be at least 1000.');
  if (!(a.runs >= 2 && a.runs <= 500)) throw new Error('--runs must be between 2 and 500.');
  if (a.name && !/^[\w.-]+$/.test(a.name)) throw new Error('--name only accepts letters, numbers, dot, hyphen and underscore.');
  return a;
}

// List of checks: config (input/monitoring.json) + --urls / MONITORING_URLS. Each one with a stable id.
function buildChecks(config, a, env = process.env) {
  const checks = [];
  for (const c of (config && config.checks) || []) checks.push({ ...c });
  const urls = a.urls || (checks.length ? [] : (env.MONITORING_URLS || '').split(',').map((x) => x.trim()).filter(Boolean));
  for (const url of urls) checks.push({ url });
  return checks.map((c, i) => {
    if (!c.url || !/^https?:\/\//i.test(c.url)) throw new Error(`Check ${i + 1} does not have a valid http(s) URL.`);
    const method = String(c.method || 'GET').toUpperCase();
    if (!METHODS.has(method)) throw new Error(`The check ${c.name || c.url} uses ${method}: monitoring is read-only (GET or HEAD).`);
    const u = new URL(c.url);
    return { id: c.id || `${method} ${u.host}${u.pathname}${u.search}`, name: c.name || (u.pathname === '/' ? u.host : u.pathname), url: c.url, method,
      status: c.status || null, text: c.text ?? a.text ?? null, no_text: c.no_text || null, max_ms: c.max_ms || a.slowMs };
  });
}

// Evaluates a check's response: { state: OK | Slow | Down, reason }.
function evaluate(check, r) {
  if (r.error) return { state: 'Down', reason: r.error };
  const expected = check.status ? [].concat(check.status).map(Number) : null;
  if (expected ? !expected.includes(r.status) : !(r.status >= 200 && r.status < 300)) {
    return { state: 'Down', reason: `HTTP ${r.status}${expected ? ` (expected ${expected.join(' or ')})` : ''}` };
  }
  if (check.text && check.method !== 'HEAD' && !(r.body || '').includes(check.text)) return { state: 'Down', reason: `The text "${check.text}" does not appear` };
  if (check.no_text && (r.body || '').includes(check.no_text)) return { state: 'Down', reason: `The text "${check.no_text}" appears` };
  if (r.ms > check.max_ms) return { state: 'Slow', reason: `${r.ms} ms (maximum ${check.max_ms} ms)` };
  return { state: 'OK', reason: '' };
}

function remainingDays(validUntil, now = new Date()) {
  const end = new Date(validUntil);
  return Number.isNaN(end.getTime()) ? null : Math.floor((end - now) / 86400000);
}

function overallState(results) {
  const states = results.map((r) => r.state);
  if (states.includes('Down')) return 'Down';
  if (states.some((e) => e === 'Slow' || e === 'Expiring')) return 'Degraded';
  return 'OK';
}

// What changed since the previous run: checks that broke, that recovered, and new ones.
function compare(previous, current) {
  const before = new Map(((previous && previous.results) || []).map((r) => [r.id, r.state]));
  const broke = [];
  const recovered = [];
  for (const r of current.results) {
    const prev = before.get(r.id);
    if (r.state === 'Down' && prev && prev !== 'Down') broke.push(r.id);
    else if (r.state === 'Down' && !prev && previous) broke.push(r.id);
    else if (r.state !== 'Down' && prev === 'Down') recovered.push(r.id);
  }
  return { previous: previous ? previous.state : null, broke, recovered, changed: !previous || previous.state !== current.state || broke.length > 0 || recovered.length > 0 };
}

// Title, text and level of the notification.
function buildNotification(data) {
  const { state, name, changes, results } = data;
  const level = state === 'Down' ? 'error' : state === 'Degraded' ? 'warning' : 'ok';
  const down = results.filter((r) => r.state === 'Down');
  let text;
  if (changes.recovered.length && !down.length) text = `Recovered: ${changes.recovered.join(', ')}.`;
  else if (down.length) text = `Failing: ${down.map((r) => `${r.name} (${r.reason})`).join('; ')}.`;
  else text = `Everything responds. ${results.filter((r) => r.state !== 'OK').map((r) => `${r.name}: ${r.reason}`).join('; ')}`.trim();
  if (changes.recovered.length && down.length) text += ` Recovered: ${changes.recovered.join(', ')}.`;
  return { title: `Monitoring ${name}: ${state}`, text, level,
    fields: [['Checks', `${results.filter((r) => r.state !== 'Down').length}/${results.length} OK`], ['Before', changes.previous || '—']] };
}

async function runCheck(check, timeoutMs) {
  const control = new AbortController();
  const clock = setTimeout(() => control.abort(), timeoutMs);
  const start = Date.now();
  try {
    const resp = await fetch(check.url, { method: check.method, redirect: 'follow', signal: control.signal,
      headers: { 'User-Agent': 'k0lmenIA-monitoring/1.0', 'Cache-Control': 'no-cache' } });
    const body = check.method === 'HEAD' ? '' : (await resp.text()).slice(0, 2_000_000);
    return { status: resp.status, ms: Date.now() - start, body, final_url: resp.url };
  } catch (e) {
    const cause = e.name === 'AbortError' ? `no response in ${timeoutMs} ms` : (e.cause && (e.cause.code || e.cause.message)) || e.message;
    return { error: String(cause), ms: Date.now() - start };
  } finally {
    clearTimeout(clock);
  }
}

function certificate(host, port = 443, timeoutMs = 10000) {
  return new Promise((ok) => {
    const s = tls.connect({ host, port, servername: host, timeout: timeoutMs }, () => {
      const c = s.getPeerCertificate();
      s.end();
      ok({ host, expires: c && c.valid_to ? new Date(c.valid_to).toISOString() : null, issuer: c && c.issuer ? c.issuer.O || c.issuer.CN : null });
    });
    s.on('error', (e) => ok({ host, error: e.code || e.message }));
    s.on('timeout', () => { s.destroy(); ok({ host, error: 'no response' }); });
  });
}

// k0lmena @synthetic scenarios (web suite), in their own reports folder so they do not overwrite npm test.
function runScenarios(tags, folder) {
  const dirRel = path.relative(K0, path.join(folder, 'scenarios')).split(path.sep).join('/');
  const env = { ...process.env, TAGS: tags, REPORT_DIR: dirRel, EVIDENCE: 'off', VIDEO: 'off', TRACE: 'off', PARALLEL: '' };
  const r = spawnSync('npx cucumber-js --profile web', { cwd: K0, env, shell: true, encoding: 'utf8' });
  const report = path.join(folder, 'scenarios', 'cucumber-report.json');
  if (!fs.existsSync(report)) return [{ id: `scenarios ${tags}`, name: `Scenarios ${tags}`, type: 'Scenario', state: 'Down', reason: `They could not be run (code ${r.status})` }];
  const output = [];
  for (const f of JSON.parse(fs.readFileSync(report, 'utf8'))) {
    for (const sc of f.elements || []) {
      if (sc.type === 'background') continue;
      const steps = sc.steps || [];
      const failed = steps.find((p) => (p.result || {}).status === 'failed');
      const ms = Math.round(steps.reduce((s, p) => s + ((p.result || {}).duration || 0), 0) / 1e6);
      output.push({ id: `scenario ${sc.name}`, name: sc.name, type: 'Scenario', url: f.uri, ms, state: failed ? 'Down' : 'OK',
        reason: failed ? String((failed.result || {}).error_message || 'failed').split('\n')[0].slice(0, 200) : '' });
    }
  }
  return output;
}

function notify(notification, link) {
  const py = process.platform === 'win32' ? 'python' : 'python3';
  const args = [path.join(ROOT, 'scripts', 'notify.py'), '--title', notification.title, '--text', notification.text, '--level', notification.level,
    '--fields', notification.fields.map(([k, v]) => `${k}=${String(v).replace(/,/g, ' ')}`).join(',')];
  if (link) args.push('--link', link);
  const r = spawnSync(py, args, { encoding: 'utf8' });
  process.stdout.write(r.stdout || '');
  if (r.status !== 0) console.log(`The notification could not be sent (${(r.stderr || r.error || '').toString().trim().split('\n').pop()}).`);
}

function generateReport(folder) {
  const py = process.platform === 'win32' ? 'python' : 'python3';
  const r = spawnSync(py, [path.join(ROOT, 'scripts', 'generate_monitoring_report.py'), path.join(folder, 'monitoring.json'),
    path.join(folder, 'monitoring-report.html')], { encoding: 'utf8' });
  if (r.status !== 0) console.log(`Could not generate the HTML report: ${(r.stderr || r.error || '').toString().trim().split('\n').pop()}`);
  return r.status === 0;
}

async function main() {
  const a = parseArgs(process.argv.slice(2));
  if (a.help) {
    console.log(fs.readFileSync(__filename, 'utf8').split('\n').filter((l) => l.startsWith('//')).map((l) => l.slice(3)).join('\n'));
    return 0;
  }
  const configPath = a.config ? fromCwd(a.config) : path.join(ROOT, 'input', 'monitoring.json');
  const config = fs.existsSync(configPath) ? JSON.parse(fs.readFileSync(configPath, 'utf8')) : null;
  if (a.config && !config) throw new Error(`${a.config} does not exist.`);
  const checks = buildChecks(config, a);
  const tags = (config && config.scenarios && config.scenarios.tags) || '@synthetic';
  const scenarios = a.scenarios || Boolean(config && config.scenarios && config.scenarios.run);
  if (!checks.length && !scenarios) throw new Error('There is nothing to monitor: set MONITORING_URLS in the .env, --urls or input/monitoring.json.');
  const name = a.name || (config && config.name) || (checks[0] ? new URL(checks[0].url).hostname : 'scenarios');
  const folder = a.output ? fromCwd(a.output) : path.join(ROOT, 'output', 'monitoring', name);
  fs.mkdirSync(folder, { recursive: true });
  const dataFile = path.join(folder, 'monitoring.json');
  const previous = fs.existsSync(dataFile) ? JSON.parse(fs.readFileSync(dataFile, 'utf8')) : null;
  archive(folder, GENERATED, 'monitoring.json', a.runs);
  for (const n of GENERATED) fs.rmSync(path.join(folder, n), { recursive: true, force: true });

  const start = new Date();
  console.log(`Monitoring "${name}" · ${checks.length} check(s)${scenarios ? ` + scenarios ${tags}` : ''}`);
  const results = [];
  for (const c of checks) {
    const r = await runCheck(c, a.timeoutMs);
    const ev = evaluate(c, r);
    results.push({ id: c.id, name: c.name, type: 'URL', url: c.url, method: c.method, status: r.status || null, ms: r.ms, ...ev });
    console.log(`  ${ev.state.padEnd(6)} ${c.method} ${c.url} · ${r.status || '-'} · ${r.ms} ms${ev.reason ? ` · ${ev.reason}` : ''}`);
  }
  const hosts = [...new Set(checks.filter((c) => c.url.startsWith('https://')).map((c) => new URL(c.url).host))];
  for (const h of hosts) {
    const [host, port] = h.split(':');
    const cert = await certificate(host, Number(port) || 443);
    const days = cert.expires ? remainingDays(cert.expires) : null;
    const state = cert.error ? 'Down' : days < 0 ? 'Down' : days < a.tlsDays ? 'Expiring' : 'OK';
    const reason = cert.error ? `TLS: ${cert.error}` : days < 0 ? 'Certificate expired' : days < a.tlsDays ? `Expires in ${days} day(s)` : '';
    results.push({ id: `TLS ${h}`, name: `Certificate for ${host}`, type: 'TLS', url: `https://${h}`, expires: cert.expires, remaining_days: days, issuer: cert.issuer, state, reason });
    console.log(`  ${state.padEnd(6)} TLS ${h}${days != null ? ` · expires in ${days} days` : ''}${reason && !days ? ` · ${reason}` : ''}`);
  }
  if (scenarios) {
    for (const r of runScenarios(tags, folder)) {
      results.push(r);
      console.log(`  ${r.state.padEnd(6)} Scenario ${r.name}${r.reason ? ` · ${r.reason}` : ''}`);
    }
  }

  const data = { name, date: start.toISOString(), stamp: start.toISOString().slice(0, 19), duration_ms: Date.now() - start.getTime(),
    state: overallState(results), results };
  data.changes = compare(previous, data);
  fs.writeFileSync(dataFile, JSON.stringify(data, null, 2));
  generateReport(folder);
  const rel = (p) => path.relative(ROOT, p).split(path.sep).join('/');
  console.log(`\nState: ${data.state}${data.changes.previous ? ` (before: ${data.changes.previous})` : ''}` +
    `${data.changes.broke.length ? ` · broke: ${data.changes.broke.join(', ')}` : ''}${data.changes.recovered.length ? ` · recovered: ${data.changes.recovered.join(', ')}` : ''}`);
  console.log(`Report: ${rel(path.join(folder, 'monitoring-report.html'))}`);
  // The first notification only if it starts with problems: an OK with no history is not news.
  const news = data.changes.changed && (previous || data.state !== 'OK');
  if (a.notify && (a.notifyAlways || news)) notify(buildNotification(data), process.env.MONITORING_LINK);
  return data.state === 'Down' ? 1 : 0;
}

if (require.main === module) {
  main().then((c) => process.exit(c)).catch((e) => { console.error(`Error: ${e.message}`); process.exit(2); });
}

module.exports = { parseArgs, buildChecks, evaluate, remainingDays, overallState, compare, buildNotification, GENERATED };
