// Accessibility audit of a website (accessibility-analyst agent).
//
// Usage (from the repo root):
//   npm run accessibility -- [--url https://my-app.com] [--story US-001] [--level A|AA|AAA]
//                            [--max-pages 15] [--depth 2] [--pages url1,url2]
//                            [--best-practices yes|no] [--tabs 60] [--video yes|no] [--headed]
//
// It visits the pages of the same site starting from the URL (by default APP_URL in the .env, or BASEURL),
// or only those in --pages, and on each one:
//   - runs axe-core with the WCAG 2.2 rules of the requested level (AA by default) and, if requested, the
//     best practices; axe texts come out in English,
//   - navigates with Tab: elements that receive focus without a visible indicator, focus traps and a
//     skip-to-content link,
//   - checks reflow at 320px width (WCAG 1.4.10).
//
// Evidence: a screenshot of each page with the failing elements marked in red, a screenshot of
// each failing element and a video of the walkthrough. When it finishes it generates the HTML report
// (scripts/generate_accessibility_report.py).
//
// It only navigates with GET and does not submit forms. It leaves everything in output/accessibility/<US or host>/ and
// the previous run (with its analysis.json) moves to history/ (the last 5 are kept).
//
// An automated audit finds between 30 and 50 % of accessibility problems:
// the rest requires manual review (done by the agent).
const fs = require('fs');
const path = require('path');
const { archive } = require('../history/history.js');
const { normalize, slug, stamp, DO_NOT_CRAWL, FILE, walkScroll, load, capture } = require('../explorer/explore.js');

const ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const GENERATED = ['audit.json', 'analysis.json', 'accessibility-report.html', 'screenshots', 'videos'];
const IMPACT = { critical: 'Critical', serious: 'High', moderate: 'Medium', minor: 'Low' };
const SEV_ORDER = { 'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3 };
const TAGS = {
  A: ['wcag2a', 'wcag21a', 'wcag22a'],
  AA: ['wcag2a', 'wcag21a', 'wcag22a', 'wcag2aa', 'wcag21aa', 'wcag22aa'],
  AAA: ['wcag2a', 'wcag21a', 'wcag22a', 'wcag2aa', 'wcag21aa', 'wcag22aa', 'wcag2aaa', 'wcag21aaa', 'wcag22aaa'],
};

function parseArgs(argv) {
  const a = { level: 'AA', maxPages: 15, depth: 2, bestPractices: true, tabs: 60, video: true, headed: false, pauseMs: 200 };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    const v = () => argv[++i];
    if (k === '--url') a.url = v();
    else if (k === '--story') a.story = v();
    else if (k === '--level') a.level = String(v()).toUpperCase();
    else if (k === '--max-pages') a.maxPages = parseInt(v(), 10);
    else if (k === '--depth') a.depth = parseInt(v(), 10);
    else if (k === '--pages') a.pages = v().split(',').map((x) => x.trim()).filter(Boolean);
    else if (k === '--best-practices') a.bestPractices = !/^(no|false|0)$/i.test(v());
    else if (k === '--tabs') a.tabs = parseInt(v(), 10);
    else if (k === '--video') a.video = !/^(no|false|0)$/i.test(v());
    else if (k === '--pause-ms') a.pauseMs = parseInt(v(), 10);
    else if (k === '--output') a.output = v();
    else if (k === '--headed') a.headed = true;
    else if (k === '-h' || k === '--help') a.help = true;
    else throw new Error(`Unknown option: ${k}`);
  }
  if (!TAGS[a.level]) throw new Error('--level must be A, AA or AAA.');
  return a;
}

// "wcag143" → "1.4.3"; "wcag1410" → "1.4.10".
function criteria(tags) {
  return (tags || []).map((t) => t.match(/^wcag(\d)(\d)(\d{1,2})$/)).filter(Boolean).map((m) => `${m[1]}.${m[2]}.${m[3]}`);
}

function levelOf(tags) {
  if ((tags || []).some((t) => /^wcag2\d?a$/.test(t))) return 'A';
  if ((tags || []).some((t) => /^wcag2\d?aa$/.test(t))) return 'AA';
  if ((tags || []).some((t) => /^wcag2\d?aaa$/.test(t))) return 'AAA';
  return null;
}

// Severity: that of the axe impact; best practices (without a WCAG criterion) go down one level.
function severity(impact, tags) {
  const s = IMPACT[impact] || 'Medium';
  if (criteria(tags).length) return s;
  return { 'Critical': 'High', 'High': 'Medium', 'Medium': 'Low', 'Low': 'Low' }[s];
}

// The previous run is not deleted: it moves to history/<date>/ (the last 5 are kept) to compare it.
function cleanFolder(folder) {
  archive(folder, GENERATED, 'audit.json');
  for (const name of GENERATED) fs.rmSync(path.join(folder, name), { recursive: true, force: true });
}

// Walks the page with Tab and returns the focus order and the problems. At each step it compares
// the element's style with and without focus: if nothing changes, it has no visible indicator.
async function navigateWithKeyboard(page, tabs, focusScreenshot = null) {
  await page.evaluate(() => { if (document.activeElement) document.activeElement.blur(); window.scrollTo(0, 0); });
  const steps = [];
  let repeated = 0;
  for (let i = 0; i < tabs; i++) {
    await page.keyboard.press('Tab');
    const info = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body || el === document.documentElement) return null;
      const desc = (n) => {
        let s = n.tagName.toLowerCase();
        if (n.id) s += `#${n.id}`;
        const c = (typeof n.className === 'string' ? n.className : '').trim().split(/\s+/).filter(Boolean).slice(0, 2);
        if (c.length) s += `.${c.join('.')}`;
        return s;
      };
      const style = (n) => {
        const cs = getComputedStyle(n);
        return [cs.outlineStyle, cs.outlineWidth, cs.outlineColor, cs.boxShadow, cs.borderColor, cs.borderWidth,
          cs.backgroundColor, cs.color, cs.textDecorationLine].join('|');
      };
      // Real identity of the element (two identical consecutive links are not the same element).
      window.__k0ids = window.__k0ids || new WeakMap();
      if (!window.__k0ids.has(el)) window.__k0ids.set(el, (window.__k0n = (window.__k0n || 0) + 1));
      const withFocus = style(el);
      const r = el.getBoundingClientRect();
      // Without focus (removing it for an instant) to compare, then focus is given back.
      el.setAttribute('data-k0-tab', '1');
      el.blur();
      const noFocus = style(el);
      el.focus({ preventScroll: true });
      el.removeAttribute('data-k0-tab');
      return {
        uid: window.__k0ids.get(el), element: desc(el), text: (el.innerText || el.getAttribute('aria-label') || el.value || el.title || '').trim().slice(0, 50),
        visible_indicator: withFocus !== noFocus, on_screen: r.width > 0 && r.height > 0, url: location.href,
      };
    });
    if (!info) { if (steps.length) break; continue; } // went back to the start (or to the browser): end of the cycle
    if (info.url.split('#')[0] !== page.url().split('#')[0]) break;
    const previous = steps[steps.length - 1];
    if (previous && previous.uid === info.uid) {
      repeated++;
      if (repeated >= 3) {
        if (focusScreenshot) info.screenshot = await focusScreenshot('trap');
        return { steps, trap: info };
      }
      continue;
    }
    repeated = 0;
    if (steps.some((x) => x.uid === info.uid)) break; // it wrapped around (or went back to an already visited element)
    // Evidence of the first elements without a focus indicator (screenshot with focus on).
    if (!info.visible_indicator && focusScreenshot && steps.filter((x) => !x.visible_indicator).length < 3) {
      info.screenshot = await focusScreenshot(`no-focus-${steps.length + 1}`);
    }
    steps.push(info);
  }
  return { steps, trap: null };
}

// Screenshot of an element with context: a margin around it and the element marked in red, so it is
// clear what is being pointed out (a 30 px field alone, in a thumbnail, is a blank rectangle).
async function captureElement(page, selector, file, margin = 90) {
  const loc = page.locator(selector).first();
  try {
    await loc.scrollIntoViewIfNeeded({ timeout: 3000 });
    const box = await loc.boundingBox();
    if (!box) return;
    await loc.evaluate((el) => {
      el.setAttribute('data-k0-focus', '');
      if (!document.getElementById('k0-focus')) {
        const s = document.createElement('style');
        s.id = 'k0-focus';
        s.textContent = '[data-k0-focus]{outline:3px solid #ff2d2d !important;outline-offset:3px !important;box-shadow:0 0 0 9px rgba(255,45,45,.28) !important}';
        document.head.appendChild(s);
      }
    });
    const vp = page.viewportSize();
    const width = Math.min(vp.width, Math.max(box.width + margin * 2, 360));
    const height = Math.min(vp.height, Math.max(box.height + margin * 2, 220));
    const x = Math.max(0, Math.min(box.x + box.width / 2 - width / 2, vp.width - width));
    const y = Math.max(0, Math.min(box.y + box.height / 2 - height / 2, vp.height - height));
    await page.screenshot({ path: file, type: 'jpeg', quality: 82, clip: { x, y, width, height }, timeout: 5000 });
  } catch {
    // if the element cannot be located (hidden, outside the document), it stays without a screenshot
  } finally {
    await loc.evaluate((el) => el.removeAttribute('data-k0-focus')).catch(() => {});
  }
}

// Runs axe on the page (texts in English, axe's default; a locale can be passed) and returns only what is needed.
async function runAxe(page, tags, locale) {
  await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') });
  return page.evaluate(async ({ tags, locale }) => {
    if (locale) window.axe.configure({ locale });
    const r = await window.axe.run(document, { runOnly: { type: 'tag', values: tags }, resultTypes: ['violations', 'incomplete'] });
    const nodes = (ns, max) => ns.slice(0, max).map((n) => ({
      selector: Array.isArray(n.target) ? n.target.map((t) => (Array.isArray(t) ? t.join(' >>> ') : t)).join(' → ') : String(n.target),
      simple: Array.isArray(n.target) && n.target.length === 1 && typeof n.target[0] === 'string' ? n.target[0] : null,
      html: (n.html || '').slice(0, 300), summary: (n.failureSummary || '').slice(0, 600), impact: n.impact,
    }));
    const rule = (v, max) => ({ id: v.id, impact: v.impact, title: v.help, description: v.description, help: v.helpUrl,
      tags: v.tags, total_nodes: v.nodes.length, nodes: nodes(v.nodes, max) });
    return { violations: r.violations.map((v) => rule(v, 25)), review: r.incomplete.map((v) => rule(v, 5)),
      passes: r.passes.map((p) => p.id), inapplicable: r.inapplicable.length };
  }, { tags, locale });
}

function buildFindings(pages) {
  const byRule = new Map();
  const review = new Map();
  const others = [];
  for (const p of pages) {
    for (const v of p.violations || []) {
      if (!byRule.has(v.id)) {
        byRule.set(v.id, { source: 'axe', rule: v.id, title: v.title, description: v.description, help: v.help,
          impact: v.impact, severity: severity(v.impact, v.tags), wcag: criteria(v.tags), level: levelOf(v.tags),
          best_practice: !criteria(v.tags).length, pages: [], total_nodes: 0, examples: [] });
      }
      const h = byRule.get(v.id);
      h.pages.push(p.url);
      h.total_nodes += v.total_nodes;
      for (const n of v.nodes) if (h.examples.length < 12) h.examples.push({ page: p.url, ...n });
    }
    for (const v of p.review || []) {
      if (!review.has(v.id)) {
        review.set(v.id, { rule: v.id, title: v.title, description: v.description, help: v.help, wcag: criteria(v.tags),
          pages: [], total_nodes: 0, examples: [] });
      }
      const h = review.get(v.id);
      h.pages.push(p.url);
      h.total_nodes += v.total_nodes;
      for (const n of v.nodes) if (h.examples.length < 5) h.examples.push({ page: p.url, ...n });
    }
    const t = p.keyboard;
    if (t && t.trap) {
      others.push({ source: 'keyboard', rule: 'focus-trap', title: 'Focus trap: Tab cannot leave an element',
        description: 'When navigating with the keyboard, focus gets trapped and the person cannot continue through the page.',
        severity: 'Critical', wcag: ['2.1.2'], level: 'A', pages: [p.url], total_nodes: 1,
        examples: [{ page: p.url, selector: t.trap.element, html: t.trap.text, summary: 'Focus repeats on this element.', screenshot: t.trap.screenshot }] });
    }
    const noIndicator = (t ? t.steps : []).filter((x) => !x.visible_indicator);
    if (noIndicator.length) {
      others.push({ source: 'keyboard', rule: 'focus-not-visible', title: 'Elements that receive focus without a visible indicator',
        description: 'When reached with Tab, the element does not change its appearance: keyboard users do not know where they are.',
        severity: 'High', wcag: ['2.4.7'], level: 'AA', pages: [p.url], total_nodes: noIndicator.length,
        examples: noIndicator.slice(0, 8).map((x) => ({ page: p.url, selector: x.element, html: x.text,
          summary: 'Same style with and without focus (outline, shadow, border, background, color and underline).', screenshot: x.screenshot })) });
    }
    if (t && t.steps.length > 3 && !/skip|main content|jump to|salt|ir al contenido|contenido principal/i.test(t.steps[0].text)) {
      others.push({ source: 'keyboard', rule: 'no-skip-to-content', title: 'No link to skip to the main content',
        description: 'The first focusable element does not allow skipping the menu: keyboard users have to go through it on every page.',
        severity: 'Low', wcag: ['2.4.1'], level: 'A', pages: [p.url], total_nodes: 1,
        examples: [{ page: p.url, selector: t.steps[0].element, html: t.steps[0].text, summary: 'First focusable element.' }] });
    }
    if (p.reflow && p.reflow.overflows) {
      others.push({ source: 'reflow', rule: 'reflow-320', title: 'The content does not adapt to 320px width',
        description: `At 320px the content measures ${p.reflow.document_width}px: you have to scroll in two directions to read it (equivalent to a 400 % zoom).`,
        severity: 'Medium', wcag: ['1.4.10'], level: 'AA', pages: [p.url], total_nodes: 1,
        examples: [{ page: p.url, selector: p.reflow.element || '', html: '', summary: '', screenshot: p.reflow.screenshot }] });
    }
  }
  // Keyboard and reflow findings repeated on several pages are merged, like the axe ones.
  for (const o of others) {
    const k = `${o.source}:${o.rule}`;
    if (!byRule.has(k)) byRule.set(k, o);
    else {
      const h = byRule.get(k);
      h.pages.push(...o.pages);
      h.total_nodes += o.total_nodes;
      for (const ex of o.examples) if (h.examples.length < 12) h.examples.push(ex);
    }
  }
  const list = [...byRule.values()].sort((a, b) => SEV_ORDER[a.severity] - SEV_ORDER[b.severity] || b.total_nodes - a.total_nodes);
  return {
    findings: list.map((x, i) => ({ id: `A-${String(i + 1).padStart(2, '0')}`, ...x })),
    review: [...review.values()].map((x, i) => ({ id: `R-${String(i + 1).padStart(2, '0')}`, ...x })),
  };
}

// % of rules that pass out of those that apply, adding up all the pages.
function compliance(pages) {
  let ok = 0;
  let bad = 0;
  for (const p of pages) { ok += (p.passes || []).length; bad += (p.violations || []).length; }
  return ok + bad ? Math.round((ok / (ok + bad)) * 1000) / 10 : null;
}

function generateReport(folder) {
  const py = process.platform === 'win32' ? 'python' : 'python3';
  const r = require('child_process').spawnSync(py, [path.join(ROOT, 'scripts', 'generate_accessibility_report.py'),
    path.join(folder, 'audit.json'), path.join(folder, 'accessibility-report.html')], { encoding: 'utf8' });
  if (r.status !== 0) {
    const reason = (r.stderr || r.error || '').toString().trim().split(/\r?\n/).pop();
    console.log(`Could not generate the HTML report (${reason}). Generate it with: python scripts/generate_accessibility_report.py ` +
      '<folder>/audit.json <folder>/accessibility-report.html');
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
  if (a.story && !/^[A-Za-z]+-\d+$/.test(a.story)) throw new Error('--story must be an ID like US-001.');
  if (!(a.maxPages >= 1 && a.maxPages <= 200)) throw new Error('--max-pages must be between 1 and 200.');
  const startUrl = normalize(url);
  const host = new URL(startUrl).hostname;
  const tags = [...TAGS[a.level], ...(a.bestPractices ? ['best-practice'] : [])];
  // axe-core is in English by default (it ships no en.json locale): no locale is loaded.
  const locale = null;

  const folder = a.output ? path.resolve(a.output) : path.join(ROOT, 'output', 'accessibility', a.story || host);
  cleanFolder(folder);
  const dirPages = path.join(folder, 'screenshots', 'pages');
  const dirElements = path.join(folder, 'screenshots', 'elements');
  const dirVideos = path.join(folder, 'videos');
  for (const d of [dirPages, dirElements, dirVideos]) fs.mkdirSync(d, { recursive: true });
  const rel = (p) => path.relative(folder, p).split(path.sep).join('/');

  console.log(`Accessibility of ${startUrl} · WCAG 2.2 level ${a.level}${a.bestPractices ? ' + best practices' : ''} · up to ${a.maxPages} pages`);
  console.log(`Output: ${path.relative(ROOT, folder).split(path.sep).join('/')} (replaces the previous run)`);
  const t0 = Date.now();
  const { chromium } = require('playwright');
  const browser = await chromium.launch({ headless: !a.headed });
  const viewport = { width: 1280, height: 720 };
  const context = await browser.newContext({ viewport, locale: process.env.LOCALE || 'en-US',
    ...(a.video ? { recordVideo: { dir: path.join(dirVideos, 'tmp'), size: viewport } } : {}) });
  const page = await context.newPage();

  const queue = (a.pages || [startUrl]).map((u) => ({ url: normalize(u), level: 0 }));
  const inQueue = new Set(queue.map((c) => c.url));
  const visited = new Set();
  const pages = [];
  while (queue.length && pages.length < a.maxPages) {
    const { url: u, level } = queue.shift();
    if (visited.has(u)) continue;
    visited.add(u);
    const n = String(pages.length + 1).padStart(2, '0');
    const reg = { url: u, title: '', status: 0 };
    process.stdout.write(`[${pages.length + 1}/${a.maxPages}] ${u} `);
    try {
      const { resp } = await load(page, u);
      reg.status = resp ? resp.status() : 0;
      reg.title = await page.title();
      reg.language = await page.evaluate(() => document.documentElement.getAttribute('lang'));
      await walkScroll(page);
      // Links to keep crawling (only if a fixed list of pages was not passed).
      if (!a.pages && level < a.depth) {
        const hrefs = await page.evaluate(() => [...document.querySelectorAll('a[href]')].map((x) => x.href));
        for (const h of hrefs) {
          let abs;
          try { abs = new URL(h); } catch { continue; }
          if (!/^https?:$/.test(abs.protocol) || abs.hostname !== host) continue;
          const nu = normalize(abs.href);
          if (!inQueue.has(nu) && !DO_NOT_CRAWL.test(abs.pathname + abs.search) && !FILE.test(abs.pathname)) {
            inQueue.add(nu);
            queue.push({ url: nu, level: level + 1 });
          }
        }
      }
      const axe = await runAxe(page, tags, locale);
      Object.assign(reg, axe);
      // Screenshot of the focused element, with a margin around it so the context can be seen.
      const focusScreenshot = async (name) => {
        const box = await page.locator(':focus').first().boundingBox().catch(() => null);
        if (!box) return undefined;
        const file = path.join(dirElements, `${n}-keyboard-${name}.jpg`);
        const vp = page.viewportSize();
        const x = Math.max(0, box.x - 40);
        const y = Math.max(0, box.y - 40);
        await page.screenshot({ path: file, type: 'jpeg', quality: 80, clip: { x, y,
          width: Math.min(vp.width - x, box.width + 80), height: Math.min(vp.height - y, box.height + 80) } }).catch(() => {});
        return fs.existsSync(file) ? rel(file) : undefined;
      };
      reg.keyboard = await navigateWithKeyboard(page, a.tabs, focusScreenshot).catch((e) => ({ steps: [], trap: null, error: e.message }));

      // Evidence: each failing element (the first ones of each rule) and the page with everything marked.
      for (const v of reg.violations) {
        for (const [i, node] of v.nodes.entries()) {
          if (!node.simple) continue;
          if (i < 3) {
            const file = path.join(dirElements, `${n}-${v.id}-${i + 1}.jpg`);
            await captureElement(page, node.simple, file);
            if (fs.existsSync(file)) node.screenshot = rel(file);
          }
          await page.evaluate((s) => { try { document.querySelectorAll(s).forEach((e) => e.setAttribute('data-k0-mark', '')); } catch {} }, node.simple);
        }
      }
      const file = path.join(dirPages, `${n}-${slug(u)}.jpg`);
      await capture(page, file);
      if (fs.existsSync(file)) reg.screenshot = rel(file);

      // Reflow (1.4.10): at 320px width there must be no horizontal scroll.
      await page.setViewportSize({ width: 320, height: 640 });
      await load(page, u);
      reg.reflow = await page.evaluate(() => {
        const vw = document.documentElement.clientWidth;
        const width = Math.max(document.documentElement.scrollWidth, document.body ? document.body.scrollWidth : 0);
        let element = null;
        if (width > vw + 1) {
          const el = [...document.body.querySelectorAll('*')].find((x) => {
            const r = x.getBoundingClientRect();
            return r.right > vw + 1 && r.width > 0 && (!x.parentElement || x.parentElement.getBoundingClientRect().right <= vw + 1);
          });
          if (el) {
            el.setAttribute('data-k0-mark', '');
            element = el.tagName.toLowerCase() + (el.id ? `#${el.id}` : '') + (typeof el.className === 'string' && el.className.trim() ? `.${el.className.trim().split(/\s+/).slice(0, 2).join('.')}` : '');
          }
        }
        return { document_width: width, window_width: vw, overflows: width > vw + 1, element };
      });
      if (reg.reflow.overflows) {
        const cap = path.join(dirPages, `${n}-${slug(u)}-320.jpg`);
        await capture(page, cap);
        if (fs.existsSync(cap)) reg.reflow.screenshot = rel(cap);
      }
      await page.setViewportSize(viewport);
      console.log(`→ ${reg.status} · ${reg.violations.length} failing rule(s) · ${reg.keyboard.steps.length} elements with Tab`);
    } catch (e) {
      reg.error = String(e.message || e).split('\n')[0].slice(0, 200);
      console.log(`→ error: ${reg.error}`);
      await page.setViewportSize(viewport).catch(() => {});
    }
    pages.push(reg);
    if (a.pauseMs > 0) await new Promise((r) => setTimeout(r, a.pauseMs));
  }
  const video = a.video ? page.video() : null;
  await context.close();
  const videos = [];
  if (video) {
    const target = path.join(dirVideos, 'walkthrough.webm');
    await video.saveAs(target).catch(() => {});
    await video.delete().catch(() => {});
    if (fs.existsSync(target)) videos.push({ title: 'Audit walkthrough (axe, keyboard and reflow)', file: rel(target) });
  }
  await browser.close();
  fs.rmSync(path.join(dirVideos, 'tmp'), { recursive: true, force: true });

  const { findings, review } = buildFindings(pages);
  const count = (s) => findings.filter((h) => h.severity === s).length;
  const result = {
    url: startUrl, host, story: a.story || null, date: new Date().toISOString(), stamp: stamp(),
    duration_s: Math.round((Date.now() - t0) / 1000), tool: `axe-core ${require('axe-core/package.json').version}`,
    config: { level: a.level, best_practices: a.bestPractices, max_pages: a.maxPages, depth: a.depth, tabs: a.tabs, tags },
    summary: {
      pages: pages.length, uncrawled_pages: queue.filter((c) => !visited.has(c.url)).length,
      compliance_pct: compliance(pages), findings: findings.length,
      critical: count('Critical'), high: count('High'), medium: count('Medium'), low: count('Low'),
      affected_elements: findings.reduce((s, h) => s + h.total_nodes, 0),
      unmet_criteria: [...new Set(findings.flatMap((h) => h.wcag))].sort(),
      to_review: review.length,
    },
    findings, review, pages, videos,
  };
  const output = path.join(folder, 'audit.json');
  fs.writeFileSync(output, JSON.stringify(result, null, 2), 'utf8');
  const r = result.summary;
  console.log(`\nPages: ${r.pages} · automated compliance: ${r.compliance_pct ?? '—'} % of the rules`);
  console.log(`Findings: ${r.findings} (${r.critical} critical, ${r.high} high, ${r.medium} medium, ${r.low} low) · ${r.affected_elements} elements`);
  console.log(`Unmet WCAG criteria: ${r.unmet_criteria.join(', ') || 'none'} · to review by hand: ${r.to_review}`);
  console.log(`Data: ${path.relative(ROOT, output).split(path.sep).join('/')}`);
  if (generateReport(folder)) console.log(`Report: ${path.relative(ROOT, path.join(folder, 'accessibility-report.html')).split(path.sep).join('/')}`);
}

if (require.main === module) {
  main().catch((e) => { console.error(`Error: ${e.message}`); process.exit(1); });
}

module.exports = { parseArgs, criteria, levelOf, severity, buildFindings, compliance, cleanFolder, GENERATED };
