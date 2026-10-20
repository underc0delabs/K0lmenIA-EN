// Tests for the k0lmenIA Node scripts (run: node --test tests/node).
// They only use native modules: there is no need to install k0lmena.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'k0lmenia-'));

test('read-env: same rules as dotenv and scripts/_env.py', () => {
  const dir = tmp();
  const file = path.join(dir, '.env');
  fs.writeFileSync(file, '﻿SIMPLE=value\nexport WITH_EXPORT=yes\nSPACES =  hello   \nCOMMENT=abc # no\nQUOTES="a # b"\n# OFF=x\n');
  process.env.K0LMENA_ENV_FILE = file;
  delete require.cache[require.resolve(path.join(ROOT, 'scripts/mcp/read-env.js'))];
  const { variable } = require(path.join(ROOT, 'scripts/mcp/read-env.js'));
  assert.equal(variable('SIMPLE'), 'value');
  assert.equal(variable('WITH_EXPORT'), 'yes');
  assert.equal(variable('SPACES'), 'hello');
  assert.equal(variable('COMMENT'), 'abc');
  assert.equal(variable('QUOTES'), 'a # b');
  assert.equal(variable('OFF'), '');
  delete process.env.K0LMENA_ENV_FILE;
});

test('launch: the MCP servers use pinned versions (never @latest)', () => {
  const { pinnedPackage, VERSIONS } = require(path.join(ROOT, 'scripts/mcp/launch.js'));
  for (const pkg of Object.keys(VERSIONS)) {
    assert.match(pinnedPackage(pkg), /@\d+\.\d+\.\d+$/);
  }
  process.env.PLAYWRIGHT_MCP_MCP_VERSION = '1.2.3';
  assert.equal(pinnedPackage('@playwright/mcp'), '@playwright/mcp@1.2.3');
  delete process.env.PLAYWRIGHT_MCP_MCP_VERSION;
  const mcp = fs.readFileSync(path.join(ROOT, '.mcp.json'), 'utf8');
  assert.doesNotMatch(mcp, /@latest/);
});

const { generateReport } = require(path.join(ROOT, 'tools/k0lmena/reports/performance/generate-report.js'));

test('performance report: JMeter (.jtl) with global and per-sample thresholds', () => {
  const dir = tmp();
  const jtl = path.join(dir, 'raw.jtl');
  const rows = ['timeStamp,elapsed,label,responseCode,responseMessage,threadName,dataType,success,failureMessage,bytes,sentBytes,grpThreads,allThreads,URL,Latency,IdleTime,Connect'];
  for (let i = 0; i < 20; i++) rows.push(`${1700000000000 + i * 1000},${100 + i},GET /a,200,OK,t1,text,true,,1,1,2,2,https://x/a,1,0,1`);
  rows.push(`${1700000021000},900,POST /b,500,Error,t1,text,false,"Test failed: code expected to equal\n200",1,1,2,2,https://x/b,1,0,1`);
  fs.writeFileSync(jtl, rows.join('\n'));
  const r = generateReport({ tool: 'jmeter', script: 's', profile: 'smoke', target: 'https://x', raw: jtl, log: '', output: path.join(dir, 'r'), exitCode: 0,
    thresholds: { error_pct: 10, p95: 200, by_sample: { 'POST /b': { p95: 500 } } } });
  assert.equal(r.kpis.requests, 21);
  assert.equal(r.verdict, 'fail');
  const byName = Object.fromEntries(r.thresholds.map((u) => [u.metric, u.ok]));
  assert.equal(byName['% errors'], true);
  assert.equal(byName['POST /b · p95'], false);
  assert.ok(fs.existsSync(path.join(dir, 'r.html')));
  // The multi-line error message ends up on a single line
  assert.ok(Object.keys(r.errors)[0].includes('equal 200'));
});

test('performance report: a truncated result is reported as an error, without crashing', () => {
  const dir = tmp();
  const raw = path.join(dir, 'raw.json');
  fs.writeFileSync(raw, '{"metrics": {"http_reqs": ');
  const r = generateReport({ tool: 'k6', script: 's', profile: 'smoke', target: '-', raw, log: '', output: path.join(dir, 'r'), exitCode: 0 });
  assert.equal(r.verdict, 'error');
});

test('dark theme of the cucumber reports: forces dark and is applied only once', () => {
  const { themeInHtml } = require(path.join(ROOT, 'tools/k0lmena/reports/dark-theme.js'));
  const original = '<!doctype html><html lang="en"><head><title>x</title></head><body></body></html>';
  const once = themeInHtml(original);
  assert.match(once, /<html lang="en" class="dark">/);
  assert.match(once, /id="k0lmena-theme"/);
  assert.equal(themeInHtml(once), once);
});

const explorer = require(path.join(ROOT, 'tools/k0lmena/tools/explorer/explore.js'));

test('explorer: normalizes URLs, validates resolutions and classifies links', () => {
  assert.equal(explorer.normalize('https://x.com/a/#section'), 'https://x.com/a');
  assert.equal(explorer.normalize('https://x.com/'), 'https://x.com/');
  assert.equal(explorer.slug('https://x.com/'), 'home');
  assert.equal(explorer.slug('https://x.com/Blog/Post?id=3'), 'blog-post-id-3');
  assert.deepEqual(explorer.parseResolutions('360x740, 1366x768').map((r) => r.name), ['Mobile', 'Desktop']);
  assert.throws(() => explorer.parseResolutions('large'), /Invalid resolution/);
  assert.equal(explorer.classifyLink({ status: 200 }), 'ok');
  assert.equal(explorer.classifyLink({ status: 404 }), 'broken');
  assert.equal(explorer.classifyLink({ status: 403 }), 'unverifiable');
  assert.equal(explorer.classifyLink({ status: 0, error: 'timeout' }), 'unverifiable');
  assert.equal(explorer.classifyLink({ status: 0, error: 'ENOTFOUND', down: true }), 'broken');
});

test('explorer: builds findings with severity and groups responsive issues by page', () => {
  const page = { url: 'https://x.com/', status: 200, meta_viewport: 'width=device-width', js_errors: ['boom'], console_errors: [],
    failed_resources: [{ url: 'https://x.com/a.js', status: 404, type: 'script' }], broken_images: [{ src: 'https://x.com/a.png' }], images_without_alt: 0 };
  const links = [{ url: 'https://x.com/no', internal: true, status: 404, result: 'broken', sources: ['https://x.com/'] }];
  const row = (res, width) => ({ url: 'https://x.com/', resolution: res, name: 'Mobile', width, horizontal_overflow: true, document_width: 500,
    window_width: width, overflowing_elements: [{ element: 'div.table', width: 500 }], small_text: 0, small_touch_targets: 0 });
  const h = explorer.buildFindings([page], links, [row('360x740', 360), row('390x844', 390)]);
  assert.deepEqual(h.map((x) => x.id), h.map((_, i) => `H-${String(i + 1).padStart(2, '0')}`));
  assert.ok(h.every((x, i) => i === 0 || ['Critical', 'High', 'Medium', 'Low'].indexOf(h[i - 1].severity) <= ['Critical', 'High', 'Medium', 'Low'].indexOf(x.severity)));
  const resp = h.filter((x) => x.category === 'Responsive');
  assert.equal(resp.length, 1);
  assert.deepEqual(resp[0].resolutions, ['360x740', '390x844']);
  assert.equal(resp[0].severity, 'High');
  for (const cat of ['JavaScript error', 'Failed resource', 'Broken image', 'Broken link']) assert.ok(h.some((x) => x.category === cat), cat);
});

test('explorer: each run deletes only what the previous one generated', () => {
  const dir = tmp();
  for (const f of ['exploration.json', 'analysis.json', 'exploratory-report.html', 'notes.txt']) fs.writeFileSync(path.join(dir, f), 'x');
  fs.mkdirSync(path.join(dir, 'screenshots', 'manual'), { recursive: true });
  fs.writeFileSync(path.join(dir, 'screenshots', 'manual', 'ex-01.png'), 'x');
  fs.mkdirSync(path.join(dir, 'videos'));
  explorer.cleanFolder(dir);
  assert.deepEqual(fs.readdirSync(dir), ['notes.txt']);
  explorer.cleanFolder(path.join(dir, 'does-not-exist')); // without a previous run it does not fail
});

test('explorer: a problem repeated on several pages is a single finding, with its evidence', () => {
  const pg = (url) => ({ url, status: 200, meta_viewport: 'x', js_errors: [], console_errors: [], broken_images: [], images_without_alt: 0,
    failed_resources: [{ url: 'https://x.com/styles.css', status: 404, type: 'stylesheet' }], screenshot: `screenshots/pages/${url.length}.jpg`, time_ms: 500 });
  const h = explorer.buildFindings([pg('https://x.com/'), pg('https://x.com/other')], [], []);
  assert.equal(h.length, 1);
  assert.deepEqual(h[0].pages, ['https://x.com/', 'https://x.com/other']);
  assert.ok(h[0].evidence.startsWith('screenshots/pages/'));
  const slow = explorer.buildFindings([{ ...pg('https://x.com/'), failed_resources: [], time_ms: 7000 }], [], [], { slowMs: 3000 });
  assert.equal(slow[0].category, 'Web performance');
  assert.equal(slow[0].severity, 'Medium');
  assert.deepEqual(explorer.timings([{ time_ms: 1000 }, { time_ms: 3000 }, { error: 'x' }]),
    { load_avg_ms: 2000, load_max_ms: 3000, load_p90_ms: 3000 });
});

const a11y = require(path.join(ROOT, 'tools/k0lmena/tools/accessibility/audit.js'));

test('accessibility: WCAG criteria, level and severity from the axe tags', () => {
  assert.deepEqual(a11y.criteria(['cat.color', 'wcag2aa', 'wcag143', 'wcag1410']), ['1.4.3', '1.4.10']);
  assert.equal(a11y.levelOf(['wcag2a', 'wcag111']), 'A');
  assert.equal(a11y.levelOf(['wcag21aa']), 'AA');
  assert.equal(a11y.levelOf(['best-practice']), null);
  assert.equal(a11y.severity('critical', ['wcag2a', 'wcag111']), 'Critical');
  assert.equal(a11y.severity('serious', ['best-practice']), 'Medium'); // best practice: goes down one level
  assert.equal(a11y.parseArgs(['--level', 'aaa']).level, 'AAA');
  assert.throws(() => a11y.parseArgs(['--level', 'B']), /A, AA or AAA/);
});

test('accessibility: groups by rule across pages and adds keyboard and reflow', () => {
  const v = { id: 'image-alt', impact: 'critical', title: 'Images without alt', tags: ['wcag2a', 'wcag111'], total_nodes: 2,
    nodes: [{ selector: 'img', html: '<img>' }, { selector: 'img.b', html: '<img>' }] };
  const pg = (url, extra = {}) => ({ url, violations: [v], review: [], passes: ['a', 'b', 'c'],
    keyboard: { steps: [{ element: 'a', text: 'Skip to content', visible_indicator: true }], trap: null }, ...extra });
  const { findings } = a11y.buildFindings([
    pg('https://x.com/'),
    pg('https://x.com/b', { keyboard: { steps: [{ element: 'a', text: 'Home', visible_indicator: false }], trap: { element: 'input', text: 'Editor' } },
      reflow: { overflows: true, document_width: 500 } }),
  ]);
  const alt = findings.find((h) => h.rule === 'image-alt');
  assert.deepEqual(alt.pages, ['https://x.com/', 'https://x.com/b']);
  assert.equal(alt.total_nodes, 4);
  assert.deepEqual(alt.wcag, ['1.1.1']);
  for (const r of ['focus-trap', 'focus-not-visible', 'reflow-320']) assert.ok(findings.some((h) => h.rule === r), r);
  assert.equal(findings[0].severity, 'Critical');
  assert.equal(a11y.compliance([{ passes: ['a', 'b', 'c'], violations: [v] }]), 75);
});

const perf = require(path.join(ROOT, 'tools/k0lmena/tools/web-performance/audit.js'));

test('web performance: rates with Google\'s thresholds and builds findings and opportunities', () => {
  assert.equal(perf.rate('lcp', 2400), 'good');
  assert.equal(perf.rate('lcp', 3000), 'needs-improvement');
  assert.equal(perf.rate('cls', 0.3), 'poor');
  assert.throws(() => perf.parseArgs(['--devices', 'tablet']), /mobile and\/or desktop/);
  const page = (url) => ({ url, device: 'mobile', metrics: { lcp: { value: 4500, text: '4.5 s', status: 'poor' }, cls: { value: 0, text: '0', status: 'good' } },
    opportunities: [{ id: 'unused-javascript', title: 'Unused JS', savings_ms: 1800, savings_bytes: 0 }] });
  const { findings, opportunities } = perf.buildFindings([page('https://x.com/'), page('https://x.com/b'), { url: 'https://x.com/c', device: 'mobile', error: 'boom' }]);
  assert.equal(opportunities.length, 1);
  assert.deepEqual(opportunities[0].pages, ['https://x.com/', 'https://x.com/b']);
  assert.ok(findings.some((h) => h.category === 'Core Web Vitals' && h.severity === 'High'));
  assert.ok(findings.some((h) => h.category === 'Opportunity' && h.severity === 'High'));
  assert.ok(findings.some((h) => h.category === 'Error'));
  assert.deepEqual(findings.map((h) => h.id), findings.map((_, i) => `R-${String(i + 1).padStart(2, '0')}`));
});
