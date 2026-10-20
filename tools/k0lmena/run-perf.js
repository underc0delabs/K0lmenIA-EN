// run-perf.js — runner for `npm run perf` (k6, Artillery and JMeter, on Windows, Linux, macOS and CI).
//
//   npm run perf                                   lists the available scripts
//   npm run perf -- <script> [profile] [options]
//
//   script   name without extension: performance/k6/http/<script>.ts, performance/artillery/<script>.yaml
//            or performance/jmeter/<script>.jmx (+ <script>.json with target, profiles and thresholds)
//   profile  smoke (default) | load | stress | soak | spike
//   --confirm        does not ask before a profile with load (for CI or for the agent,
//                      which already confirmed it with the person)
//   --vus N --duration 2m   (k6 and JMeter) override the script's load for this run
//
// Output in reports/performance/<tool>/: HTML report, JSON summary (small), raw
// result and log. The console only shows the summary; the tool's detail stays in the log.
require('./env');
const fs = require('fs');
const path = require('path');
const { spawn, spawnSync } = require('child_process');
const { generateReport } = require('./reports/performance/generate-report');

const ROOT = __dirname;
const PROFILES = ['smoke', 'load', 'stress', 'soak', 'spike'];
const DIR_K6 = path.join(ROOT, 'performance/k6/http');
const DIR_ART = path.join(ROOT, 'performance/artillery');
const DIR_JM = path.join(ROOT, 'performance/jmeter');
const rel = (p) => path.relative(ROOT, p).split(path.sep).join('/');

function exit(msg, code = 2) {
  console.error(msg);
  process.exit(code);
}

function list() {
  const k6 = fs.existsSync(DIR_K6) ? fs.readdirSync(DIR_K6).filter((f) => f.endsWith('.ts')).map((f) => f.slice(0, -3)) : [];
  const art = fs.existsSync(DIR_ART) ? fs.readdirSync(DIR_ART).filter((f) => /\.ya?ml$/.test(f)).map((f) => f.replace(/\.ya?ml$/, '')) : [];
  const jm = fs.existsSync(DIR_JM) ? fs.readdirSync(DIR_JM).filter((f) => f.endsWith('.jmx')).map((f) => f.slice(0, -4)) : [];
  console.log('Performance scripts:\n');
  if (!k6.length && !art.length && !jm.length) console.log('  (none yet: the performance-mapper agent generates them)');
  for (const s of k6) console.log(`  k6         ${s}`);
  for (const s of art) console.log(`  artillery  ${s}`);
  for (const s of jm) console.log(`  jmeter     ${s}`);
  console.log(`\nUsage: npm run perf -- <script> [${PROFILES.join('|')}] [--confirm]`);
}

// ------------------------------------------------------------ arguments
const args = process.argv.slice(2);
const flags = {};
const pos = [];
for (let i = 0; i < args.length; i++) {
  const a = args[i];
  if (a === '--confirm') flags.confirm = true;
  else if (a === '--vus' || a === '--duration') {
    const value = args[++i];
    if (!value || value.startsWith('--')) exit(`Missing the value of ${a} (e.g. --vus 20 --duration 2m).`);
    if (a === '--vus' && !/^[1-9]\d*$/.test(value)) exit(`--vus must be an integer greater than 0 (got "${value}").`);
    if (a === '--duration' && !/^\d+\s*[smh]?$/i.test(value)) exit(`--duration must be seconds or have an s, m or h suffix (e.g. 90, 2m, 1h); got "${value}".`);
    flags[a.slice(2)] = value;
  }
  else pos.push(a);
}
if (!pos.length) {
  list();
  process.exit(0);
}
const name = path.basename(pos[0]).replace(/\.(ts|js|ya?ml|jmx)$/, '');
const profile = (pos[1] || 'smoke').toLowerCase();
if (!PROFILES.includes(profile)) exit(`Unknown profile "${profile}". Options: ${PROFILES.join(', ')}.`);

// The same name in two tools is ambiguous: ask for a rename instead of silently picking one.
const matches = [
  fs.existsSync(path.join(DIR_K6, `${name}.ts`)) && 'k6',
  fs.existsSync(path.join(DIR_JM, `${name}.jmx`)) && 'jmeter',
  ['yaml', 'yml'].some((e) => fs.existsSync(path.join(DIR_ART, `${name}.${e}`))) && 'artillery',
].filter(Boolean);
if (matches.length > 1) {
  exit(`There are "${name}" scripts in ${matches.join(' and ')}: rename one (e.g. ${name}-${matches[1]}) so it is not ambiguous.`);
}

let tool, source;
if (fs.existsSync(path.join(DIR_K6, `${name}.ts`))) {
  tool = 'k6';
  source = path.join(DIR_K6, `${name}.ts`);
} else if (fs.existsSync(path.join(DIR_JM, `${name}.jmx`))) {
  tool = 'jmeter';
  source = path.join(DIR_JM, `${name}.jmx`);
} else {
  const yml = ['yaml', 'yml'].map((e) => path.join(DIR_ART, `${name}.${e}`)).find((f) => fs.existsSync(f));
  if (!yml) exit(`Could not find the script "${name}" in performance/k6/http/, performance/artillery/ or performance/jmeter/. Run "npm run perf" to see the list.`);
  tool = 'artillery';
  source = yml;
}

// JMeter: the load of each profile, the target and the thresholds go in <script>.json, next to the .jmx.
function configJMeter() {
  const file = path.join(DIR_JM, `${name}.json`);
  if (!fs.existsSync(file)) exit(`Missing ${rel(file)} (target, profiles and thresholds of the JMeter script).`);
  let cfg;
  try {
    cfg = JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (e) {
    exit(`${rel(file)} is not valid JSON: ${e.message}`);
  }
  if (!cfg.profiles || !cfg.profiles[profile]) exit(`${rel(file)} does not define the profile "${profile}" (profiles.${profile}).`);
  // target: the name of a .env variable (e.g. API_BASEURL) or a URL.
  const base = /^[A-Z][A-Z0-9_]*$/.test(cfg.target || '') ? process.env[cfg.target] : cfg.target;
  if (!base) exit(`${rel(file)}: the target "${cfg.target || ''}" is empty (if it is a variable, define it in the root .env).`);
  return { ...cfg, base: base.replace(/\/+$/, '') };
}
const cfgJM = tool === 'jmeter' ? configJMeter() : null;

// ------------------------------------------------------------ target (to show and confirm)
function getTarget() {
  if (tool === 'jmeter') return cfgJM.base;
  const text = fs.readFileSync(source, 'utf8');
  if (tool === 'artillery') {
    const yaml = require('js-yaml');
    const cfg = (yaml.load(text) || {}).config || {};
    const envs = cfg.environments || {};
    if (!envs[profile]) exit(`${rel(source)} does not define the profile "${profile}" (config.environments.${profile}).`);
    return (envs[profile] && envs[profile].target) || cfg.target || '—';
  }
  const targets = [];
  if (/env\.API_BASEURL/.test(text) && process.env.API_BASEURL) targets.push(process.env.API_BASEURL);
  if (/env\.BASEURL/.test(text) && process.env.BASEURL) targets.push(process.env.BASEURL);
  if (!targets.length) targets.push(...new Set(text.match(/https?:\/\/[^\s'"`/]+/g) || []));
  return targets.join(', ') || '—';
}
const target = getTarget();

function confirm() {
  if (profile === 'smoke' || flags.confirm) return Promise.resolve();
  const warning = `Profile "${profile}" against ${target}: it generates real load on that system.`;
  if (!process.stdin.isTTY || process.env.CI) {
    exit(`${warning}\nTo run it without an interactive terminal add --confirm (only with authorization from the system owners).`);
  }
  const rl = require('readline').createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((ok) =>
    rl.question(`${warning}\nDo you confirm? (y/N): `, (r) => {
      rl.close();
      if (!/^y(es)?$/i.test(r.trim())) exit('Cancelled.', 1);
      ok();
    })
  );
}

// ------------------------------------------------------------ run
function stamp() {
  const d = new Date(), p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

function k6Binary() {
  for (const f of ['tools/k6/k6.exe', 'tools/k6/k6']) if (fs.existsSync(path.join(ROOT, f))) return path.join(ROOT, f);
  const r = spawnSync(process.platform === 'win32' ? 'where' : 'which', ['k6'], { encoding: 'utf8' });
  if (r.status === 0 && r.stdout.trim()) return 'k6';
  exit('Could not find k6. Install it with "npm run bootstrap:k6" (it goes to tools/k6) or have it in the PATH.');
}

// JMeter runs with `java -jar ApacheJMeter.jar` (no .bat or shell: paths may contain spaces).
// The .jtl is written as CSV (JMeter's default format). Properties go in a file (-q) and not
// as -J: with several -J the Java 8 launcher on Windows crashes before starting.
function jarJMeter() {
  const candidates = [];
  if (process.env.JMETER_HOME) candidates.push(path.join(process.env.JMETER_HOME, 'bin/ApacheJMeter.jar'));
  const dirTools = path.join(ROOT, 'tools/jmeter');
  if (fs.existsSync(dirTools)) {
    for (const d of fs.readdirSync(dirTools).filter((x) => x.startsWith('apache-jmeter-')).sort().reverse()) {
      candidates.push(path.join(dirTools, d, 'bin/ApacheJMeter.jar'));
    }
  }
  const jar = candidates.find((f) => fs.existsSync(f));
  if (!jar) exit('Could not find JMeter. Install it with "npm run bootstrap:jmeter" (it goes to tools/jmeter) or define JMETER_HOME.');
  return jar;
}

function javaBinary() {
  const java = process.env.JAVA_HOME ? path.join(process.env.JAVA_HOME, 'bin', process.platform === 'win32' ? 'java.exe' : 'java') : 'java';
  const r = spawnSync(java, ['-version'], { encoding: 'utf8' });
  if (r.error || r.status !== 0) exit('JMeter needs Java 8 or later: install it and put it in the PATH, or define JAVA_HOME.');
  return java;
}

// "90", "90s", "5m", "2h" → seconds (for --duration in JMeter)
function seconds(text) {
  const m = String(text).trim().match(/^(\d+)\s*(s|m|h)?$/i);
  if (!m) exit(`Invalid duration "${text}": use seconds or an s, m or h suffix (e.g. 90, 2m, 1h).`);
  return Number(m[1]) * { s: 1, m: 60, h: 3600 }[(m[2] || 's').toLowerCase()];
}

function run(cmd, cmdArgs, env, logFile) {
  return new Promise((resolve) => {
    const log = fs.createWriteStream(logFile);
    const viewLive = process.stdout.isTTY && !process.env.CI;
    const child = spawn(cmd, cmdArgs, { cwd: ROOT, env, shell: process.platform === 'win32' && cmd === 'npx' });
    const write = (d) => {
      log.write(d);
      if (viewLive) process.stdout.write(d);
    };
    child.stdout.on('data', write);
    child.stderr.on('data', write);
    child.on('error', (e) => {
      log.write(String(e));
      log.end(() => resolve(1));
    });
    child.on('close', (code) => log.end(() => resolve(code ?? 1)));
  });
}

async function main() {
  await confirm();
  const ts = stamp();
  const dir = path.join(ROOT, 'reports/performance', tool);
  fs.mkdirSync(dir, { recursive: true });
  const base = path.join(dir, `${name}-${profile}-${ts}`);
  const raw = `${base}-raw.${tool === 'jmeter' ? 'jtl' : 'json'}`;
  const logFile = `${base}.log`;
  const env = { ...process.env, PROFILE: profile };

  console.log(`Performance: ${name} · ${tool} · profile ${profile} · target ${target}`);
  console.log(`Tool log: ${rel(logFile)}`);
  const start = Date.now();
  let code;

  if (tool === 'k6') {
    const k6 = k6Binary();
    const b = spawnSync(process.execPath, ['performance/k6/esbuild.k6.config.mjs', rel(source)], { cwd: ROOT, encoding: 'utf8' });
    if (b.status !== 0) exit(`${rel(source)} does not compile:\n${b.stderr || b.stdout}`);
    if (flags.vus) env.PERF_VUS = flags.vus;
    if (flags.duration) env.PERF_DURATION = flags.duration;
    env.K0LMENA_PERF_OUTPUT = raw;
    const dist = path.join(ROOT, 'performance/k6/dist/http', `${name}.js`);
    code = await run(k6, ['run', '--no-color', dist], env, logFile);
  } else if (tool === 'jmeter') {
    const java = javaBinary();
    const jar = jarJMeter();
    // Each profile key reaches the .jmx as a property: ${__P(users,1)}, ${__P(duration,30)}...
    const props = { ...cfgJM.profiles[profile], base_url: cfgJM.base };
    if (flags.vus) props.users = flags.vus;
    if (flags.duration) props.duration = seconds(flags.duration);
    const propsFile = `${base}.properties`;
    // .properties format: the backslash is an escape and each property goes on its own line.
    const escape = (v) => String(v).replace(/\\/g, '\\\\').replace(/\r?\n/g, ' ');
    fs.writeFileSync(propsFile, Object.entries(props).map(([k, v]) => `${k}=${escape(v)}`).join('\n') + '\n');
    const dashboard = `${base}-dashboard`;
    code = await run(java, [
      '-jar', jar, '-n', '-t', rel(source), '-l', rel(raw), '-j', rel(`${base}-jmeter.log`),
      '-q', rel(propsFile), '-e', '-o', rel(dashboard),
    ], env, logFile);
    if (fs.existsSync(path.join(dashboard, 'index.html'))) console.log(`JMeter dashboard: ${rel(path.join(dashboard, 'index.html'))}`);
  } else {
    if (flags.vus || flags.duration) console.log('Note: --vus and --duration are only for k6 and JMeter; in Artillery the load is in the .yaml phases.');
    const bin = path.join(ROOT, 'node_modules/artillery/bin/run');
    code = await run(process.execPath, [bin, 'run', rel(source), '--environment', profile, '--output', raw], { ...env, NO_COLOR: '1' }, logFile);
  }

  const r = generateReport({ tool, script: name, profile, target, raw, log: logFile, output: base, exitCode: code,
    thresholds: cfgJM && cfgJM.thresholds });

  // Short summary in the console (it is what the agent reads).
  const k = r.kpis, l = r.latency;
  const f = (x, u = '') => (x == null ? '—' : `${Math.round(x * 100) / 100}${u}`);
  console.log(`\nResult: ${r.verdict.toUpperCase()} (${Math.round((Date.now() - start) / 1000)} s)`);
  if (r.error) console.log(`  ${r.error}`);
  console.log(`  requests ${f(k.requests)} · req/s ${f(k.rps)} · errors ${f(k.error_pct, ' %')}`);
  console.log(`  latency (${l.source}): p50 ${f(l.p50, ' ms')} · p95 ${f(l.p95, ' ms')} · p99 ${f(l.p99, ' ms')} · max ${f(l.max, ' ms')}`);
  for (const u of r.thresholds) console.log(`  ${u.ok ? 'pass' : 'FAIL'}  ${u.metric}: ${u.condition} (measured ${u.value})`);
  const errors = Object.entries(r.errors);
  if (errors.length) console.log(`  errors: ${errors.slice(0, 5).map(([e, n]) => `${e} x${n}`).join(' · ')}`);
  console.log(`Report: ${rel(r.files.html)}`);
  console.log(`Summary: ${rel(r.files.summary)}`);
  process.exit(r.verdict === 'pass' || r.verdict === 'no thresholds' ? 0 : 1);
}

main().catch((e) => exit(e.stack || String(e), 1));
