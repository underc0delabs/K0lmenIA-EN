// "Pixel perfect" visual regression (pixel-perfect agent).
//
// Usage (from the repo root):
//   npm run pixel-perfect -- [--url https://my-app.com] [--story US-001] [--pages url1,url2]
//                            [--max-pages 8] [--depth 1] [--resolutions 390x844,1366x768]
//                            [--hide ".banner,.date"] [--threshold 0.1] [--tolerance-px 3]
//                            [--pct-max 0.2] [--browser chromium|firefox|webkit] [--headed]
//                            [--reference] [--accept all|id1,id2]
//
// Takes a screenshot of each page at each resolution and compares it with its REFERENCE (the version
// accepted as correct):
//   - pixel by pixel: percent of the screen that changed and the regions with changes,
//   - element by element: what shifted (and by how many px), what changed size or text, what
//     no longer appears and what is new. Elements that moved together are reported as a
//     block (something above grew and pushed the rest), not one by one.
// Before each screenshot it turns off animations and transitions, hides the --hide areas (dates,
// rotating banners, ads) and waits for fonts and images: two identical screenshots give 0 %.
//
// The first run (or with --reference) CREATES the reference; the next ones compare against it.
// With --accept, the current screenshots become the reference (all or the given screens):
// that is accepting the changes as correct, so it is done only when the person confirms it.
// The reference can also come from a design (Figma): put a PNG in reference/ with the same
// name as the screen (01-home-1366x768.png) and it is compared pixel by pixel only.
//
// Leaves everything in output/pixel-perfect/<US or host>/: reference/ (kept across runs),
// actual/, diffs/, crops/, pixel-perfect.json and pixel-perfect-report.html. The previous
// comparison moves to history/ (last 5; the reference is kept). Without --hide, the hidden
// areas the reference was created with are reused. Only navigates with GET.
const fs = require('fs');
const path = require('path');
const { archive } = require('../history/history.js');
const { normalize, slug, stamp, DO_NOT_CRAWL, FILE, walkScroll, load } = require('../explorer/explore.js');
const visual = require('../visual/compare.js');

const ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const fromCwd = (p) => path.resolve(process.env.INIT_CWD || process.cwd(), p); // npm run changes the cwd to tools/k0lmena
const GENERATED = ['actual', 'diffs', 'crops', 'pixel-perfect.json', 'analysis.json', 'pixel-perfect-report.html'];
const SEV_ORDER = { Critical: 0, High: 1, Medium: 2, Low: 3 };

function parseArgs(argv) {
  const a = { maxPages: 8, depth: 1, hide: [], threshold: 0.1, tolerance: 3, pctMax: 0.2, browser: 'chromium',
    headed: false, reference: false, maxHeight: 12000 };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    const v = () => argv[++i];
    if (k === '--url') a.url = v();
    else if (k === '--story') a.story = v();
    else if (k === '--pages') a.pages = v().split(',').map((x) => x.trim()).filter(Boolean);
    else if (k === '--max-pages') a.maxPages = parseInt(v(), 10);
    else if (k === '--depth') a.depth = parseInt(v(), 10);
    else if (k === '--resolutions') a.resolutions = v();
    else if (k === '--hide') a.hide = v().split(',').map((x) => x.trim()).filter(Boolean);
    else if (k === '--threshold') a.threshold = parseFloat(v());
    else if (k === '--tolerance-px') a.tolerance = parseInt(v(), 10);
    else if (k === '--pct-max') a.pctMax = parseFloat(v());
    else if (k === '--browser') a.browser = v().toLowerCase();
    else if (k === '--height-max') a.maxHeight = parseInt(v(), 10);
    else if (k === '--reference') a.reference = true;
    else if (k === '--accept') a.accept = v();
    else if (k === '--output') a.output = v();
    else if (k === '--headed') a.headed = true;
    else if (k === '-h' || k === '--help') a.help = true;
    else throw new Error(`Unknown option: ${k}`);
  }
  if (!['chromium', 'firefox', 'webkit'].includes(a.browser)) throw new Error('--browser: chromium, firefox or webkit.');
  return a;
}

function parseResolutions(txt) {
  return txt.split(',').map((r) => r.trim()).filter(Boolean).map((r) => {
    const m = r.match(/^(\d{3,4})x(\d{3,4})$/);
    if (!m) throw new Error(`Invalid resolution: ${r} (use WIDTHxHEIGHT, for example 1366x768)`);
    const width = +m[1];
    return { id: r, width, height: +m[2], name: width < 600 ? 'Mobile' : width < 1024 ? 'Tablet' : 'Desktop' };
  });
}

// Hidden areas: if --hide is not passed, the reference's are used (otherwise they change on their own and give false differences).
const effectiveHide = (a, ref) => (a.hide.length ? a.hide : (ref && ref.config && ref.config.hide) || []);
const screenId = (n, url, res) => `${String(n).padStart(2, '0')}-${slug(url)}-${res}`;

async function discover(page, start, a) {
  if (a.pages) return a.pages.map(normalize);
  const host = new URL(start).hostname;
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
    } catch { /* the page that does not open is reported when capturing it */ }
  }
  return list;
}

// Stable screenshot of a screen: full-page PNG + boxes of the elements.
async function captureScreen(browser, url, res, a, file) {
  const ctx = await browser.newContext({ viewport: { width: res.width, height: res.height }, deviceScaleFactor: 1,
    locale: process.env.LOCALE || 'en-US', ...(a.browser === 'chromium' && res.width < 768 ? { isMobile: true, hasTouch: true } : {}) });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e.message || e).split('\n')[0]));
  try {
    const { resp } = await load(page, url);
    await walkScroll(page);
    await page.evaluate(() => window.scrollTo(0, 0));
    await visual.stabilize(page, { hide: a.hide });
    const measures = await visual.measureElements(page);
    const height = Math.min(measures.height, a.maxHeight);
    await page.screenshot({ path: file, fullPage: height === measures.height, timeout: 30000,
      ...(height < measures.height ? { clip: { x: 0, y: 0, width: res.width, height } } : {}) });
    return { status: resp ? resp.status() : 0, title: await page.title(), elements: measures.elements,
      width: measures.width, height: measures.height, cropped: height < measures.height, js_errors: errors };
  } finally {
    await ctx.close();
  }
}

const box = (e) => ({ x: e.x, y: e.y, w: e.w, h: e.h });
const textEl = (e) => (e.text ? `“${e.text.slice(0, 50)}”` : e.desc);

// What is above a shifted block and explains the shift: a new element, one
// that grew or one that disappeared, with a height similar to the shift.
function causeOf(b, c) {
  const above = (e) => e.y < b.from.y + 4;
  const added = c.added.filter(above).find((e) => Math.abs(e.h - b.dy) <= Math.max(6, Math.abs(b.dy) * 0.4));
  if (added && b.dy > 0) return `${textEl(added)} appeared (${added.h} px tall)`;
  const grew = c.resized.filter(above).find((e) => Math.abs(e.dh - b.dy) <= 6);
  if (grew) return `${textEl(grew)} changed height (${grew.dh > 0 ? '+' : ''}${grew.dh} px)`;
  const gone = c.missing.filter(above).find((e) => Math.abs(e.h + b.dy) <= Math.max(6, Math.abs(b.dy) * 0.4));
  if (gone && b.dy < 0) return `${textEl(gone)} is gone (${gone.h} px tall)`;
  return '';
}

// Findings of a screen from the element and pixel comparison.
function findingsOf(p, a) {
  const h = [];
  const c = p.elements_cmp;
  if (c) {
    for (const b of c.blocks) {
      const dist = Math.hypot(b.dx, b.dy);
      const dir = Math.abs(b.dy) >= Math.abs(b.dx) ? (b.dy > 0 ? `moved down ${b.dy}` : `moved up ${-b.dy}`) : (b.dx > 0 ? `shifted right ${b.dx}` : `shifted left ${-b.dx}`);
      h.push({ type: 'Shifted block', severity: dist >= 40 ? 'High' : dist >= 12 ? 'Medium' : 'Low',
        title: `${b.elements} elements ${dir} px`,
        detail: `From ${textEl(b.from)} down, everything moved the same: something above changed size or position and pushed the rest.` +
          (causeOf(b, c) ? ` Probable cause: ${causeOf(b, c)}.` : ''),
        elements: b.examples, _ref: box(b.from), _act: { ...box(b.from), x: b.from.x + b.dx, y: b.from.y + b.dy } });
    }
    for (const m of c.moved) {
      h.push({ type: 'Shifted element', severity: m.severity, title: `${textEl(m)} shifted ${m.dx >= 0 ? '+' : ''}${m.dx} px in X and ${m.dy >= 0 ? '+' : ''}${m.dy} px in Y`,
        detail: `${m.desc}: it was at (${m.x}, ${m.y}) and is now at (${m.actual.x}, ${m.actual.y})${m.dw || m.dh ? `; it also changed size (${m.w}×${m.h} → ${m.actual.w}×${m.actual.h})` : ''}.`,
        delta: { dx: m.dx, dy: m.dy, dw: m.dw, dh: m.dh }, _ref: box(m), _act: box(m.actual) });
    }
    for (const m of c.resized.filter((x) => Math.abs(x.dw) >= 8 || Math.abs(x.dh) >= 8)) {
      h.push({ type: 'Size change', severity: Math.abs(m.dw) >= 40 || Math.abs(m.dh) >= 40 ? 'Medium' : 'Low',
        title: `${textEl(m)} changed size: ${m.w}×${m.h} → ${m.actual.w}×${m.actual.h} px`,
        detail: `${m.desc} is still in the same place but ${m.dw ? `${m.dw > 0 ? 'grew' : 'shrank'} ${Math.abs(m.dw)} px in width` : ''}${m.dw && m.dh ? ' and ' : ''}${m.dh ? `${m.dh > 0 ? 'grew' : 'shrank'} ${Math.abs(m.dh)} px in height` : ''}.`,
        delta: { dx: 0, dy: 0, dw: m.dw, dh: m.dh }, _ref: box(m), _act: box(m.actual) });
    }
    for (const m of c.changed) {
      h.push({ type: 'Changed text', severity: ['a', 'button', 'label', 'h1', 'h2'].includes(m.tag) ? 'Medium' : 'Low',
        title: `${m.tag}: ${textEl(m)} → ${textEl(m.actual)}`, detail: `${m.desc} is in the same place with another text.`,
        _ref: box(m), _act: box(m.actual) });
    }
    for (const m of c.missing) {
      const inter = ['a', 'button', 'input', 'select', 'textarea'].includes(m.tag);
      h.push({ type: 'Missing element', severity: inter ? 'High' : 'Medium', title: `No longer appears: ${textEl(m)}`,
        detail: `${m.desc} was at (${m.x}, ${m.y}) in the reference and is not in the current version (or it is hidden).`, _ref: box(m) });
    }
    for (const s of c.styles || []) {
      const ex = s.elements[0];
      const inter = s.elements.some((x) => ['a', 'button', 'input', 'select', 'textarea'].includes(x.tag));
      h.push({ type: 'Style change', severity: inter || s.elements.length >= 5 ? 'Medium' : 'Low',
        title: `${s.elements.length === 1 ? textEl(ex) : `${s.elements.length} elements`}: ${s.name} ${s.from} → ${s.to}`,
        detail: `The ${s.name} of ${s.elements.slice(0, 4).map(textEl).join(', ')}${s.elements.length > 4 ? ' and others' : ''} changed.`,
        style: { property: s.prop, from: s.from, to: s.to }, _ref: box(ex), _act: box(ex.actual) });
    }
    for (const m of c.added) {
      h.push({ type: 'New element', severity: 'Low', title: `New: ${textEl(m)}`,
        detail: `${m.desc} at (${m.x}, ${m.y}) was not in the reference. If it is intentional, accept the new reference.`, _act: box(m) });
    }
  }
  if (p.height_ref && p.height && Math.abs(p.height - p.height_ref) > 20) {
    const d = p.height - p.height_ref;
    h.push({ type: 'Page height', severity: Math.abs(d) > 200 ? 'Medium' : 'Low',
      title: `The page ${d > 0 ? 'grew' : 'shrank'} ${Math.abs(d)} px in height (${p.height_ref} → ${p.height})`,
      detail: 'There is new content, content that went away or something that changed size.' });
  }
  // Pixels that changed and are not explained by a measured element (backgrounds, colors, images, icons).
  if (p.pct > a.pctMax && !h.some((x) => x.type !== 'Page height')) {
    h.push({ type: 'Visual change', severity: p.pct > 5 ? 'High' : p.pct > 1 ? 'Medium' : 'Low',
      title: `${p.pct} % of the screen changed (${p.regions.length} region(s))`,
      detail: 'The elements are in place but colors, images, fonts, borders or backgrounds change: look at the marked regions.',
      _region: p.regions[0] });
  }
  return h;
}

function generateReport(folder) {
  const py = process.platform === 'win32' ? 'python' : 'python3';
  const r = require('child_process').spawnSync(py, [path.join(ROOT, 'scripts', 'generate_pixel_perfect_report.py'),
    path.join(folder, 'pixel-perfect.json'), path.join(folder, 'pixel-perfect-report.html')], { encoding: 'utf8' });
  if (r.status !== 0) {
    const reason = (r.stderr || r.error || '').toString().trim().split(/\r?\n/).pop();
    console.log(`Could not generate the HTML report (${reason}). Generate it with: python scripts/generate_pixel_perfect_report.py ` +
      '<folder>/pixel-perfect.json <folder>/pixel-perfect-report.html');
    return false;
  }
  return true;
}

function accept(folder, which) {
  const dirRef = path.join(folder, 'reference');
  const dirAct = path.join(folder, 'actual');
  const dataFile = path.join(folder, 'pixel-perfect.json');
  if (!fs.existsSync(dataFile)) throw new Error('There is no comparison to accept: run first without --accept.');
  const data = JSON.parse(fs.readFileSync(dataFile, 'utf8'));
  const refFilePath = path.join(dirRef, 'reference.json');
  const ref = JSON.parse(fs.readFileSync(refFilePath, 'utf8'));
  const ids = which === 'all' ? data.screens.map((p) => p.id) : which.split(',').map((x) => x.trim());
  let n = 0;
  for (const id of ids) {
    const p = data.screens.find((x) => x.id === id);
    if (!p || !p.actual) { console.log(`  ${id}: not in the last comparison (ignored)`); continue; }
    fs.copyFileSync(path.join(folder, p.actual), path.join(dirRef, `${id}.png`));
    const elems = JSON.parse(fs.readFileSync(path.join(dirAct, `${id}.json`), 'utf8'));
    fs.writeFileSync(path.join(dirRef, `${id}.json`), JSON.stringify(elems));
    const r = ref.screens.find((x) => x.id === id);
    const fresh = { id, url: p.url, resolution: p.resolution, file: `${id}.png`, height: p.height, accepted: new Date().toISOString() };
    if (r) Object.assign(r, fresh); else ref.screens.push(fresh);
    n++;
  }
  ref.updated = new Date().toISOString();
  fs.writeFileSync(refFilePath, JSON.stringify(ref, null, 2));
  console.log(`${n} screen(s) accepted as the new reference.`);
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
  const start = normalize(url);
  const host = new URL(start).hostname;
  const folder = a.output ? fromCwd(a.output) : path.join(ROOT, 'output', 'pixel-perfect', a.story || host);
  const relRoot = (p) => path.relative(ROOT, p).split(path.sep).join('/');
  if (a.accept) {
    accept(folder, a.accept);
    return;
  }
  const dirRef = path.join(folder, 'reference');
  const refFilePath = path.join(dirRef, 'reference.json');
  const hasRef = fs.existsSync(refFilePath) && !a.reference;
  const ref = hasRef ? JSON.parse(fs.readFileSync(refFilePath, 'utf8')) : null;
  a.hide = effectiveHide(a, ref);

  archive(folder, GENERATED, 'pixel-perfect.json'); // the previous run moves to history/ (last 5)
  for (const n of GENERATED) fs.rmSync(path.join(folder, n), { recursive: true, force: true });
  if (a.reference) fs.rmSync(dirRef, { recursive: true, force: true });
  const dirAct = path.join(folder, 'actual');
  const dirDiff = path.join(folder, 'diffs');
  const dirCrop = path.join(folder, 'crops');
  for (const d of [dirRef, dirAct, dirDiff, dirCrop]) fs.mkdirSync(d, { recursive: true });
  const rel = (p) => path.relative(folder, p).split(path.sep).join('/');

  const pw = require('playwright');
  const browser = await pw[a.browser].launch({ headless: !a.headed });
  const t0 = Date.now();
  const resolutions = parseResolutions(a.resolutions || (ref && ref.config && ref.config.resolutions) || '390x844,1366x768');
  let pages;
  if (!a.pages && ref) {
    pages = [...new Set(ref.screens.map((p) => p.url))];
  } else {
    const ctx = await browser.newContext();
    pages = await discover(await ctx.newPage(), start, a);
    await ctx.close();
  }
  const mode = hasRef ? 'comparison' : 'reference';
  console.log(`${mode === 'reference' ? 'Creating the reference' : 'Comparing against the reference'}: ${pages.length} page(s) × ${resolutions.length} resolution(s) · ${a.browser}`);
  console.log(`Output: ${relRoot(folder)}`);

  const screens = [];
  let n = 0;
  for (const [i, u] of pages.entries()) {
    for (const res of resolutions) {
      n++;
      const id = (ref && ref.screens.find((p) => p.url === u && p.resolution === res.id) || {}).id || screenId(i + 1, u, res.id);
      process.stdout.write(`[${n}/${pages.length * resolutions.length}] ${res.id.padEnd(9)} ${u} `);
      const p = { id, url: u, resolution: res.id, device: res.name, vp_width: res.width };
      const actFile = path.join(mode === 'reference' ? dirRef : dirAct, `${id}.png`);
      try {
        const m = await captureScreen(browser, u, res, a, actFile);
        Object.assign(p, { status: m.status, title: m.title, height: m.height, cropped: m.cropped, js_errors: m.js_errors,
          n_elements: m.elements.length });
        fs.writeFileSync(path.join(mode === 'reference' ? dirRef : dirAct, `${id}.json`), JSON.stringify(m.elements));
      } catch (e) {
        p.error = String(e.message || e).split('\n')[0].slice(0, 200);
        console.log(`→ error: ${p.error}`);
        screens.push(p);
        continue;
      }
      if (mode === 'reference') {
        p.reference = rel(actFile);
        p.state = 'Reference';
        console.log('→ reference saved');
        screens.push(p);
        continue;
      }
      p.actual = rel(actFile);
      const refFile = path.join(dirRef, `${id}.png`);
      if (!fs.existsSync(refFile)) {
        p.state = 'New';
        console.log('→ no reference (new screen)');
        screens.push(p);
        continue;
      }
      p.reference = rel(refFile);
      const refInfo = ref.screens.find((x) => x.id === id) || {};
      p.height_ref = refInfo.height || visual.pngSize(refFile).height;
      p.reference_date = refInfo.accepted || ref.date;
      const cmp = visual.comparePng(refFile, actFile, { threshold: a.threshold });
      const dif = path.join(dirDiff, `${id}.png`);
      fs.writeFileSync(dif, cmp.diff);
      Object.assign(p, { diff: rel(dif), pct: cmp.pct, pixels: cmp.different, regions: cmp.regions.slice(0, 12) });
      // Elements: only if the reference is a screenshot (a Figma design has no elements).
      const elemRef = path.join(dirRef, `${id}.json`);
      if (fs.existsSync(elemRef)) {
        const r = JSON.parse(fs.readFileSync(elemRef, 'utf8'));
        const act = JSON.parse(fs.readFileSync(path.join(dirAct, `${id}.json`), 'utf8'));
        p.elements_cmp = visual.compareElements(r, act, { tolerance: a.tolerance });
      } else p.pixels_only = true;
      // Crops of the regions with the most changes: reference, actual and diff side by side.
      p.crops = [];
      for (const [k, reg] of p.regions.slice(0, 6).entries()) {
        const v = visual.windowOf([reg], 40, 260, 120);
        const base = path.join(dirCrop, `${id}-r${k + 1}`);
        fs.writeFileSync(`${base}-ref.png`, visual.markedCrop(refFile, v, reg, [255, 176, 32]));
        fs.writeFileSync(`${base}-act.png`, visual.markedCrop(actFile, v, reg, [255, 176, 32]));
        fs.writeFileSync(`${base}-dif.png`, visual.markedCrop(dif, v, null));
        p.crops.push({ region: reg, reference: rel(`${base}-ref.png`), actual: rel(`${base}-act.png`), diff: rel(`${base}-dif.png`) });
      }
      p.findings = findingsOf(p, a);
      // Crop of each finding: before (position in the reference) and after (in the actual one).
      for (const [k, h] of p.findings.entries()) {
        const boxes = [h._ref, h._act, h._region].filter(Boolean);
        if (!boxes.length) continue;
        const v = visual.windowOf(boxes, 70);
        const base = path.join(dirCrop, `${id}-h${k + 1}`);
        if (h._ref || h._region) {
          fs.writeFileSync(`${base}-before.png`, visual.markedCrop(refFile, v, h._ref || h._region));
          h.before = rel(`${base}-before.png`);
        }
        if (h._act || h._region) {
          fs.writeFileSync(`${base}-after.png`, visual.markedCrop(actFile, v, h._act || h._region, h._act ? [20, 168, 149] : [255, 45, 45]));
          h.after = rel(`${base}-after.png`);
        }
        delete h._ref; delete h._act; delete h._region;
      }
      const serious = p.findings.filter((x) => x.severity !== 'Low');
      p.state = !p.findings.length && p.pct <= a.pctMax ? 'No changes' : serious.length ? 'With changes' : 'Minor changes';
      console.log(`→ ${p.state} · ${p.pct} % · ${p.findings.length} finding(s)`);
      screens.push(p);
    }
  }
  await browser.close();

  if (mode === 'reference') {
    fs.writeFileSync(refFilePath, JSON.stringify({ url: start, host, story: a.story || null, date: new Date().toISOString(),
      browser: a.browser, config: { resolutions: resolutions.map((r) => r.id).join(','), hide: a.hide },
      screens: screens.filter((p) => !p.error).map((p) => ({ id: p.id, url: p.url, resolution: p.resolution,
        file: `${p.id}.png`, height: p.height, accepted: new Date().toISOString() })) }, null, 2));
  }

  // Numbered findings (the most serious first).
  const findings = [];
  for (const p of screens) {
    for (const h of p.findings || []) findings.push({ ...h, screen: p.id, url: p.url, resolution: p.resolution });
  }
  findings.sort((x, y) => SEV_ORDER[x.severity] - SEV_ORDER[y.severity]);
  findings.forEach((h, i) => { h.id = `V-${String(i + 1).padStart(2, '0')}`; });
  for (const p of screens) delete p.findings;

  const count = (e) => screens.filter((p) => p.state === e).length;
  const compared = screens.filter((p) => p.pct != null);
  const result = {
    mode, url: start, host, story: a.story || null, date: new Date().toISOString(), stamp: stamp(),
    duration_s: Math.round((Date.now() - t0) / 1000), browser: a.browser,
    tool: `Playwright ${require('playwright/package.json').version} · built-in comparison (pngjs)`,
    reference: ref ? { date: ref.date, updated: ref.updated || null, browser: ref.browser } : { date: new Date().toISOString(), browser: a.browser },
    config: { resolutions: resolutions.map((r) => r.id), hide: a.hide, threshold: a.threshold, tolerance_px: a.tolerance, pct_max: a.pctMax },
    summary: {
      pages: pages.length, screens: screens.length, compared: compared.length,
      no_changes: count('No changes'), minor_changes: count('Minor changes'), with_changes: count('With changes'),
      new_screens: count('New'), errors: screens.filter((p) => p.error).length,
      shifted_elements: findings.filter((h) => h.type === 'Shifted element').length,
      shifted_blocks: findings.filter((h) => h.type === 'Shifted block').length,
      missing: findings.filter((h) => h.type === 'Missing element').length,
      new_elements: findings.filter((h) => h.type === 'New element').length,
      pct_max: compared.length ? Math.max(...compared.map((p) => p.pct)) : 0,
      findings: findings.length,
      by_severity: Object.fromEntries(['Critical', 'High', 'Medium', 'Low'].map((s) => [s, findings.filter((h) => h.severity === s).length])),
    },
    findings, screens,
  };
  const out = path.join(folder, 'pixel-perfect.json');
  fs.writeFileSync(out, JSON.stringify(result, null, 2), 'utf8');
  const r = result.summary;
  if (mode === 'reference') console.log(`\nReference created: ${r.screens - r.errors} screen(s). The next run compares against it.`);
  else console.log(`\nNo changes: ${r.no_changes} · minor changes: ${r.minor_changes} · with changes: ${r.with_changes} · new: ${r.new_screens} · findings: ${r.findings}`);
  console.log(`Data: ${relRoot(out)}`);
  if (generateReport(folder)) console.log(`Report: ${relRoot(path.join(folder, 'pixel-perfect-report.html'))}`);
}

if (require.main === module) {
  main().catch((e) => { console.error(`Error: ${e.message}`); process.exit(1); });
}

module.exports = { parseArgs, parseResolutions, findingsOf, screenId, effectiveHide, discover, GENERATED };
