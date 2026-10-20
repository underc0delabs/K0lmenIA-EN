// Web performance audit with Lighthouse (web-performance-auditor agent).
//
// Usage (from the repo root):
//   npm run web-performance -- [--url https://my-app.com] [--story US-001] [--pages url1,url2]
//                          [--max-pages 5] [--depth 1] [--devices mobile,desktop]
//                          [--repetitions 1] [--headed]
//
// It visits the pages of the same site starting from the URL (by default APP_URL in the .env, or BASEURL),
// or only those in --pages, and on each one runs Lighthouse (texts in English) on mobile (Moto G
// with slow 4G, Google's standard) and on desktop:
//   - performance, best practices and SEO scores,
//   - lab Core Web Vitals: LCP, CLS and TBT (the lab equivalent of INP),
//     plus FCP and Speed Index, with Google's thresholds (good / needs improvement / poor),
//   - the improvement opportunities with the estimated savings and the resources that cause them,
//   - the LCP element, the weight by resource type and the third-party impact,
//   - the loading sequence (screenshots) and the final screenshot.
// With --repetitions N it runs each page N times and keeps the median (Lighthouse varies
// between runs: to compare versions, 3 is advisable).
//
// It leaves everything in output/web-performance/<US or host>/ (the previous run moves to history/, last 5):
// web-performance.json, web-performance-report.html, screenshots/ and lighthouse/ (the native report of each
// page, for the detail). When it finishes it generates the HTML report (scripts/generate_web_performance_report.py).
//
// These are LAB data (a simulated load), not real-user data (CrUX): they are useful to
// find and compare problems, not to claim how each person experiences it.
const fs = require('fs');
const path = require('path');
const { archive } = require('../history/history.js');
const { normalize, slug, stamp, DO_NOT_CRAWL, FILE } = require('../explorer/explore.js');

const ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const GENERATED = ['web-performance.json', 'analysis.json', 'web-performance-report.html', 'screenshots', 'lighthouse'];
// Google's thresholds (good up to, poor from). TBT is the lab substitute for INP.
const THRESHOLDS = {
  lcp: { name: 'LCP', title: 'Largest Contentful Paint', good: 2500, poor: 4000, unit: 'ms', vital: true },
  cls: { name: 'CLS', title: 'Cumulative Layout Shift', good: 0.1, poor: 0.25, unit: '', vital: true },
  tbt: { name: 'TBT', title: 'Total Blocking Time', good: 200, poor: 600, unit: 'ms', vital: true },
  fcp: { name: 'FCP', title: 'First Contentful Paint', good: 1800, poor: 3000, unit: 'ms' },
  si: { name: 'SI', title: 'Speed Index', good: 3400, poor: 5800, unit: 'ms' },
};
const AUDIT_METRIC = { lcp: 'largest-contentful-paint', cls: 'cumulative-layout-shift', tbt: 'total-blocking-time',
  fcp: 'first-contentful-paint', si: 'speed-index' };
const SEV_ORDER = { 'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3 };

function parseArgs(argv) {
  const a = { maxPages: 5, depth: 1, devices: ['mobile', 'desktop'], repetitions: 1, headed: false };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    const v = () => argv[++i];
    if (k === '--url') a.url = v();
    else if (k === '--story') a.story = v();
    else if (k === '--pages') a.pages = v().split(',').map((x) => x.trim()).filter(Boolean);
    else if (k === '--max-pages') a.maxPages = parseInt(v(), 10);
    else if (k === '--depth') a.depth = parseInt(v(), 10);
    else if (k === '--devices') a.devices = v().split(',').map((x) => x.trim().toLowerCase()).filter(Boolean);
    else if (k === '--repetitions') a.repetitions = parseInt(v(), 10);
    else if (k === '--output') a.output = v();
    else if (k === '--headed') a.headed = true;
    else if (k === '-h' || k === '--help') a.help = true;
    else throw new Error(`Unknown option: ${k}`);
  }
  if (a.devices.some((d) => !['mobile', 'desktop'].includes(d))) throw new Error('--devices accepts mobile and/or desktop.');
  if (!(a.repetitions >= 1 && a.repetitions <= 5)) throw new Error('--repetitions must be between 1 and 5.');
  if (!(a.maxPages >= 1 && a.maxPages <= 50)) throw new Error('--max-pages must be between 1 and 50.');
  return a;
}

/** good | needs-improvement | poor according to Google's thresholds. */
function rate(key, value) {
  const u = THRESHOLDS[key];
  if (!u || value == null) return null;
  return value <= u.good ? 'good' : value <= u.poor ? 'needs-improvement' : 'poor';
}

// The previous run is not deleted: it moves to history/<date>/ (the last 5 are kept) to compare it.
function cleanFolder(folder) {
  archive(folder, GENERATED, 'web-performance.json');
  for (const name of GENERATED) fs.rmSync(path.join(folder, name), { recursive: true, force: true });
}

const toText = (s) => String(s || '').replace(/\[([^\]]+)\]\([^)]+\)/g, '$1').replace(/`/g, '').trim();
const linksIn = (s) => [...String(s || '').matchAll(/\[([^\]]+)\]\((https?:[^)]+)\)/g)].map((m) => m[2]);

// Rows of an audit's details: depending on the type, they come in items, or in nested tables
// (the Lighthouse 13 "insights" bring a list of tables).
function rowsOf(d) {
  if (!d) return [];
  const items = Array.isArray(d.items) ? d.items : d.items && typeof d.items === 'object' ? Object.values(d.items) : [];
  return items.flatMap((it) => (it && (it.type === 'table' || it.type === 'opportunity') && Array.isArray(it.items) ? it.items : [it]))
    .filter((it) => it && typeof it === 'object');
}

// From the LHR (Lighthouse result) it keeps only what the report uses.
function summarize(lhr) {
  const audits = lhr.audits;
  const metrics = {};
  for (const [k, id] of Object.entries(AUDIT_METRIC)) {
    const au = audits[id];
    if (au && au.numericValue != null) metrics[k] = { value: au.numericValue, text: au.displayValue, status: rate(k, au.numericValue) };
  }
  const scores = {};
  for (const [id, c] of Object.entries(lhr.categories || {})) scores[id] = c.score == null ? null : Math.round(c.score * 100);

  // Opportunities: performance audits that fail and estimate a saving (time or bytes).
  const refs = (lhr.categories.performance && lhr.categories.performance.auditRefs) || [];
  const opportunities = [];
  for (const ref of refs) {
    const au = audits[ref.id];
    if (!au || au.score == null || au.score >= 0.9 || au.scoreDisplayMode === 'informative' || au.scoreDisplayMode === 'notApplicable') continue;
    const d = au.details || {};
    const ms = d.overallSavingsMs || (au.metricSavings && Math.max(au.metricSavings.LCP || 0, au.metricSavings.FCP || 0, au.metricSavings.TBT || 0)) || 0;
    const bytes = d.overallSavingsBytes || 0;
    const cls = (au.metricSavings && au.metricSavings.CLS) || 0;
    if (!ms && !bytes && !cls) continue;
    const items = rowsOf(d).slice(0, 6).map((it) => ({
      url: typeof it.url === 'string' ? it.url : (it.node && it.node.snippet) || it.label || it.source && it.source.url || '',
      savings_bytes: it.wastedBytes || null, savings_ms: it.wastedMs || null, size: it.totalBytes || it.transferSize || null,
    })).filter((it) => it.url);
    opportunities.push({ id: ref.id, title: au.title, description: toText(au.description), more_info: linksIn(au.description)[0] || null,
      savings_ms: Math.round(ms), savings_bytes: Math.round(bytes), savings_cls: cls ? Math.round(cls * 1000) / 1000 : 0,
      value: au.displayValue || '', metrics: Object.keys(au.metricSavings || {}).filter((m) => au.metricSavings[m] > 0), items });
  }
  opportunities.sort((x, y) => y.savings_ms - x.savings_ms || y.savings_bytes - x.savings_bytes);

  // LCP element (depending on the Lighthouse version, it comes in one audit or another).
  let lcp = null;
  for (const id of ['largest-contentful-paint-element', 'lcp-breakdown-insight', 'lcp-discovery-insight']) {
    const d = audits[id] && audits[id].details;
    const find = (x) => (x && typeof x === 'object' ? (x.type === 'node' ? x : Object.values(x).map(find).find(Boolean)) : null);
    const node = find(d);
    if (node) { lcp = { selector: node.selector || '', html: (node.snippet || '').slice(0, 300), label: node.nodeLabel || '' }; break; }
  }

  // Weight by resource type, from the list of requests.
  const resources = {};
  let size = 0;
  let requests = 0;
  for (const r of rowsOf(audits['network-requests'] && audits['network-requests'].details)) {
    const type = { Document: 'Document', Script: 'JavaScript', Stylesheet: 'CSS', Image: 'Images', Font: 'Fonts', Media: 'Video and audio',
      XHR: 'Data (fetch/XHR)', Fetch: 'Data (fetch/XHR)' }[r.resourceType] || 'Other';
    resources[type] = resources[type] || { bytes: 0, requests: 0 };
    resources[type].bytes += r.transferSize || 0;
    resources[type].requests += 1;
    size += r.transferSize || 0;
    requests += 1;
  }

  const thirdParties = rowsOf(audits['third-party-summary'] && audits['third-party-summary'].details)
    .map((t) => ({ entity: typeof t.entity === 'string' ? t.entity : (t.entity && t.entity.text) || '', bytes: t.transferSize || 0, blocking_ms: Math.round(t.blockingTime || 0) }))
    .filter((t) => t.entity).sort((x, y) => y.blocking_ms - x.blocking_ms || y.bytes - x.bytes).slice(0, 8);

  const frames = rowsOf(audits['screenshot-thumbnails'] && audits['screenshot-thumbnails'].details)
    .map((f) => ({ ms: Math.round(f.timing), data: f.data }));
  const final = audits['final-screenshot'] && audits['final-screenshot'].details && audits['final-screenshot'].details.data;

  return { scores, metrics, opportunities, lcp, resources, total_size: size, requests, third_parties: thirdParties, _frames: frames, _final: final,
    warnings: (lhr.runWarnings || []).map(toText) };
}

function saveImage(dataUri, file) {
  const m = /^data:image\/\w+;base64,(.+)$/.exec(dataUri || '');
  if (!m) return false;
  fs.writeFileSync(file, Buffer.from(m[1], 'base64'));
  return true;
}

function buildFindings(results) {
  const h = [];
  // Core Web Vitals and metrics outside the thresholds, per page and device.
  for (const r of results) {
    if (r.error) {
      h.push({ category: 'Error', severity: 'High', page: r.url, device: r.device, title: 'Lighthouse could not measure the page', detail: r.error });
      continue;
    }
    for (const [k, m] of Object.entries(r.metrics)) {
      if (m.status === 'good') continue;
      const u = THRESHOLDS[k];
      const poor = m.status === 'poor';
      h.push({ category: u.vital ? 'Core Web Vitals' : 'Metric', metric: k, severity: poor ? (u.vital ? 'High' : 'Medium') : (u.vital ? 'Medium' : 'Low'),
        page: r.url, device: r.device, title: `${u.name} ${poor ? 'poor' : 'needs improvement'}: ${m.text}`,
        detail: `${u.title}: good up to ${u.unit === 'ms' ? `${u.good / 1000} s` : u.good}, poor from ${u.unit === 'ms' ? `${u.poor / 1000} s` : u.poor}.` });
    }
  }
  // Opportunities: one per audit, adding up pages (the same problem usually comes from the template).
  const op = new Map();
  for (const r of results.filter((x) => !x.error)) {
    for (const o of r.opportunities) {
      if (!op.has(o.id)) op.set(o.id, { ...o, pages: [], devices: new Set(), savings_ms_max: 0, savings_bytes_max: 0 });
      const x = op.get(o.id);
      if (!x.pages.includes(r.url)) x.pages.push(r.url);
      x.devices.add(r.device);
      x.savings_ms_max = Math.max(x.savings_ms_max, o.savings_ms);
      x.savings_bytes_max = Math.max(x.savings_bytes_max, o.savings_bytes);
    }
  }
  const opportunities = [...op.values()].map((o) => ({ ...o, devices: [...o.devices] }))
    .sort((x, y) => y.savings_ms_max - x.savings_ms_max || y.savings_bytes_max - x.savings_bytes_max);
  for (const o of opportunities) {
    const sev = o.savings_ms_max >= 1500 ? 'High' : o.savings_ms_max >= 500 || o.savings_bytes_max >= 500 * 1024 ? 'Medium' : 'Low';
    h.push({ category: 'Opportunity', severity: sev, page: o.pages[0], pages: o.pages, device: o.devices.join(', '),
      title: o.title, detail: [o.savings_ms_max ? `estimated savings up to ${(o.savings_ms_max / 1000).toFixed(1)} s` : '',
        o.savings_bytes_max ? `${Math.round(o.savings_bytes_max / 1024)} KB` : ''].filter(Boolean).join(' · '), audit: o.id });
  }
  h.sort((a, b) => SEV_ORDER[a.severity] - SEV_ORDER[b.severity]);
  return { findings: h.map((x, i) => ({ id: `R-${String(i + 1).padStart(2, '0')}`, ...x })), opportunities };
}

const median = (xs) => { const s = [...xs].sort((a, b) => a - b); return s[Math.floor((s.length - 1) / 2)]; };

function generateReport(folder) {
  const py = process.platform === 'win32' ? 'python' : 'python3';
  const r = require('child_process').spawnSync(py, [path.join(ROOT, 'scripts', 'generate_web_performance_report.py'),
    path.join(folder, 'web-performance.json'), path.join(folder, 'web-performance-report.html')], { encoding: 'utf8' });
  if (r.status !== 0) {
    const reason = (r.stderr || r.error || '').toString().trim().split(/\r?\n/).pop();
    console.log(`Could not generate the HTML report (${reason}). Generate it with: python scripts/generate_web_performance_report.py ` +
      '<folder>/web-performance.json <folder>/web-performance-report.html');
    return false;
  }
  return true;
}

async function discoverPages(start, a, chromium) {
  if (a.pages) return a.pages.map(normalize);
  const host = new URL(start).hostname;
  const b = await chromium.launch();
  const page = await b.newPage();
  const list = [start];
  const queue = [{ url: start, level: 0 }];
  const seen = new Set([start]);
  while (queue.length && list.length < a.maxPages) {
    const { url, level } = queue.shift();
    if (level >= a.depth) continue;
    try {
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
      const hrefs = await page.evaluate(() => [...document.querySelectorAll('a[href]')].map((x) => x.href));
      for (const h of hrefs) {
        let u;
        try { u = new URL(h); } catch { continue; }
        if (!/^https?:$/.test(u.protocol) || u.hostname !== host || DO_NOT_CRAWL.test(u.pathname + u.search) || FILE.test(u.pathname)) continue;
        const n = normalize(u.href);
        if (seen.has(n)) continue;
        seen.add(n);
        queue.push({ url: n, level: level + 1 });
        if (list.length < a.maxPages) list.push(n);
      }
    } catch { /* a page that does not open is reported by Lighthouse */ }
  }
  await b.close();
  return list;
}

async function main() {
  const a = parseArgs(process.argv.slice(2));
  if (a.help) {
    console.log(fs.readFileSync(__filename, 'utf8').split('\n').filter((l) => l.startsWith('//')).map((l) => l.slice(3)).join('\n'));
    return;
  }
  const [major, minor] = process.versions.node.split('.').map(Number);
  if (major < 22 || (major === 22 && minor < 19)) {
    throw new Error(`Lighthouse needs Node 22.19 or later (you have ${process.versions.node}). Update Node (22 LTS) and run again.`);
  }
  const url = a.url || (a.pages && a.pages[0]) || process.env.APP_URL || process.env.BASEURL;
  if (!url) throw new Error('No URL: pass it with --url or set APP_URL in the root .env.');
  if (!/^https?:\/\//i.test(url)) throw new Error(`The URL must start with http:// or https:// (got "${url}").`);
  if (a.story && !/^[A-Za-z]+-\d+$/.test(a.story)) throw new Error('--story must be an ID like US-001.');
  const start = normalize(url);
  const host = new URL(start).hostname;

  const folder = a.output ? path.resolve(a.output) : path.join(ROOT, 'output', 'web-performance', a.story || host);
  cleanFolder(folder);
  const dirScreenshots = path.join(folder, 'screenshots');
  const dirLh = path.join(folder, 'lighthouse');
  for (const d of [dirScreenshots, dirLh]) fs.mkdirSync(d, { recursive: true });
  const rel = (p) => path.relative(folder, p).split(path.sep).join('/');

  const { chromium } = require('playwright');
  const { default: lighthouse, desktopConfig } = await import('lighthouse');
  const chromeLauncher = require('chrome-launcher');
  const pages = await discoverPages(start, a, chromium);
  console.log(`Web performance of ${pages.length} page(s) · ${a.devices.join(' and ')} · ${a.repetitions} repetition(s) per page`);
  console.log(`Output: ${path.relative(ROOT, folder).split(path.sep).join('/')} (replaces the previous run)`);
  const t0 = Date.now();

  // A dedicated Chrome for Lighthouse (Playwright's, so there is no need to install another one).
  const chrome = await chromeLauncher.launch({ chromePath: chromium.executablePath(),
    chromeFlags: [...(a.headed ? [] : ['--headless=new']), '--no-first-run', '--disable-extensions'] });
  const results = [];
  try {
    for (const [i, u] of pages.entries()) {
      for (const dev of a.devices) {
        const n = String(i + 1).padStart(2, '0');
        process.stdout.write(`[${i + 1}/${pages.length}] ${dev.padEnd(7)} ${u} `);
        const runs = [];
        let error = null;
        for (let k = 0; k < a.repetitions; k++) {
          try {
            const r = await lighthouse(u, { port: chrome.port, output: ['html'], logLevel: 'error', locale: 'en-US',
              onlyCategories: ['performance', 'best-practices', 'seo'] }, dev === 'desktop' ? desktopConfig : undefined);
            if (r && r.lhr && !r.lhr.runtimeError) runs.push(r);
            else error = (r && r.lhr && r.lhr.runtimeError && r.lhr.runtimeError.message) || 'Lighthouse returned no results';
          } catch (e) {
            error = String(e.message || e).split('\n')[0].slice(0, 200);
          }
        }
        if (!runs.length) {
          console.log(`→ error: ${error}`);
          results.push({ url: u, device: dev, error });
          continue;
        }
        // Median by performance score (with a single run, that one).
        const scores = runs.map((r) => r.lhr.categories.performance.score || 0);
        const chosen = runs.find((r) => (r.lhr.categories.performance.score || 0) === median(scores));
        let summary;
        try {
          summary = summarize(chosen.lhr);
        } catch (e) {
          const msg = `Could not read the Lighthouse result: ${String(e.message || e).split(/\r?\n/)[0]}`;
          console.log(`→ error: ${msg}`);
          results.push({ url: u, device: dev, error: msg });
          continue;
        }
        const res = { url: u, device: dev, title: '', ...summary, repetitions: runs.length,
          run_scores: scores.map((s) => Math.round(s * 100)) };
        const native = path.join(dirLh, `${n}-${slug(u)}-${dev}.html`);
        fs.writeFileSync(native, Array.isArray(chosen.report) ? chosen.report[0] : chosen.report);
        res.lighthouse = rel(native);
        const final = path.join(dirScreenshots, `${n}-${slug(u)}-${dev}.jpg`);
        if (saveImage(res._final, final)) res.screenshot = rel(final);
        res.sequence = [];
        for (const [j, f] of res._frames.entries()) {
          const file = path.join(dirScreenshots, `${n}-${slug(u)}-${dev}-t${String(j).padStart(2, '0')}.jpg`);
          if (saveImage(f.data, file)) res.sequence.push({ ms: f.ms, screenshot: rel(file) });
        }
        delete res._final;
        delete res._frames;
        results.push(res);
        const m = res.metrics;
        console.log(`→ ${res.scores.performance} · LCP ${m.lcp ? m.lcp.text : '—'} · CLS ${m.cls ? m.cls.text : '—'} · TBT ${m.tbt ? m.tbt.text : '—'}`);
      }
    }
  } finally {
    await chrome.kill();
  }

  const { findings, opportunities } = buildFindings(results);
  const ok = results.filter((r) => !r.error);
  const avg = (dev) => {
    const xs = ok.filter((r) => r.device === dev && r.scores.performance != null).map((r) => r.scores.performance);
    return xs.length ? Math.round(xs.reduce((s, x) => s + x, 0) / xs.length) : null;
  };
  // Pages with all three Core Web Vitals in green (null if that device was not measured).
  const vitalsOk = (dev) => (a.devices.includes(dev) ? ok.filter((r) => r.device === dev)
    .filter((r) => ['lcp', 'cls', 'tbt'].every((k) => !r.metrics[k] || r.metrics[k].status === 'good')).length : null);
  const result = {
    url: start, host, story: a.story || null, date: new Date().toISOString(), stamp: stamp(),
    duration_s: Math.round((Date.now() - t0) / 1000), tool: `Lighthouse ${require('lighthouse/package.json').version}`,
    config: { devices: a.devices, repetitions: a.repetitions, max_pages: a.maxPages, thresholds: THRESHOLDS },
    summary: {
      pages: pages.length, measurements: results.length, errors: results.length - ok.length,
      web_performance_mobile: avg('mobile'), web_performance_desktop: avg('desktop'),
      vitals_ok_mobile: vitalsOk('mobile'), vitals_ok_desktop: vitalsOk('desktop'),
      findings: findings.length, opportunities: opportunities.length,
    },
    findings, opportunities, results,
  };
  const output = path.join(folder, 'web-performance.json');
  fs.writeFileSync(output, JSON.stringify(result, null, 2), 'utf8');
  const r = result.summary;
  console.log(`\nAverage performance: mobile ${r.web_performance_mobile ?? '—'} · desktop ${r.web_performance_desktop ?? '—'}`);
  const vit = (x) => (x == null ? '—' : `${x}/${pages.length}`);
  console.log(`Core Web Vitals in green: mobile ${vit(r.vitals_ok_mobile)} · desktop ${vit(r.vitals_ok_desktop)}`);
  console.log(`Findings: ${r.findings} · distinct opportunities: ${r.opportunities}`);
  console.log(`Data: ${path.relative(ROOT, output).split(path.sep).join('/')}`);
  if (generateReport(folder)) console.log(`Report: ${path.relative(ROOT, path.join(folder, 'web-performance-report.html')).split(path.sep).join('/')}`);
}

if (require.main === module) {
  main().catch((e) => { console.error(`Error: ${e.message}`); process.exit(1); });
}

module.exports = { parseArgs, rate, buildFindings, cleanFolder, THRESHOLDS, GENERATED, summarize };
