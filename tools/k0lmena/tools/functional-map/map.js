// Functional map of a website (project-documenter agent).
//
// Usage (from the repo root):
//   npm run functional-map -- [--url https://my-app.com] [--pages url1,url2] [--max-pages 30]
//                             [--depth 2] [--pause-ms 300] [--output <folder>] [--headed]
//
// Crawls the pages of the same host starting at the URL (by default APP_URL from .env, or BASEURL) and
// documents what is on each one, so the agents that write cases know the real application:
//   title and headings · navigation menus (the ones repeated across the whole site go only once)
//   · forms with each field (label, type, required, lengths, minimums and maximums, pattern,
//   list options) · buttons · visible messages (alerts, errors, notices) · table
//   headers · an excerpt of the main text.
//
// It is documentation, not a test: it takes no screenshots and does not look for errors (that is npm run explore).
// Only navigates with GET: it does not fill in or submit forms (any non-GET navigation is cut off) and
// does not follow logout or delete links. It covers the public pages (no login).
//
// Leaves functional-map.json and functional-map.md in input/documentation/project/ (or --output); each
// run replaces the previous one.
const fs = require('fs');
const path = require('path');
const { normalize, walkScroll, load } = require('../explorer/explore.js');
const { discover } = require('../pixel-perfect/pixel-perfect.js');
const { extractForms } = require('../forms/forms.js');

const ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const fromCwd = (p) => path.resolve(process.env.INIT_CWD || process.cwd(), p);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

function parseArgs(argv) {
  const a = { maxPages: 30, depth: 2, pauseMs: 300, headed: false };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    const v = () => argv[++i];
    if (k === '--url') a.url = v();
    else if (k === '--pages') a.pages = v().split(',').map((x) => x.trim()).filter(Boolean);
    else if (k === '--max-pages') a.maxPages = parseInt(v(), 10);
    else if (k === '--depth') a.depth = parseInt(v(), 10);
    else if (k === '--pause-ms') a.pauseMs = parseInt(v(), 10);
    else if (k === '--output') a.output = v();
    else if (k === '--headed') a.headed = true;
    else if (k === '-h' || k === '--help') a.help = true;
    else throw new Error(`Unknown option: ${k}`);
  }
  if (!(a.maxPages >= 1 && a.maxPages <= 200)) throw new Error('--max-pages must be between 1 and 200.');
  if (!(a.depth >= 0 && a.depth <= 5)) throw new Error('--depth must be between 0 and 5.');
  return a;
}

// Runs in the browser: what is visible on the page, without the forms (extractForms extracts them).
function _content() {
  const visible = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const text = (el) => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  const unique = (xs) => [...new Set(xs.filter(Boolean))];
  const headings = [...document.querySelectorAll('h1, h2, h3')].filter(visible)
    .map((h) => ({ level: Number(h.tagName[1]), text: text(h).slice(0, 120) })).filter((h) => h.text).slice(0, 40);
  const menus = [...document.querySelectorAll('nav, [role=navigation], header [role=menubar], aside [role=menu]')].filter(visible).map((n) => ({
    name: n.getAttribute('aria-label') || (n.closest('header') ? 'Header' : n.closest('footer') ? 'Footer' : n.closest('aside') ? 'Sidebar' : 'Navigation'),
    items: unique([...n.querySelectorAll('a[href], button, [role=menuitem]')].filter(visible).map((x) => text(x).slice(0, 60))).slice(0, 40),
  })).filter((m) => m.items.length);
  const inMenu = (el) => el.closest('nav, [role=navigation], form');
  const buttons = unique([...document.querySelectorAll('button, [role=button], input[type=submit], input[type=button], a.btn, a.button')]
    .filter((b) => visible(b) && !inMenu(b)).map((b) => (text(b) || b.value || b.getAttribute('aria-label') || '').slice(0, 60))).slice(0, 40);
  const messages = unique([...document.querySelectorAll('[role=alert], [role=status], [aria-live], .alert, .error, .warning, .notice, .toast, .message')]
    .filter(visible).map((m) => text(m).slice(0, 200))).slice(0, 20);
  const tables = [...document.querySelectorAll('table')].filter(visible)
    .map((t) => [...t.querySelectorAll('thead th, tr:first-child th')].map((th) => text(th).slice(0, 40)).filter(Boolean))
    .filter((c) => c.length).slice(0, 10);
  const main = document.querySelector('main, [role=main], article') || document.body;
  const paragraphs = [...main.querySelectorAll('p, li')].filter((p) => visible(p) && !p.closest('nav, footer, header, form')).map(text).filter((t) => t.length > 30);
  let excerpt = '';
  for (const p of paragraphs) { if ((excerpt + p).length > 700) break; excerpt += (excerpt ? ' ' : '') + p; }
  const desc = document.querySelector('meta[name=description]');
  return { title: document.title.trim(), description: desc ? desc.content.trim() : '', language: document.documentElement.lang || '',
    headings, menus, buttons, messages, tables, excerpt };
}

// The menus that appear on most pages are the global navigation: they go only once.
function splitGlobalMenus(pages) {
  const key = (m) => `${m.name}|${m.items.join('|')}`;
  const count = new Map();
  for (const p of pages) for (const m of p.menus || []) count.set(key(m), (count.get(key(m)) || 0) + 1);
  const minimum = Math.max(2, Math.ceil(pages.length * 0.6));
  const globals = [];
  for (const p of pages) {
    for (const m of p.menus || []) if (count.get(key(m)) >= minimum && !globals.some((g) => key(g) === key(m))) globals.push(m);
    p.menus = (p.menus || []).filter((m) => count.get(key(m)) < minimum);
  }
  return globals;
}

const cell = (x) => String(x ?? '').replace(/\|/g, '/').replace(/\s+/g, ' ').trim();

function constraints(c) {
  const r = [];
  if (c.minlength != null) r.push(`min. ${c.minlength} characters`);
  if (c.maxlength != null) r.push(`max. ${c.maxlength} characters`);
  if (c.min != null) r.push(`minimum ${c.min}`);
  if (c.max != null) r.push(`maximum ${c.max}`);
  if (c.pattern) r.push(`pattern ${c.pattern}`);
  if (c.options && c.options.length) r.push(`options: ${c.options.map((o) => o.text || o.value).filter(Boolean).slice(0, 12).join(', ')}`);
  if (c.placeholder) r.push(`placeholder "${c.placeholder}"`);
  return r.join('; ');
}

// Markdown of the map (with the tables in plain Markdown: they are then passed through format_tables.py).
function toMarkdown(map) {
  const l = [];
  l.push('---', 'title: Site functional map', 'type: web', `sources: ${map.url}`, `updated: ${map.date.slice(0, 10)}`,
    'generated_by: npm run functional-map', '---', '', `# Functional map of ${map.host}`, '');
  l.push(`Automatic crawl (GET only, no login, no form submission) of ${map.pages.length} page(s) starting at ${map.url}.`,
    'It describes what the application shows today: use it as context, **not** as a source of requirements.', '');
  if (map.unvisited) l.push(`> Some pages were left uncrawled (limit of ${map.max_pages}): raise --max-pages to cover them.`, '');
  if (map.global_navigation.length) {
    l.push('## Global navigation', '');
    for (const m of map.global_navigation) l.push(`- **${m.name}**: ${m.items.join(' · ')}`);
    l.push('');
  }
  l.push('## Pages', '', '| # | Page | Title | Forms | Fields |', '|---|---|---|---|---|');
  map.pages.forEach((p, i) => l.push(`| ${i + 1} | ${cell(p.path)} | ${cell(p.title || p.error)} | ${(p.forms || []).length} | ${(p.forms || []).reduce((s, f) => s + f.fields.length, 0)} |`));
  l.push('');
  map.pages.forEach((p, i) => {
    l.push(`## ${i + 1}. ${p.title || p.path}`, '', `- URL: ${p.url}`);
    if (p.error) { l.push(`- Could not be opened: ${p.error}`, ''); return; }
    if (p.description) l.push(`- Description: ${p.description}`);
    if (p.headings.length) l.push(`- Sections: ${p.headings.map((h) => h.text).join(' · ')}`);
    for (const m of p.menus) l.push(`- ${m.name} menu: ${m.items.join(' · ')}`);
    if (p.buttons.length) l.push(`- Buttons: ${p.buttons.join(' · ')}`);
    if (p.messages.length) l.push(`- Visible messages: ${p.messages.map((m) => `"${m}"`).join(' · ')}`);
    for (const t of p.tables) l.push(`- Table with columns: ${t.join(' · ')}`);
    if (p.excerpt) l.push(`- Text: ${p.excerpt}`);
    l.push('');
    for (const f of p.forms) {
      l.push(`### Form: ${f.name}${f.method ? ` (${f.method}${f.action ? ` ${f.action}` : ''})` : ''}`, '');
      l.push('| Field | Label | Type | Required | Constraints |', '|---|---|---|---|---|');
      for (const c of f.fields) {
        l.push(`| ${cell(c.name)} | ${cell(c.label)} | ${cell(c.type)} | ${c.required ? 'Yes' : c.required_mark ? 'Marked (*)' : 'No'} | ${cell(constraints(c))} |`);
      }
      l.push('', f.button ? '' : '> No visible submit button.', '');
    }
  });
  return l.filter((x, i, xs) => !(x === '' && xs[i - 1] === '')).join('\n') + '\n';
}

function formatTables(file) {
  const py = process.platform === 'win32' ? 'python' : 'python3';
  const r = require('child_process').spawnSync(py, [path.join(ROOT, 'scripts', 'format_tables.py'), file], { encoding: 'utf8' });
  if (r.status !== 0) console.log(`Could not align the tables (${(r.stderr || r.error || '').toString().trim().split('\n').pop()}). Run: python scripts/format_tables.py ${path.relative(ROOT, file)}`);
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
  const folder = a.output ? fromCwd(a.output) : path.join(ROOT, 'input', 'documentation', 'project');
  fs.mkdirSync(folder, { recursive: true });

  const { chromium } = require('playwright'); // here and not at the top: the tests use the functions without installing k0lmena
  const browser = await chromium.launch({ headless: !a.headed });
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, locale: process.env.LOCALE || 'en-US' });
  const page = await ctx.newPage();
  // Nothing is ever submitted: any non-GET navigation is cut off.
  await page.route('**/*', (route) => {
    const rq = route.request();
    return rq.isNavigationRequest() && rq.method() !== 'GET' ? route.abort() : route.continue();
  });

  console.log(`Functional map of ${start} · up to ${a.maxPages} pages · depth ${a.depth}`);
  const urls = await discover(page, start, a);
  const pages = [];
  for (const [i, u] of urls.entries()) {
    process.stdout.write(`[${i + 1}/${urls.length}] ${u} `);
    const rec = { url: u, path: new URL(u).pathname + new URL(u).search };
    try {
      const { resp } = await load(page, u);
      rec.status = resp ? resp.status() : 0;
      await walkScroll(page);
      Object.assign(rec, await page.evaluate(_content));
      rec.forms = (await page.evaluate(extractForms)).map(({ index, ...f }) => f);
      console.log(`· ${rec.forms.length} form(s)`);
    } catch (e) {
      rec.error = String(e.message || e).split('\n')[0];
      console.log(`· error: ${rec.error}`);
    }
    pages.push(rec);
    if (a.pauseMs) await wait(a.pauseMs);
  }
  await browser.close();

  const global_navigation = splitGlobalMenus(pages.filter((p) => !p.error));
  const map = { url: start, host, date: new Date().toISOString(), max_pages: a.maxPages,
    unvisited: !a.pages && urls.length >= a.maxPages, global_navigation, pages };
  const json = path.join(folder, 'functional-map.json');
  const md = path.join(folder, 'functional-map.md');
  fs.writeFileSync(json, JSON.stringify(map, null, 2));
  fs.writeFileSync(md, toMarkdown(map));
  formatTables(md);
  const rel = (p) => path.relative(ROOT, p).split(path.sep).join('/');
  console.log(`\n${pages.length} page(s), ${pages.reduce((s, p) => s + (p.forms || []).length, 0)} form(s).`);
  console.log(`Map: ${rel(md)} (data: ${rel(json)})`);
}

if (require.main === module) {
  main().catch((e) => { console.error(`Error: ${e.message}`); process.exit(1); });
}

module.exports = { parseArgs, splitGlobalMenus, constraints, toMarkdown };
