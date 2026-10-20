// Heuristic usability evaluation (ux-evaluator agent), with Nielsen's 10 heuristics.
//
// Usage (from the repo root):
//   npm run ux -- [--url https://my-app.com] [--pages url1,url2] [--max-pages 8] [--depth 1]
//                 [--resolutions 1366x768,390x844] [--story US-001] [--headed]
//
// It visits the pages (GET only, it does not submit forms) on desktop and mobile and reviews what can be measured:
//   H1 Visibility of status: title of each page (and that it is not repeated), the current section marked in the menu.
//   H2 The person's language: visible technical errors (Error 500, Exception, null, NaN, stack traces).
//   H3 Control and freedom: modals with no way to close them, links that open another tab without warning.
//   H4 Consistency: the same action with different names across the site (Sign in / Log in / Login),
//      too many button styles, several typefaces, skipped headings or more than one h1.
//   H5 Error prevention: email, phone or date fields as free text, passwords without "show".
//   H6 Recognition rather than recall: placeholder as the only label, icon-only buttons without a name.
//   H7 Flexibility: no search box on a site with many pages.
//   H8 Minimalist design: very long paragraphs, menus with too many options, too many primary buttons.
//   H9 Recovering from errors: the 404 page (that it exists, is not technical and offers a way back).
//   H10 Help: help, FAQ or contact links.
//   Mobile: the main action visible without scrolling.
// Each finding with the heuristic, the severity, the page and a screenshot of the marked element. What cannot
// be measured (flows, feedback on actions, cognitive load) is reviewed by the agent by hand.
//
// It leaves everything in output/ux/<US or host>/ (ux.json, ux-report.html, screenshots/, crops/); the previous
// run moves to history/ (the last 5 are kept).
const fs = require('fs');
const path = require('path');
const { normalize, slug, stamp, walkScroll, load } = require('../explorer/explore.js');
const { parseResolutions, discover } = require('../pixel-perfect/pixel-perfect.js');
const visual = require('../visual/compare.js');
const { archive } = require('../history/history.js');

const ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const fromCwd = (p) => path.resolve(process.env.INIT_CWD || process.cwd(), p);
const GENERATED = ['ux.json', 'analysis.json', 'ux-report.html', 'screenshots', 'crops'];
const SEV_ORDER = { 'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3 };
const HEURISTICS = {
  H1: 'Visibility of system status', H2: 'Match between the system and the real world (the person\'s language)', H3: 'User control and freedom',
  H4: 'Consistency and standards', H5: 'Error prevention', H6: 'Recognition rather than recall', H7: 'Flexibility and efficiency of use',
  H8: 'Aesthetic and minimalist design', H9: 'Help users recognize, diagnose and recover from errors', H10: 'Help and documentation',
};
// The same action with different names (for vocabulary consistency). English first; Spanish kept for Spanish sites.
const SYNONYMS = [
  ['sign in', 'log in', 'login', 'sign-in', 'iniciar sesión', 'iniciá sesión', 'ingresar', 'entrar', 'acceder'],
  ['sign up', 'register', 'create account', 'create an account', 'registrarse', 'registrate', 'crear cuenta', 'registro'],
  ['log out', 'logout', 'sign out', 'cerrar sesión', 'salir'],
  ['cart', 'bag', 'basket', 'carrito', 'bolsa', 'cesta'],
  ['checkout', 'buy now', 'pay', 'proceed to checkout', 'comprar', 'finalizar compra', 'pagar', 'ir a pagar'],
  ['search', 'buscar', 'búsqueda'],
  ['contact', 'contact us', 'get in touch', 'contacto', 'contactanos', 'contáctenos', 'escribinos'],
  ['send', 'submit', 'enviar', 'mandar'],
];
const WEIGHT = { 'Critical': 40, 'High': 25, 'Medium': 10, 'Low': 4 };

function parseArgs(argv) {
  const a = { maxPages: 8, depth: 1, resolutions: '1366x768,390x844', headed: false };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    const v = () => argv[++i];
    if (k === '--url') a.url = v();
    else if (k === '--pages') a.pages = v().split(',').map((x) => x.trim()).filter(Boolean);
    else if (k === '--max-pages') a.maxPages = parseInt(v(), 10);
    else if (k === '--depth') a.depth = parseInt(v(), 10);
    else if (k === '--resolutions') a.resolutions = v();
    else if (k === '--story') a.story = v();
    else if (k === '--output') a.output = v();
    else if (k === '--headed') a.headed = true;
    else if (k === '-h' || k === '--help') a.help = true;
    else throw new Error(`Unknown option: ${k}`);
  }
  if (a.story && !/^[A-Za-z]+-\d+$/.test(a.story)) throw new Error('--story must be an ID like US-001.');
  return a;
}

// In the page: everything that is measured. Marks the elements of each finding with data-k0-ux to crop them.
function _measureInPage(mobile) {
  const visible = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const box = (el) => { const r = el.getBoundingClientRect(); return { x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY), w: Math.round(r.width), h: Math.round(r.height) }; };
  const desc = (el) => el.tagName.toLowerCase() + (el.id ? `#${el.id}` : '') + (typeof el.className === 'string' && el.className.trim() ? `.${el.className.trim().split(/\s+/).slice(0, 2).join('.')}` : '');
  const text = (el) => (el.innerText || el.getAttribute('aria-label') || el.value || el.title || '').replace(/\s+/g, ' ').trim();
  const h = [];
  const add = (heur, severity, title, detail, el) => h.push({ heuristic: heur, severity, title, detail, element: el ? desc(el) : null, box: el && visible(el) ? box(el) : null });
  const body = document.body.innerText || '';
  // H2: visible technical errors
  const technical = body.match(/\b(Error \d{3}|Exception|Traceback|Stack ?trace|NullPointer|undefined is not|Cannot read propert\w+|SQLSTATE|ORA-\d+|Uncaught)\b/i);
  if (technical) add('H2', 'High', `Visible technical message: “${technical[0]}”`, 'The person sees a programming error instead of a message they can understand.', null);
  if (/\b(undefined|NaN|\[object Object\])\b/.test(body)) add('H2', 'Medium', 'Technical values in the text (undefined, NaN, [object Object])', 'A piece of data that did not load is shown with its technical name.', null);
  // H1: current section marked
  const nav = document.querySelector('nav, header');
  if (nav) {
    const links = [...nav.querySelectorAll('a[href]')].filter(visible);
    const current = links.find((l) => l.getAttribute('aria-current') || /\b(active|current|selected|activo)\b/i.test(l.className || '') || l.href === location.href);
    const marked = current && (current.getAttribute('aria-current') || /\b(active|current|selected|activo)\b/i.test(current.className || ''));
    if (links.length >= 3 && !marked) add('H1', 'Low', 'The menu does not mark which section you are in', 'Without an indicator (aria-current or an active style), the person does not know where they are.', nav);
    if (links.length > 9) add('H8', 'Low', `Main menu with ${links.length} options`, 'More than 7 to 9 options are hard to scan: group them.', nav);
  }
  // H3: modals that cannot be closed, links to another tab without warning
  for (const d of [...document.querySelectorAll('dialog[open], [role=dialog], [aria-modal=true]')].filter(visible)) {
    const close = d.querySelector('button[aria-label*=close i], button[aria-label*=dismiss i], button[aria-label*=errar i], [class*=close i], button[title*=close i], button[title*=errar i]') || [...d.querySelectorAll('button')].find((b) => /close|dismiss|cancel|×|✕|cerrar|cancelar/i.test(text(b)));
    if (!close) add('H3', 'Medium', 'A modal without a button to close it', 'The person is trapped: add a Close button (and make Esc work).', d);
  }
  const newTabs = [...document.querySelectorAll('a[target=_blank]')].filter((l) => visible(l) && !/new (tab|window)|opens in|external|↗|nueva (pestaña|ventana)|externo/i.test(text(l) + (l.getAttribute('aria-label') || '') + (l.title || '')));
  if (newTabs.length >= 3) add('H3', 'Low', `${newTabs.length} links open another tab without warning`, 'Warn with an icon or text: opening tabs without warning is disorienting (and breaks the Back button).', newTabs[0]);
  // H4: headings, typefaces, button styles
  const h1s = [...document.querySelectorAll('h1')].filter(visible);
  if (h1s.length === 0) add('H4', 'Low', 'The page has no main title (h1)', 'The h1 says what the page is about.', null);
  if (h1s.length > 1) add('H4', 'Low', `The page has ${h1s.length} main titles (h1)`, 'A single h1 per page keeps the hierarchy in order.', h1s[1]);
  let previous = 0;
  for (const hx of [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].filter(visible)) {
    const n = Number(hx.tagName[1]);
    if (previous && n > previous + 1) { add('H4', 'Low', `Skipped heading: from h${previous} to h${n}`, 'Heading levels must follow an order.', hx); break; }
    previous = n;
  }
  const fonts = new Set([...document.querySelectorAll('body *')].slice(0, 1500).filter((x) => x.childElementCount === 0 && (x.innerText || '').trim()).map((x) => getComputedStyle(x).fontFamily.split(',')[0].replace(/["']/g, '').trim()));
  if (fonts.size > 3) add('H4', 'Low', `${fonts.size} different typefaces`, `${[...fonts].slice(0, 5).join(', ')}: with more than 3 the page looks messy.`, null);
  const buttons = [...document.querySelectorAll('button, [role=button], a.btn, a[class*=button i], input[type=submit]')].filter(visible);
  const styles = new Set(buttons.map((b) => { const cs = getComputedStyle(b); return `${cs.backgroundColor}|${cs.borderRadius}`; }));
  // H6: icon-only buttons, placeholder as label
  for (const b of buttons) {
    if (!text(b) && !b.getAttribute('aria-label') && !b.title) { add('H6', 'Medium', 'Button without text or name (icon only)', 'Nobody knows what it does until they tap it: add visible text or an aria-label.', b); break; }
  }
  const fields = [...document.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=checkbox]):not([type=radio]), textarea, select')].filter(visible);
  const noLabel = fields.filter((c) => {
    const lab = (c.id && document.querySelector(`label[for="${CSS.escape(c.id)}"]`)) || c.closest('label');
    return !lab && !c.getAttribute('aria-label') && !c.getAttribute('aria-labelledby') && c.getAttribute('placeholder');
  });
  if (noLabel.length) add('H6', 'Medium', `${noLabel.length} field(s) use the placeholder as their only label`, 'When typing, the placeholder disappears and the person forgets what the field asked for.', noLabel[0]);
  // H5: field types
  for (const c of fields) {
    const hint = `${c.name} ${c.id} ${c.getAttribute('placeholder') || ''} ${c.getAttribute('autocomplete') || ''}`.toLowerCase();
    const type = (c.getAttribute('type') || 'text').toLowerCase();
    if (type === 'text' && /mail/.test(hint)) { add('H5', 'Medium', 'Email field as free text', 'With type="email" the phone shows the keyboard with @ and the browser validates the format.', c); break; }
  }
  for (const c of fields) {
    const hint = `${c.name} ${c.id} ${c.getAttribute('placeholder') || ''}`.toLowerCase();
    if ((c.getAttribute('type') || 'text') === 'text' && /(tel|phone|mobile|cell|whatsapp|celular)/.test(hint)) { add('H5', 'Low', 'Phone field as free text', 'With type="tel" the phone shows the numeric keypad.', c); break; }
  }
  const pwd = fields.find((c) => c.type === 'password');
  if (pwd) {
    const near = pwd.parentElement ? pwd.parentElement.querySelector('button, [role=button], input[type=checkbox]') : null;
    if (!near) add('H5', 'Low', 'The password has no option to show it', 'Showing the password reduces typing errors, especially on phones.', pwd);
  }
  // H8: long paragraphs and primary buttons
  const long = [...document.querySelectorAll('p')].filter((p) => visible(p) && (p.innerText || '').split(/\s+/).length > 120);
  if (long.length) add('H8', 'Low', `${long.length} paragraph(s) longer than 120 words`, 'Long texts are not read: split them, use headings or lists.', long[0]);
  // H10: help
  const help = [...document.querySelectorAll('a[href]')].some((l) => /help|faq|frequently asked|support|contact|ayuda|preguntas frecuentes|soporte|contacto/i.test(text(l) + l.href));
  // Mobile: main action visible without scrolling
  let ctaTop = null;
  if (mobile) {
    const cta = buttons.find((b) => b.getBoundingClientRect().width > 60) || null;
    if (cta) ctaTop = cta.getBoundingClientRect().top < innerHeight;
  }
  // Visible vocabulary (for consistency across pages).
  const interactive = [...document.querySelectorAll('a, button, [role=button], input[type=submit]')].filter(visible).map((x) => text(x).toLowerCase()).filter((t) => t && t.length < 40);
  return { title: document.title, findings: h, button_styles: styles.size, has_search: Boolean(document.querySelector('input[type=search], [role=search], input[name*=search i], input[name=q], input[placeholder*=search i], input[placeholder*=busc i]')),
    help, cta_top: ctaTop, vocabulary: [...new Set(interactive)], height: document.documentElement.scrollHeight };
}

async function check404(browser, start) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const u = new URL('/k0lmenia-page-that-does-not-exist-' + Date.now().toString(36), start).href;
  try {
    const r = await page.goto(u, { waitUntil: 'load', timeout: 30000 });
    const info = await page.evaluate(() => ({ text: (document.body.innerText || '').slice(0, 600), links: document.querySelectorAll('a[href]').length,
      technical: /(Error \d{3}|Exception|Traceback|nginx|Apache|Cannot GET|Whitelabel)/i.test(document.body.innerText || '') }));
    return { url: u, status: r ? r.status() : 0, ...info };
  } catch (e) {
    return { url: u, error: String(e.message || e).split('\n')[0] };
  } finally {
    await ctx.close();
  }
}

function generateReport(folder) {
  const py = process.platform === 'win32' ? 'python' : 'python3';
  const r = require('child_process').spawnSync(py, [path.join(ROOT, 'scripts', 'generate_ux_report.py'), path.join(folder, 'ux.json'),
    path.join(folder, 'ux-report.html')], { encoding: 'utf8' });
  if (r.status !== 0) {
    const reason = (r.stderr || r.error || '').toString().trim().split(/\r?\n/).pop();
    console.log(`Could not generate the HTML report (${reason}). Generate it with: python scripts/generate_ux_report.py <folder>/ux.json <folder>/ux-report.html`);
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
  const start = normalize(url);
  const host = new URL(start).hostname;
  const folder = a.output ? fromCwd(a.output) : path.join(ROOT, 'output', 'ux', a.story || host);
  archive(folder, GENERATED, 'ux.json');
  for (const n of GENERATED) fs.rmSync(path.join(folder, n), { recursive: true, force: true });
  const shotsDir = path.join(folder, 'screenshots');
  const cropsDir = path.join(folder, 'crops');
  for (const d of [shotsDir, cropsDir]) fs.mkdirSync(d, { recursive: true });
  const rel = (p) => path.relative(folder, p).split(path.sep).join('/');
  const relRoot = (p) => path.relative(ROOT, p).split(path.sep).join('/');
  const { chromium } = require('playwright');
  const browser = await chromium.launch({ headless: !a.headed });
  const t0 = Date.now();
  const c0 = await browser.newContext();
  const pages = await discover(await c0.newPage(), start, a);
  await c0.close();
  const resolutions = parseResolutions(a.resolutions);
  console.log(`UX: ${pages.length} page(s) × ${resolutions.length} resolution(s) · output ${relRoot(folder)}`);
  const screens = [];
  let findings = [];
  const titles = new Map();
  const vocabulary = new Map(); // term → pages
  let searchBox = false;
  let help = false;
  const styles = [];
  for (const [i, u] of pages.entries()) {
    const pageId = `${String(i + 1).padStart(2, '0')}-${slug(u)}`;
    for (const res of resolutions) {
      const mobile = res.width < 768;
      const ctx = await browser.newContext({ viewport: { width: res.width, height: res.height }, deviceScaleFactor: 1, locale: process.env.LOCALE || 'en-US',
        ...(mobile ? { isMobile: true, hasTouch: true } : {}) });
      const page = await ctx.newPage();
      const p = { page: pageId, url: u, resolution: res.id };
      process.stdout.write(`[${res.id.padEnd(9)}] ${u} `);
      try {
        await load(page, u);
        await walkScroll(page);
        await page.evaluate(() => window.scrollTo(0, 0));
        await visual.stabilize(page);
        const m = await page.evaluate(_measureInPage, mobile);
        const file = path.join(shotsDir, `${pageId}-${res.id}.png`);
        const height = Math.min(m.height, 8000);
        await page.screenshot({ path: file, fullPage: height === m.height, ...(height < m.height ? { clip: { x: 0, y: 0, width: res.width, height } } : {}) });
        p.screenshot = rel(file);
        p.title = m.title;
        if (!mobile) {
          titles.set(m.title, [...(titles.get(m.title) || []), u]);
          for (const t of m.vocabulary) vocabulary.set(t, new Set([...(vocabulary.get(t) || []), u]));
          styles.push(m.button_styles);
          searchBox = searchBox || m.has_search;
          help = help || m.help;
        }
        if (mobile && m.cta_top === false) m.findings.push({ heuristic: 'H8', severity: 'Medium', title: 'On mobile the main action is below the fold', detail: 'You have to scroll to find the first button: move it up or make it sticky.', box: null });
        for (const [k, h] of m.findings.entries()) {
          if (h.box && h.box.y < height) {
            const crop = path.join(cropsDir, `${pageId}-${res.id}-${k + 1}.png`);
            fs.writeFileSync(crop, visual.markedCrop(file, visual.windowOf([h.box], 60, 300, 140), h.box));
            h.crop = rel(crop);
          }
          findings.push({ ...h, page: pageId, url: u, resolution: res.id, screenshot: p.screenshot });
        }
        p.findings = m.findings.length;
        console.log(`→ ${m.findings.length} finding(s)`);
      } catch (e) {
        p.error = String(e.message || e).split('\n')[0].slice(0, 200);
        console.log(`→ error: ${p.error}`);
      }
      screens.push(p);
      await ctx.close();
    }
  }
  const p404 = await check404(browser, start);
  await browser.close();
  // Site-wide findings
  const site = [];
  for (const [t, us] of titles) if (us.length > 1 && pages.length > 1) site.push({ heuristic: 'H1', severity: 'Low', title: `${us.length} pages with the same title: “${t.slice(0, 60)}”`, detail: 'The tab title must say which page the person is on.' });
  for (const group of SYNONYMS) {
    const used = group.filter((g) => [...vocabulary.keys()].some((t) => t === g || t.startsWith(`${g} `) || t.endsWith(` ${g}`)));
    if (used.length > 1) site.push({ heuristic: 'H4', severity: 'Medium', title: `The same action with different names: ${used.map((x) => `“${x}”`).join(', ')}`, detail: 'Use a single name for each action across the whole site.' });
  }
  const maxStyles = styles.length ? Math.max(...styles) : 0;
  if (maxStyles > 5) site.push({ heuristic: 'H4', severity: 'Low', title: `${maxStyles} different button styles on one page`, detail: 'Define 2 or 3 styles (primary, secondary, text) and always use them the same way.' });
  if (!searchBox && pages.length >= 8) site.push({ heuristic: 'H7', severity: 'Low', title: 'There is no search box', detail: 'On a site with many pages, search is the shortcut for people who know what they are looking for.' });
  if (!help) site.push({ heuristic: 'H10', severity: 'Low', title: 'There are no help, FAQ or contact links', detail: 'A person who gets stuck has nowhere to ask.' });
  if (p404.error) site.push({ heuristic: 'H9', severity: 'Medium', title: 'Could not check the 404 error page', detail: p404.error });
  else {
    if (p404.status === 200) site.push({ heuristic: 'H9', severity: 'Medium', title: 'An address that does not exist responds 200', detail: `${p404.url} should respond 404 (search engines and monitors get confused).` });
    if (p404.technical) site.push({ heuristic: 'H9', severity: 'High', title: 'The error page is technical', detail: `It shows: “${p404.text.slice(0, 120)}”. It should explain what happened and how to get back.` });
    if (!p404.links) site.push({ heuristic: 'H9', severity: 'Medium', title: 'The error page has no way back', detail: 'Add the menu or a link to the home page and to search.' });
  }
  findings = [...findings, ...site.map((h) => ({ ...h, page: 'site', url: start, resolution: '—' }))];
  // The same problem on several pages = one finding.
  // The numbers in the title (how many links, how many options) change from page to page: they do not count for grouping.
  const groups = new Map();
  for (const h of findings) {
    const k = `${h.heuristic}|${h.title.replace(/\b\d+\b/g, '#')}`;
    if (!groups.has(k)) groups.set(k, { ...h, where: [] });
    groups.get(k).where.push({ url: h.url, resolution: h.resolution, crop: h.crop, screenshot: h.screenshot, title: h.title });
  }
  for (const g of groups.values()) {
    if (g.where.length > 1 && /\b\d+\b/.test(g.title)) {
      const noNumber = g.title.replace(/^\d+\s+/, '').replace(/\s*\b\d+\b\s*/g, ' ').trim();
      g.title = `${noNumber.charAt(0).toUpperCase()}${noNumber.slice(1)} (on ${g.where.length} screens)`;
      g.detail = `${g.detail} Per screen: ${g.where.map((d) => d.title.match(/\d+/)?.[0]).filter(Boolean).join(', ')}.`;
    }
  }
  findings = [...groups.values()].sort((x, y) => SEV_ORDER[x.severity] - SEV_ORDER[y.severity] || y.where.length - x.where.length);
  findings.forEach((h, i) => { h.id = `U-${String(i + 1).padStart(2, '0')}`; });
  const byHeur = Object.fromEntries(Object.keys(HEURISTICS).map((k) => {
    const hs = findings.filter((h) => h.heuristic === k);
    return [k, { name: HEURISTICS[k], findings: hs.length, score: Math.max(0, 100 - hs.reduce((s, h) => s + WEIGHT[h.severity], 0)) }];
  }));
  const score = Math.round(Object.values(byHeur).reduce((s, x) => s + x.score, 0) / 10);
  const result = {
    url: start, host, story: a.story || null, date: new Date().toISOString(), stamp: stamp(), duration_s: Math.round((Date.now() - t0) / 1000),
    tool: `Playwright ${require('playwright/package.json').version}`, resolutions: resolutions.map((r) => r.id), heuristics: HEURISTICS,
    summary: { pages: pages.length, screens: screens.length, findings: findings.length, score, by_heuristic: byHeur,
      by_severity: Object.fromEntries(['Critical', 'High', 'Medium', 'Low'].map((s) => [s, findings.filter((h) => h.severity === s).length])) },
    page_404: p404, findings, screens,
  };
  const output = path.join(folder, 'ux.json');
  fs.writeFileSync(output, JSON.stringify(result, null, 2), 'utf8');
  console.log(`\nHeuristic score: ${score}/100 · findings: ${findings.length}`);
  console.log(`Data: ${relRoot(output)}`);
  if (generateReport(folder)) console.log(`Report: ${relRoot(path.join(folder, 'ux-report.html'))}`);
}

if (require.main === module) {
  main().catch((e) => { console.error(`Error: ${e.message}`); process.exit(1); });
}

module.exports = { parseArgs, HEURISTICS, SYNONYMS, GENERATED };
