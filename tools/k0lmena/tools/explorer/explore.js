// Automatic exploration of a website with Playwright (web-explorer agent).
//
// Usage (from the repo root):
//   npm run explore -- [--url https://my-app.com] [--story US-001] [--max-pages 25]
//                       [--depth 3] [--resolutions 360x740,768x1024,1366x768]
//                       [--responsive 10] [--external yes|no] [--video yes|no] [--slow-ms 3000]
//                       [--pause-ms 300] [--headed]
//
// Crawls the pages of the same host starting at the URL (by default APP_URL from .env, or BASEURL)
// and on each one checks:
//   - broken links (internal and external) and broken images,
//   - JavaScript errors, console errors and failing resources (4xx/5xx, no response),
//   - responsive: horizontal overflow, elements that go off screen, small text,
//     small touch targets and meta viewport, at several resolutions,
//   - load metrics of each page (total time, first byte, DOM ready, requests and size).
//
// Evidence: full-page screenshot of each page (desktop) and of each page at each
// resolution, with the problem elements marked in red, and a video of the crawl and of
// each resolution. When done it generates the HTML report (scripts/generate_exploratory_report.py).
//
// Only navigates with GET: it does not fill in or submit forms and does not follow logout links.
// Leaves everything in output/exploratory/<US or host>/: exploration.json, exploratory-report.html, screenshots/
// and videos/. The previous run (with its analysis.json) moves to history/ (the last 5 are kept).
const fs = require('fs');
const path = require('path');
const { archive } = require('../history/history.js');

const ROOT = path.resolve(__dirname, '..', '..', '..', '..');

const DEFAULT_RESOLUTIONS = '360x740,390x844,768x1024,1366x768,1920x1080';
const RESOLUTION_NAME = (width) => (width < 600 ? 'Mobile' : width < 1024 ? 'Tablet' : 'Desktop');
// Links that are not crawled even if they belong to the site: they log out or have side effects on a GET.
// (Spanish words kept on purpose so Spanish-language sites stay safe too.)
const DO_NOT_CRAWL = /(log-?out|sign-?out|salir|cerrar-?sesion|desconectar|disconnect|delete|borrar|eliminar|unsubscribe)/i;
// Files that are checked (status) but not opened as a page.
const FILE = /\.(pdf|zip|rar|7z|gz|docx?|xlsx?|pptx?|csv|mp3|mp4|avi|mov|webm|jpe?g|png|gif|webp|avif|svg|ico|exe|dmg|apk)$/i;
// Statuses that do not prove the link is broken: they ask for login or block robots.
const UNVERIFIABLE = new Set([401, 403, 405, 429, 999]);

function parseArgs(argv) {
  const a = { maxPages: 25, depth: 3, responsive: 10, external: true, pauseMs: 300, headed: false,
    resolutions: DEFAULT_RESOLUTIONS, video: true, slowMs: 3000 };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    const v = () => argv[++i];
    if (k === '--url') a.url = v();
    else if (k === '--story') a.story = v();
    else if (k === '--max-pages') a.maxPages = parseInt(v(), 10);
    else if (k === '--depth') a.depth = parseInt(v(), 10);
    else if (k === '--resolutions') a.resolutions = v();
    else if (k === '--responsive') { const r = v(); a.responsive = r === 'all' ? Infinity : parseInt(r, 10); }
    else if (k === '--external') a.external = !/^(no|false|0)$/i.test(v());
    else if (k === '--pause-ms') a.pauseMs = parseInt(v(), 10);
    else if (k === '--video') a.video = !/^(no|false|0)$/i.test(v());
    else if (k === '--slow-ms') a.slowMs = parseInt(v(), 10);
    else if (k === '--output') a.output = v();
    else if (k === '--headed') a.headed = true;
    else if (k === '-h' || k === '--help') a.help = true;
    else throw new Error(`Unknown option: ${k}`);
  }
  return a;
}

function parseResolutions(text) {
  return text.split(',').map((r) => r.trim()).filter(Boolean).map((r) => {
    const m = r.match(/^(\d{3,4})x(\d{3,4})$/);
    if (!m) throw new Error(`Invalid resolution: ${r} (format WIDTHxHEIGHT, e.g. 390x844)`);
    const width = Number(m[1]);
    return { width, height: Number(m[2]), id: r, name: RESOLUTION_NAME(width) };
  });
}

// Normalizes so the same thing is not visited twice: no #fragment and no redundant trailing "/".
function normalize(url) {
  const u = new URL(url);
  u.hash = '';
  if (u.pathname.length > 1 && u.pathname.endsWith('/')) u.pathname = u.pathname.slice(0, -1);
  return u.href;
}

function slug(url) {
  const u = new URL(url);
  const s = (u.pathname + u.search).replace(/[^a-z0-9]+/gi, '-').replace(/^-+|-+$/g, '').toLowerCase();
  return (s || 'home').slice(0, 60);
}

const stamp = () => {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
};

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function inParallel(items, limit, fn) {
  let i = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (i < items.length) { const it = items[i++]; await fn(it); }
  });
  await Promise.all(workers);
}

// Scrolls down to the bottom little by little so lazy images load, and goes back to the top.
async function walkScroll(page) {
  await page.evaluate(async () => {
    const step = Math.max(200, window.innerHeight * 0.8);
    for (let y = 0; y < document.documentElement.scrollHeight && y < 30000; y += step) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 120));
    }
    window.scrollTo(0, 0);
  }).catch(() => {});
}

async function load(page, url) {
  const start = Date.now();
  const resp = await page.goto(url, { waitUntil: 'load', timeout: 30000 });
  await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {});
  return { resp, ms: Date.now() - start };
}

// What is checked inside the page at the desktop resolution.
function checkContent() {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none';
  };
  const images = [...document.images];
  const brokenEl = images.filter((img) => img.complete && img.naturalWidth === 0 && (img.currentSrc || img.getAttribute('src')));
  brokenEl.forEach((img) => img.setAttribute('data-k0-mark', ''));
  const broken = brokenEl.map((img) => ({ src: img.currentSrc || img.src, alt: img.getAttribute('alt') }));
  const noAlt = images.filter((img) => !img.hasAttribute('alt') && visible(img))
    .map((img) => img.currentSrc || img.src).filter(Boolean);
  const links = [...document.querySelectorAll('a[href]')].map((a) => ({
    href: a.href, text: (a.innerText || a.getAttribute('aria-label') || a.title || '').trim().slice(0, 80),
  }));
  const meta = document.querySelector('meta[name="viewport"]');
  return {
    title: document.title, broken, noAlt: noAlt.slice(0, 20), totalNoAlt: noAlt.length,
    totalImages: images.length, links, metaViewport: meta ? meta.getAttribute('content') : null,
  };
}

// What is checked at each resolution.
function checkResponsive(isMobile) {
  const vw = document.documentElement.clientWidth;
  const docWidth = Math.max(document.documentElement.scrollWidth, document.body ? document.body.scrollWidth : 0);
  const desc = (el) => {
    let s = el.tagName.toLowerCase();
    if (el.id) s += `#${el.id}`;
    const classes = (typeof el.className === 'string' ? el.className : '').trim().split(/\s+/).filter(Boolean).slice(0, 2);
    if (classes.length) s += `.${classes.join('.')}`;
    return s;
  };
  const visible = (el, r) => {
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' && cs.opacity !== '0';
  };
  const all = [...document.body.querySelectorAll('*')];
  const overflowSet = new Set();
  const overflowing = [];
  if (docWidth > vw + 1) {
    for (const el of all) {
      const r = el.getBoundingClientRect();
      if (r.right > vw + 1 && visible(el, r)) {
        overflowSet.add(el);
        // Only the outermost overflowing element (if the parent also overflows, the parent is reported).
        if (!overflowSet.has(el.parentElement) && overflowing.length < 8) {
          el.setAttribute('data-k0-mark', '');
          overflowing.push({ element: desc(el), width: Math.round(r.width), right: Math.round(r.right) });
        }
      }
    }
  }
  let smallText = 0;
  const textExamples = [];
  const touch = [];
  if (isMobile) {
    for (const el of all) {
      const hasText = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim().length > 1);
      if (!hasText) continue;
      const r = el.getBoundingClientRect();
      const px = parseFloat(getComputedStyle(el).fontSize);
      if (px < 12 && visible(el, r)) {
        smallText++;
        if (textExamples.length < 5) textExamples.push({ element: desc(el), px, text: el.textContent.trim().slice(0, 40) });
      }
    }
    // WCAG 2.5.8 (minimum size 24x24): links inside a text do not count, nor do small
    // targets with free space around them (the 24px square does not touch another target).
    const targets = [...document.querySelectorAll('a[href], button, input:not([type=hidden]), select, textarea, [role=button]')]
      .map((el) => ({ el, r: el.getBoundingClientRect() })).filter((o) => visible(o.el, o.r));
    const inText = (el) => getComputedStyle(el).display === 'inline' && el.parentElement &&
      [...el.parentElement.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim().length > 1);
    const touches = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
    for (const o of targets) {
      if ((o.r.width >= 24 && o.r.height >= 24) || inText(o.el)) continue;
      const cx = o.r.left + o.r.width / 2;
      const cy = o.r.top + o.r.height / 2;
      const zone = { left: cx - 12, right: cx + 12, top: cy - 12, bottom: cy + 12 };
      const neighbor = targets.some((x) => x !== o && !x.el.contains(o.el) && !o.el.contains(x.el) && touches(zone, x.r));
      if (neighbor && touch.length < 200) {
        if (touch.length < 20) o.el.setAttribute('data-k0-mark', '');
        touch.push({ element: desc(o.el), width: Math.round(o.r.width), height: Math.round(o.r.height),
          text: (o.el.innerText || o.el.getAttribute('aria-label') || o.el.value || '').trim().slice(0, 30) });
      }
    }
  }
  return {
    window_width: vw, document_width: docWidth, horizontal_overflow: docWidth > vw + 1,
    overflowing_elements: overflowing, small_text: smallText, small_text_examples: textExamples,
    small_touch_targets: touch.length, touch_examples: touch.slice(0, 5),
  };
}

// Navigation metrics (Navigation and Resource Timing). The size is approximate: resources
// from other domains without Timing-Allow-Origin report 0 bytes.
function measure() {
  const nav = performance.getEntriesByType('navigation')[0];
  const resources = performance.getEntriesByType('resource');
  const bytes = resources.reduce((s, r) => s + (r.transferSize || 0), nav ? nav.transferSize || 0 : 0);
  return {
    ttfb_ms: nav ? Math.round(nav.responseStart) : null,
    dom_ms: nav ? Math.round(nav.domContentLoadedEventEnd) : null,
    load_ms: nav ? Math.round(nav.loadEventEnd) : null,
    requests: resources.length + 1,
    size_kb: Math.round(bytes / 1024),
  };
}

// Full-page screenshot (JPG, lightweight) with the marked elements highlighted in red.
async function capture(page, file) {
  await page.addStyleTag({ content: '[data-k0-mark]{outline:3px solid #ff2d2d !important;outline-offset:-2px !important;' +
    'box-shadow:0 0 0 6px rgba(255,45,45,.35) !important}' }).catch(() => {});
  const options = { path: file, type: 'jpeg', quality: 70, timeout: 20000 };
  await page.screenshot({ ...options, fullPage: true }).catch(() => page.screenshot(options));
}

// Deletes ONLY what this script generates (and the old analysis), so the new run replaces
// the previous one without touching other files the person may have left in the folder.
const GENERATED = ['exploration.json', 'analysis.json', 'exploratory-report.html', 'screenshots', 'videos'];
// The previous run is not deleted: it moves to history/<date>/ (the last 5 are kept) to compare it.
function cleanFolder(folder) {
  archive(folder, GENERATED, 'exploration.json');
  for (const name of GENERATED) fs.rmSync(path.join(folder, name), { recursive: true, force: true });
}

function generateReport(folder) {
  const py = process.platform === 'win32' ? 'python' : 'python3';
  const r = require('child_process').spawnSync(py, [path.join(ROOT, 'scripts', 'generate_exploratory_report.py'),
    path.join(folder, 'exploration.json'), path.join(folder, 'exploratory-report.html')], { encoding: 'utf8' });
  if (r.status !== 0) {
    const reason = (r.stderr || r.error || '').toString().trim().split(/\r?\n/).pop();
    console.log(`Could not generate the HTML report (${reason}). ` +
      'Generate it with: python scripts/generate_exploratory_report.py <folder>/exploration.json <folder>/exploratory-report.html');
    return false;
  }
  return true;
}

// Native fetch (not Playwright's request, which with some servers throws socket errors
// that cannot be caught). The body is not downloaded: it is canceled as soon as the headers arrive.
async function request(url, method) {
  const r = await fetch(url, { method, redirect: 'follow', signal: AbortSignal.timeout(15000),
    headers: { 'User-Agent': 'Mozilla/5.0 (k0lmenIA web-explorer)', Accept: '*/*' } });
  if (r.body) await r.body.cancel().catch(() => {});
  return r.status;
}

async function verifyLink(url) {
  try {
    // Many servers do not implement HEAD properly: on an error or a 4xx/5xx it is confirmed with GET.
    const head = await request(url, 'HEAD').catch(() => 0);
    if (head && head < 400) return { status: head };
    return { status: await request(url, 'GET') };
  } catch (e) {
    const cause = e.cause ? ` ${e.cause.code || ''} ${e.cause.message || ''}` : '';
    const msg = `${e.name === 'TimeoutError' ? 'timeout' : e.message}${cause}`.trim();
    // It is only "broken" if the site does not exist or refuses the connection; the rest (timeouts, responses
    // the client cannot interpret) proves nothing.
    const down = /ENOTFOUND|EAI_AGAIN|ECONNREFUSED|NAME_NOT_RESOLVED|certificate|CERT_|SSL/i.test(msg);
    return { status: 0, error: /timeout/i.test(msg) ? 'No response (timeout)' : msg.slice(0, 160), down };
  }
}

function classifyLink(l) {
  if (l.status >= 200 && l.status < 400) return 'ok';
  if (UNVERIFIABLE.has(l.status) || (l.status === 0 && !l.down)) return 'unverifiable';
  return 'broken';
}

const SEV_ORDER = { Critical: 0, High: 1, Medium: 2, Low: 3 };

function buildFindings(pages, links, responsive, { slowMs = 3000 } = {}) {
  const h = [];
  const screenshotOf = new Map(pages.map((p) => [p.url, p.screenshot]));
  // If the finding does not bring its own evidence, the screenshot of the page where it was found is used.
  const add = (x) => h.push({ ...x, evidence: x.evidence || screenshotOf.get(x.page) });
  for (const p of pages) {
    if (!p.error && p.status < 400 && p.time_ms >= slowMs) {
      add({ category: 'Web performance', severity: p.time_ms >= slowMs * 2 ? 'Medium' : 'Low', page: p.url,
        title: `Slow load: ${(p.time_ms / 1000).toFixed(1)} s`,
        detail: `Took more than ${(slowMs / 1000).toFixed(1)} s to load` +
          (p.metrics && p.metrics.ttfb_ms != null ? ` (first byte ${p.metrics.ttfb_ms} ms, ${p.metrics.requests} requests, ~${p.metrics.size_kb} KB)` : '') });
    }
    if (p.error || p.status >= 400) {
      add({ category: 'Page error', severity: p.status >= 500 || p.error ? 'Critical' : 'High', page: p.url,
        title: p.error ? 'The page could not be opened' : `The page responds ${p.status}`, detail: p.error || `HTTP ${p.status}` });
    }
    for (const err of p.js_errors) {
      add({ category: 'JavaScript error', severity: 'High', page: p.url, title: 'Uncaught JavaScript error', detail: err });
    }
    for (const err of p.console_errors) {
      add({ category: 'Console error', severity: 'Medium', page: p.url, title: 'Error in the browser console', detail: err });
    }
    for (const r of p.failed_resources) {
      if (r.type === 'image') continue; // reported as a broken image
      const critical = ['script', 'stylesheet', 'document'].includes(r.type);
      add({ category: 'Failed resource', severity: critical ? 'High' : 'Medium', page: p.url,
        title: `${r.type || 'resource'} that does not load (${r.status || 'no response'})`, detail: r.url + (r.error ? ` · ${r.error}` : '') });
    }
    for (const img of p.broken_images) {
      add({ category: 'Broken image', severity: 'High', page: p.url, title: 'Image that does not load',
        detail: img.src + (img.status ? ` (HTTP ${img.status})` : '') + (img.alt ? ` · alt "${img.alt}"` : '') });
    }
    if (p.images_without_alt > 0) {
      add({ category: 'Accessibility', severity: 'Low', page: p.url, title: `${p.images_without_alt} image(s) without alternative text (alt)`,
        detail: (p.examples_without_alt || []).slice(0, 3).join(' · ') });
    }
    if (!p.error && p.status < 400 && !p.meta_viewport) {
      add({ category: 'Responsive', severity: 'Medium', page: p.url, title: 'No <meta name="viewport">',
        detail: 'On mobile the page is shown shrunk as if it were desktop.' });
    }
  }
  for (const l of links.filter((x) => x.result === 'broken')) {
    add({ category: 'Broken link', severity: l.internal ? 'High' : 'Medium', page: l.sources[0],
      title: `Broken ${l.internal ? 'internal link' : 'external link'} (${l.status || 'no response'})`,
      detail: l.url + (l.error ? ` · ${l.error}` : '') + (l.sources.length > 1 ? ` · appears on ${l.sources.length} pages` : ''),
      link_text: l.text });
  }
  // Responsive: one finding per page and problem type, with all the affected resolutions.
  const groups = new Map();
  const addTo = (r, type) => {
    const k = `${r.url}|${type}`;
    if (!groups.has(k)) groups.set(k, { type, url: r.url, rows: [] });
    groups.get(k).rows.push(r);
  };
  for (const r of responsive) {
    if (r.error) continue;
    if (r.horizontal_overflow) addTo(r, 'overflow');
    if (r.small_text > 0) addTo(r, 'text');
    if (r.small_touch_targets > 0) addTo(r, 'touch');
  }
  for (const { type, url, rows } of groups.values()) {
    const res = rows.map((r) => r.resolution);
    const evidence = (rows.find((r) => r.screenshot) || {}).screenshot;
    const r0 = rows[0];
    if (type === 'overflow') {
      const worst = r0.overflowing_elements[0];
      add({ category: 'Responsive', severity: rows.some((r) => r.width < 768) ? 'High' : 'Medium', page: url, resolutions: res,
        title: `Horizontal scroll at ${res.join(', ')}`,
        detail: `At ${r0.resolution} the content is ${r0.document_width}px wide on a ${r0.window_width}px screen` +
          (worst ? `; ${worst.element} overflows (${worst.width}px)` : ''), evidence });
    } else if (type === 'text') {
      add({ category: 'Responsive', severity: 'Low', page: url, resolutions: res,
        title: `${r0.small_text} text(s) smaller than 12px at ${res.join(', ')}`,
        detail: r0.small_text_examples.map((x) => `${x.element} ${x.px}px "${x.text}"`).join(' · '), evidence });
    } else {
      add({ category: 'Responsive', severity: 'Low', page: url, resolutions: res,
        title: `${r0.small_touch_targets} touch element(s) smaller than 24px and too close together at ${res.join(', ')}`,
        detail: r0.touch_examples.map((x) => `${x.element} ${x.width}x${x.height}${x.text ? ` "${x.text}"` : ''}`).join(' · '), evidence });
    }
  }
  // The same problem on several pages (typical of the template: a missing CSS, the menu) is a
  // single finding with the list of pages where it appears.
  const unique = new Map();
  for (const x of h) {
    const k = [x.category, x.title, x.detail, (x.resolutions || []).join()].join('|');
    if (!unique.has(k)) unique.set(k, { ...x, pages: [x.page] });
    else if (!unique.get(k).pages.includes(x.page)) unique.get(k).pages.push(x.page);
  }
  const list = [...unique.values()];
  list.sort((a, b) => SEV_ORDER[a.severity] - SEV_ORDER[b.severity] || b.pages.length - a.pages.length);
  return list.map((x, i) => ({ id: `H-${String(i + 1).padStart(2, '0')}`, ...x }));
}

async function main() {
  const a = parseArgs(process.argv.slice(2));
  if (a.help) {
    console.log(fs.readFileSync(__filename, 'utf8').split('\n').filter((l) => l.startsWith('//')).map((l) => l.slice(3)).join('\n'));
    return;
  }
  const url = a.url || process.env.APP_URL || process.env.BASEURL;
  if (!url) throw new Error('No URL: pass it with --url or set APP_URL in the root .env.');
  if (!/^https?:\/\//i.test(url)) throw new Error(`The URL must start with http:// or https:// (got "${url}").`);
  if (a.story && !/^[A-Za-z]+-\d+$/.test(a.story)) throw new Error('--story must be an ID like US-001.');
  if (!(a.maxPages >= 1 && a.maxPages <= 500)) throw new Error('--max-pages must be between 1 and 500.');
  const resolutions = parseResolutions(a.resolutions);
  const startUrl = normalize(url);
  const host = new URL(startUrl).hostname;
  const runStamp = stamp();
  // Fixed folder per story or site: the previous run moves to history/.
  const folder = a.output ? path.resolve(a.output) : path.join(ROOT, 'output', 'exploratory', a.story || host);
  cleanFolder(folder);
  const dirScreenshots = path.join(folder, 'screenshots');
  const dirPages = path.join(dirScreenshots, 'pages');
  const dirResponsive = path.join(dirScreenshots, 'responsive');
  const dirVideos = path.join(folder, 'videos');
  for (const d of [dirPages, dirResponsive, dirVideos]) fs.mkdirSync(d, { recursive: true });
  const rel = (p) => path.relative(folder, p).split(path.sep).join('/');
  const videos = [];

  console.log(`Exploring ${startUrl} · up to ${a.maxPages} pages · resolutions ${resolutions.map((r) => r.id).join(', ')}`);
  console.log(`Output: ${path.relative(ROOT, folder).split(path.sep).join('/')} (replaces the previous run)`);
  const t0 = Date.now();
  const { chromium } = require('playwright'); // here and not at the top: the tests use the functions without installing k0lmena
  const browser = await chromium.launch({ headless: !a.headed });
  // Context with video: when it is closed, the video is saved with a readable name.
  const newContext = (options) => browser.newContext({ ignoreHTTPSErrors: false, locale: process.env.LOCALE || 'en-US', ...options,
    ...(a.video ? { recordVideo: { dir: path.join(dirVideos, 'tmp'), size: options.viewport } } : {}) });
  const closeContext = async (ctx, pageObj, name, title) => {
    const video = a.video ? pageObj.video() : null;
    await ctx.close();
    if (!video) return;
    const dest = path.join(dirVideos, `${name}.webm`);
    await video.saveAs(dest).catch(() => {});
    await video.delete().catch(() => {});
    if (fs.existsSync(dest)) videos.push({ title, file: rel(dest) });
  };
  const context = await newContext({ viewport: { width: 1280, height: 720 } });
  const page = await context.newPage();

  // Events of the current page (reset on each visit).
  let current = null;
  // "Failed to load resource" is the console echo of a failing resource: it is already reported as a resource.
  page.on('console', (m) => {
    if (current && m.type() === 'error' && !/^Failed to load resource/.test(m.text())) current.console_errors.add(m.text().slice(0, 300));
  });
  page.on('pageerror', (e) => { if (current) current.js_errors.add(String(e.message || e).split('\n')[0].slice(0, 300)); });
  page.on('response', (r) => {
    if (current && r.status() >= 400) current.resources.set(r.url(), { url: r.url(), status: r.status(), type: r.request().resourceType() });
  });
  page.on('requestfailed', (rq) => {
    const reason = rq.failure() ? rq.failure().errorText : 'failed';
    if (current && !/ERR_ABORTED/.test(reason)) current.resources.set(rq.url(), { url: rq.url(), status: 0, type: rq.resourceType(), error: reason });
  });

  const visited = new Set();
  const queue = [{ url: startUrl, level: 0 }];
  const inQueue = new Set([startUrl]);
  const pages = [];
  const linksMap = new Map(); // url → { url, internal, sources:Set, text }

  while (queue.length && pages.length < a.maxPages) {
    const { url: u, level } = queue.shift();
    if (visited.has(u)) continue;
    visited.add(u);
    current = { console_errors: new Set(), js_errors: new Set(), resources: new Map() };
    const rec = { url: u, level, title: '', status: 0, time_ms: 0, links: 0, images: 0 };
    process.stdout.write(`[${pages.length + 1}/${a.maxPages}] ${u} `);
    try {
      const { resp, ms } = await load(page, u);
      rec.status = resp ? resp.status() : 0;
      rec.time_ms = ms;
      const final = normalize(page.url());
      if (final !== u) rec.redirects_to = final;
      if (new URL(final).hostname !== host) {
        rec.off_site = true;
      } else {
        await walkScroll(page);
        await page.waitForLoadState('networkidle', { timeout: 3000 }).catch(() => {});
        const c = await page.evaluate(checkContent);
        rec.title = c.title;
        rec.links = c.links.length;
        rec.images = c.totalImages;
        rec.meta_viewport = c.metaViewport;
        rec.images_without_alt = c.totalNoAlt;
        rec.examples_without_alt = c.noAlt;
        rec._broken = c.broken;
        rec.metrics = await page.evaluate(measure).catch(() => null);
        const file = path.join(dirPages, `${String(pages.length + 1).padStart(2, '0')}-${slug(u)}.jpg`);
        await capture(page, file);
        if (fs.existsSync(file)) rec.screenshot = rel(file);
        for (const l of c.links) {
          let abs;
          try { abs = new URL(l.href); } catch { continue; }
          if (!/^https?:$/.test(abs.protocol)) continue; // mailto:, tel:, javascript:
          const n = normalize(abs.href);
          const internal = abs.hostname === host;
          if (!linksMap.has(n)) linksMap.set(n, { url: n, internal, sources: new Set(), text: l.text });
          linksMap.get(n).sources.add(u);
          if (internal && !inQueue.has(n) && level < a.depth && !DO_NOT_CRAWL.test(abs.pathname + abs.search) && !FILE.test(abs.pathname)) {
            inQueue.add(n);
            queue.push({ url: n, level: level + 1 });
          }
        }
      }
      console.log(`→ ${rec.status} (${ms} ms)`);
    } catch (e) {
      rec.error = String(e.message || e).split('\n')[0].slice(0, 200);
      console.log(`→ error: ${rec.error}`);
    }
    rec.console_errors = [...current.console_errors];
    rec.js_errors = [...current.js_errors];
    const resources = [...current.resources.values()].filter((r) => normalize(r.url) !== u || r.type !== 'document');
    // Broken images: the ones the DOM shows without loading + the ones that responded with an error.
    const broken = new Map((rec._broken || []).map((i) => [i.src, i]));
    for (const r of resources.filter((x) => x.type === 'image')) broken.set(r.url, { ...(broken.get(r.url) || {}), src: r.url, status: r.status });
    rec.broken_images = [...broken.values()];
    rec.failed_resources = resources;
    delete rec._broken;
    pages.push(rec);
    current = null;
    if (a.pauseMs > 0) await wait(a.pauseMs);
  }
  const unvisited = queue.filter((c) => !visited.has(c.url)).length;
  await closeContext(context, page, 'walkthrough', 'Walkthrough of the pages (desktop 1280x720)');

  // Links: the visited internal ones already have a status; the rest are checked over HTTP.
  const byPage = new Map(pages.map((p) => [p.url, p]));
  const links = [...linksMap.values()].filter((l) => l.internal || a.external);
  console.log(`Checking ${links.length} links…`);
  await inParallel(links, 8, async (l) => {
    const p = byPage.get(l.url);
    if (p && !p.error && p.status) { l.status = p.status; return; }
    // Logout or delete links are never requested, not even to check them.
    const u = new URL(l.url);
    if (l.internal && DO_NOT_CRAWL.test(u.pathname + u.search)) { l.status = 0; l.error = 'Not checked: it logs out or may have side effects'; return; }
    Object.assign(l, await verifyLink(l.url));
  });
  const outputLinks = links.map((l) => ({ url: l.url, internal: l.internal, status: l.status, error: l.error, down: l.down,
    result: classifyLink(l), text: l.text, sources: [...l.sources] }));

  // Responsive: the first N healthy pages (crawl order: the ones closest to the start first).
  const forResponsive = pages.filter((p) => !p.error && p.status < 400 && !p.off_site).slice(0, a.responsive);
  const responsive = [];
  console.log(`Checking responsive for ${forResponsive.length} page(s) at ${resolutions.length} resolutions…`);
  // One context (and one video) per resolution; mobile and tablet emulate a touch screen.
  for (const r of resolutions) {
    const ctx = await newContext({ viewport: { width: r.width, height: r.height }, isMobile: r.width < 768, hasTouch: r.width < 1024 });
    const pg = await ctx.newPage();
    for (const [i, p] of forResponsive.entries()) {
      const row = { url: p.url, resolution: r.id, name: r.name, width: r.width, height: r.height };
      try {
        await load(pg, p.url);
        await walkScroll(pg);
        Object.assign(row, await pg.evaluate(checkResponsive, r.width < 768));
        const file = path.join(dirResponsive, `${String(i + 1).padStart(2, '0')}-${slug(p.url)}-${r.id}.jpg`);
        await capture(pg, file);
        if (fs.existsSync(file)) row.screenshot = rel(file);
      } catch (e) {
        row.error = String(e.message || e).split('\n')[0].slice(0, 200);
      }
      responsive.push(row);
    }
    await closeContext(ctx, pg, `responsive-${r.id}`, `${r.name} ${r.id}`);
  }
  await browser.close();
  fs.rmSync(path.join(dirVideos, 'tmp'), { recursive: true, force: true });

  const findings = buildFindings(pages, outputLinks, responsive, { slowMs: a.slowMs });
  const count = (cat) => findings.filter((x) => x.category === cat).length;
  const result = {
    url: startUrl, host, story: a.story || null, date: new Date().toISOString(), stamp: runStamp,
    duration_s: Math.round((Date.now() - t0) / 1000),
    config: { max_pages: a.maxPages, depth: a.depth, responsive: Number.isFinite(a.responsive) ? a.responsive : 'all',
      external: a.external, resolutions: resolutions.map((r) => r.id), video: a.video, slow_ms: a.slowMs },
    summary: {
      pages: pages.length, uncrawled_pages: unvisited, links: outputLinks.length,
      broken_links: outputLinks.filter((l) => l.result === 'broken').length,
      unverifiable_links: outputLinks.filter((l) => l.result === 'unverifiable').length,
      images: pages.reduce((s, p) => s + (p.images || 0), 0),
      broken_images: count('Broken image'), js_errors: count('JavaScript error'), console_errors: count('Console error'),
      failed_resources: count('Failed resource'), responsive: count('Responsive'), slow: count('Web performance'),
      findings: findings.length, ...timings(pages),
    },
    findings, pages, links: outputLinks, responsive, videos,
  };
  const out = path.join(folder, 'exploration.json');
  fs.writeFileSync(out, JSON.stringify(result, null, 2), 'utf8');
  const r = result.summary;
  console.log(`\nPages: ${r.pages}${unvisited ? ` (${unvisited} left uncrawled: raise --max-pages or --depth)` : ''}`);
  console.log(`Links: ${r.links} · broken ${r.broken_links} · unverifiable ${r.unverifiable_links}`);
  console.log(`Broken images: ${r.broken_images} · JS errors: ${r.js_errors} · console errors: ${r.console_errors} · failed resources: ${r.failed_resources}`);
  console.log(`Responsive: ${r.responsive} finding(s) · total findings: ${r.findings}`);
  console.log(`Data: ${path.relative(ROOT, out).split(path.sep).join('/')}`);
  if (generateReport(folder)) {
    console.log(`Report: ${path.relative(ROOT, path.join(folder, 'exploratory-report.html')).split(path.sep).join('/')}`);
  }
}

// Average, maximum and 90th percentile of the load times of the pages that opened.
function timings(pages) {
  const ms = pages.filter((p) => !p.error && p.time_ms).map((p) => p.time_ms).sort((x, y) => x - y);
  if (!ms.length) return { load_avg_ms: 0, load_max_ms: 0, load_p90_ms: 0 };
  return { load_avg_ms: Math.round(ms.reduce((s, x) => s + x, 0) / ms.length), load_max_ms: ms[ms.length - 1],
    load_p90_ms: ms[Math.min(ms.length - 1, Math.ceil(ms.length * 0.9) - 1)] };
}

if (require.main === module) {
  main().catch((e) => { console.error(`Error: ${e.message}`); process.exit(1); });
}

module.exports = { normalize, slug, parseResolutions, classifyLink, buildFindings, parseArgs, timings, cleanFolder, GENERATED,
  // Reused by the accessibility auditor (tools/accessibility).
  DO_NOT_CRAWL, FILE, stamp, walkScroll, load, capture };
