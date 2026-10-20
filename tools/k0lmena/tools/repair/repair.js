// Web automation repairer (automation-repairer agent).
//
// Usage (from the repo root):
//   npm run repair -- [--story US-001] [--report tools/k0lmena/reports/web/cucumber-report.json]
//                      [--failures output/failures/<x>/failures.json] [--base-url https://my-app.com]
//   npm run repair -- --apply R-01,R-03 [--story US-001]     → applies those proposals (or "safe")
//   npm run repair -- --verify [--story US-001]              → re-runs the repaired scenarios
//   npm run repair -- --report-only [--story US-001]         → regenerates the report
//
// 1) Analyze (default): takes the web scenarios that failed in the last npm test (or the ones from the
//    failure-analyst with --failures), extracts from the error the locator that did not work, looks for it in
//    web/locators, in the steps or in the .feature, and tests it against the DOM k0lmena saved at the
//    moment of the failure (reports/web/dom/). Diagnoses: no longer exists, matches several
//    elements, exists but is not visible, or exists and is visible (the wait failed). Looks for the most
//    similar candidates (role, accessible name, text, placeholder, label, data-testid, id) and proposes the
//    most robust new locator (role + name → label → placeholder → testId → text), verifying that it
//    finds ONE single element. Marks the proposed element with a box on a screenshot of the DOM.
//    It does not touch any file.
// 2) Apply (--apply): replaces the locator in its file (saves a copy in backup/ and the diff
//    in changes.diff). "safe" = the High confidence ones in action steps. What comes from a
//    verification step (Then) may be an application bug: it is only applied if it is named by ID.
// 3) Verify (--verify): runs only the repaired scenarios (TAGS with their @US and @TC) in a
//    folder of their own and marks each repair as Verified or Still failing. Runs against the
//    environment like npm test: it is done only with confirmation.
//
// Leaves everything in output/repairs/<US or suite>/: repairs.json, repair-report.html,
// screenshots/, backup/, changes.diff and verification/. Analyzing again REPLACES the folder.
const fs = require('fs');
const path = require('path');
const { archive } = require('../history/history.js');
const { spawnSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const fromCwd = (p) => path.resolve(process.env.INIT_CWD || process.cwd(), p); // npm run changes the cwd to tools/k0lmena
const K0 = path.resolve(__dirname, '..', '..');
const GENERATED = ['repairs.json', 'analysis.json', 'repair-report.html', 'screenshots', 'backup', 'changes.diff', 'verification'];
const METHODS = ['getByRole', 'getByText', 'getByLabel', 'getByPlaceholder', 'getByTestId', 'getByAltText', 'getByTitle'];

function parseArgs(argv) {
  const a = {};
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    const v = () => argv[++i];
    if (k === '--story') a.story = v().toUpperCase();
    else if (k === '--report') a.report = v();
    else if (k === '--failures') a.failures = v();
    else if (k === '--base-url') a.baseUrl = v();
    else if (k === '--apply') a.apply = v();
    else if (k === '--verify') a.verify = true;
    else if (k === '--report-only') a.reportOnly = true;
    else if (k === '--output') a.output = v();
    else if (k === '-h' || k === '--help') a.help = true;
    else throw new Error(`Unknown option: ${k}`);
  }
  if (a.story && !/^[A-Z]+-\d+$/.test(a.story)) throw new Error('--story must be an ID like US-001.');
  return a;
}

// ------------------------------------------------------------------ locator from the error message
// "getByRole('button', { name: 'Sign up', exact: true })" → { role: 'button', name: 'Sign up', exact: true }
function _literal(s) {
  s = s.trim();
  let m = s.match(/^(['"`])((?:\\.|(?!\1).)*)\1/);
  if (m) return { value: m[2].replace(/\\(['"`\\])/g, '$1'), rest: s.slice(m[0].length) };
  m = s.match(/^\/((?:\\.|[^/])+)\/([a-z]*)/);
  if (m) return { value: { regex: m[1], flags: m[2] }, rest: s.slice(m[0].length) };
  return null;
}

function _options(s) {
  const o = {};
  const m = s.match(/\{([^}]*)\}/);
  if (!m) return o;
  const name = m[1].match(/name:\s*((['"`]).*?\2|\/(?:\\.|[^/])+\/[a-z]*)/);
  if (name) o.name = _literal(name[1]).value;
  if (/exact:\s*true/.test(m[1])) o.exact = true;
  return o;
}

function locatorFromError(error) {
  if (!error) return null;
  // Playwright writes the locator in "Locator: …", "waiting for …" or "strict mode violation: …".
  const re = new RegExp(`(?:locator\\(([\\s\\S]*?)\\)\\.)?(${METHODS.join('|')})\\(([^\\n]*?)\\)(?=\\s|$|\\.|,)`, 'm');
  const m = error.match(re);
  if (m) {
    const method = m[2];
    const lit = _literal(m[3]);
    if (!lit) return null;
    const text = `${method}(${m[3]})`;
    if (method === 'getByRole') return { type: 'role', input: { role: lit.value, ..._options(lit.rest) }, text };
    const key = { getByText: 'text', getByLabel: 'label', getByPlaceholder: 'placeholder', getByTestId: 'testId',
      getByAltText: 'alt', getByTitle: 'title' }[method];
    return { type: key, input: { [key]: lit.value }, text };
  }
  const css = error.match(/(?:waiting for |Locator: |violation: )locator\((['"`])(.+?)\1\)/);
  if (css) {
    if (css[2].startsWith('xpath=')) return { type: 'xpath', input: { xpath: css[2].slice(6) }, text: `locator('${css[2]}')` };
    return { type: 'css', input: { css: css[2] }, text: `locator('${css[2]}')` };
  }
  return null;
}

const valueTxt = (v) => (v && typeof v === 'object' && v.regex ? `/${v.regex}/${v.flags}` : String(v));

// TypeScript code of a LocatorInput (as the mappers write it).
function codeOf(input) {
  const q = (s) => (s && typeof s === 'object' && s.regex ? `/${s.regex}/${s.flags}` : `'${String(s).replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`);
  const parts = Object.entries(input).filter(([, v]) => v !== undefined).map(([k, v]) => `${k}: ${typeof v === 'boolean' ? v : q(v)}`);
  return `{ ${parts.join(', ')} }`;
}

// ------------------------------------------------------------------ where the locator is in the code
function listFiles(dir, ext) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir).filter((f) => f.endsWith(ext)).map((f) => path.join(dir, f));
}

const escRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

function locate(loc, sc) {
  const relK = (p) => path.relative(ROOT, p).split(path.sep).join('/');
  const value = loc.input.name ?? loc.input.text ?? loc.input.label ?? loc.input.placeholder ?? loc.input.testId ?? loc.input.alt ??
    loc.input.title ?? loc.input.css ?? loc.input.xpath;
  if (value == null || typeof value === 'object') return null;
  const key = loc.type === 'role' ? 'name' : loc.type;
  const reEntry = new RegExp(`\\b${key}\\s*:\\s*(['"\`])${escRe(value)}\\1`);
  // 1) the story's locators first, then the rest
  const locs = listFiles(path.join(K0, 'web', 'locators'), '.ts').sort((x, y) => (sc.story && x.includes(sc.story) ? -1 : 0) - (sc.story && y.includes(sc.story) ? -1 : 0));
  for (const f of locs) {
    const lines = fs.readFileSync(f, 'utf8').split(/\r?\n/);
    const i = lines.findIndex((l) => reEntry.test(l) && (loc.type !== 'role' || new RegExp(`role\\s*:\\s*['"\`]${escRe(loc.input.role)}['"\`]`).test(l)));
    if (i >= 0) {
      const m = lines[i].match(/^\s*([\w$]+)\s*:/);
      return { type: 'locator', file: relK(f), line: i + 1, text: lines[i].trim(), key: m ? m[1] : null };
    }
  }
  // 2) the value comes from the .feature (a step parameter): the scenario passes it as "text"
  if (sc.uri) {
    const f = path.join(K0, sc.uri);
    if (fs.existsSync(f)) {
      const lines = fs.readFileSync(f, 'utf8').split(/\r?\n/);
      const i = lines.findIndex((l, k) => k + 1 >= (sc.line || 0) && l.includes(`"${value}"`));
      if (i >= 0) return { type: 'feature', file: relK(f), line: i + 1, text: lines[i].trim(), value };
    }
  }
  // 3) written directly in a step
  for (const f of listFiles(path.join(K0, 'web', 'steps'), '.ts')) {
    const lines = fs.readFileSync(f, 'utf8').split(/\r?\n/);
    const i = lines.findIndex((l) => l.includes(`'${value}'`) || l.includes(`"${value}"`) || l.includes(`\`${value}\``));
    if (i >= 0) return { type: 'step', file: relK(f), line: i + 1, text: lines[i].trim() };
  }
  return null;
}

// ------------------------------------------------------------------ failures to repair
function _texts(p) {
  return (p.embeddings || []).filter((x) => x.mime_type === 'text/plain').map((x) => Buffer.from(x.data, 'base64').toString('utf8'));
}

function reportFailures(file, story) {
  const base = path.dirname(file);
  let features = [];
  try { features = JSON.parse(fs.readFileSync(file, 'utf8') || '[]'); } catch { throw new Error(`Could not read ${file}.`); }
  const output = new Map();
  for (const f of features) {
    for (const sc of f.elements || []) {
      if (sc.type === 'background') continue;
      const tags = [...new Set([...(f.tags || []), ...(sc.tags || [])].map((t) => t.name.replace(/^@/, '')))];
      const us = tags.find((t) => /^US-\d+$/i.test(t)) || null;
      if (story && (us || '').toUpperCase() !== story) continue;
      let step = null;
      let error = '';
      let dom = null;
      let url = null;
      for (const p of sc.steps || []) {
        const r = p.result || {};
        if (r.status === 'failed' && !step) {
          step = `${(p.keyword || '').trim()} ${p.name || ''}`.trim();
          error = (r.error_message || '').replace(/\x1b\[[0-9;]*m/g, '').trim();
        }
        for (const t of _texts(p)) {
          const d = t.match(/^DOM:[ \t]*([^\r\n]+)/); // the scenario name may contain spaces
          if (d && !dom) dom = path.join(base, d[1]);
          const u = t.match(/- URL:\s*(\S+)/);
          if (u && !url) url = u[1];
        }
      }
      const key = `${f.uri}:${sc.line}`;
      if (!step) { output.delete(key); continue; } // with retry: if the last attempt passed, there is nothing to repair
      output.set(key, { scenario: sc.name, feature: f.name, uri: f.uri.split(path.sep).join('/'), line: sc.line, tags, story: us,
        case: tags.find((t) => /^TC(-API)?-\d+$/.test(t)) || null, step, error, dom, url });
    }
  }
  return [...output.values()];
}

function analystFailures(file, story) {
  const data = JSON.parse(fs.readFileSync(file, 'utf8'));
  const dir = path.dirname(file);
  return (data.failures || []).filter((x) => x.suite === 'web' && (!story || (x.story || '').toUpperCase() === story)).map((x) => {
    const dom = (x.evidence || []).find((ev) => ev.type === 'dom');
    return { scenario: x.scenario, feature: x.feature, uri: x.uri, line: x.line, tags: x.tags || [], story: x.story, case: x.case,
      step: x.failed_step, error: (x.error || '').replace(/\x1b\[[0-9;]*m/g, ''), dom: dom ? path.join(dir, dom.file) : null, url: x.url || null, analyst_category: x.category };
  });
}

// ------------------------------------------------------------------ analysis against the saved DOM
function locatorOf(page, input) {
  if ('role' in input) return page.getByRole(input.role, { name: _rx(input.name), exact: input.exact });
  if ('testId' in input) return page.getByTestId(input.testId);
  if ('placeholder' in input) return page.getByPlaceholder(_rx(input.placeholder));
  if ('label' in input) return page.getByLabel(_rx(input.label));
  if ('text' in input) return page.getByText(_rx(input.text));
  if ('alt' in input) return page.getByAltText(_rx(input.alt));
  if ('title' in input) return page.getByTitle(_rx(input.title));
  if ('css' in input) return page.locator(input.css);
  if ('xpath' in input) return page.locator(`xpath=${input.xpath}`);
  throw new Error('locator without a type');
}
const _rx = (v) => (v && typeof v === 'object' && v.regex ? new RegExp(v.regex, v.flags) : v);

// In the browser: candidates similar to the original locator, with their score and the data to build
// new locators. Runs on the saved DOM (without the page's JavaScript).
function _candidatesInPage(orig) {
  const norm = (s) => (s || '').toString().normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
  const tokens = (s) => norm(s).split(/[^a-z0-9ñ]+/).filter((t) => t.length > 1);
  const similar = (a, b) => {
    a = norm(a); b = norm(b);
    if (!a || !b) return 0;
    if (a === b) return 1;
    if (a.includes(b) || b.includes(a)) return 0.75 * Math.min(a.length, b.length) / Math.max(a.length, b.length) + 0.2;
    const ta = new Set(tokens(a)); const tb = new Set(tokens(b));
    const common = [...ta].filter((t) => tb.has(t) || [...tb].some((u) => u.length > 3 && t.length > 3 && (u.startsWith(t.slice(0, 4)) || t.startsWith(u.slice(0, 4))))).length;
    return ta.size && tb.size ? (2 * common) / (ta.size + tb.size) * 0.85 : 0;
  };
  const roleOf = (el) => {
    const r = el.getAttribute('role');
    if (r) return r;
    const t = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (t === 'button' || (t === 'input' && ['submit', 'button', 'reset'].includes(type))) return 'button';
    if (t === 'a' && el.hasAttribute('href')) return 'link';
    if (/^h[1-6]$/.test(t)) return 'heading';
    if (t === 'input' && type === 'checkbox') return 'checkbox';
    if (t === 'input' && type === 'radio') return 'radio';
    if (t === 'select') return 'combobox';
    if (t === 'textarea' || (t === 'input' && ['', 'text', 'email', 'password', 'search', 'tel', 'url', 'number'].includes(type))) return 'textbox';
    if (t === 'img') return 'img';
    if (t === 'nav') return 'navigation';
    if (t === 'li') return 'listitem';
    return null;
  };
  const labelOf = (el) => {
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) return l.innerText.trim(); }
    const p = el.closest('label');
    return p ? p.innerText.trim() : '';
  };
  const nameOf = (el) => (el.getAttribute('aria-label') || (el.getAttribute('aria-labelledby') || '').split(/\s+/).map((i) => (document.getElementById(i) || {}).innerText || '').join(' ').trim()
    || labelOf(el) || (['INPUT'].includes(el.tagName) && ['submit', 'button'].includes(el.type) ? el.value : '') || el.innerText || el.getAttribute('alt')
    || el.getAttribute('title') || '').replace(/\s+/g, ' ').trim();
  const target = orig.name ?? orig.text ?? orig.label ?? orig.placeholder ?? orig.testId ?? orig.alt ?? orig.title ?? '';
  const targetTxt = typeof target === 'object' && target ? target.regex : target;
  // Clues are recovered from the original CSS: #id, .class and text.
  const cssHints = orig.css ? { id: (orig.css.match(/#([\w-]+)/) || [])[1], classes: (orig.css.match(/\.([\w-]+)/g) || []).map((c) => c.slice(1)) } : null;
  const SEL = 'a,button,input,select,textarea,h1,h2,h3,h4,h5,h6,label,img,[role],[data-testid],[aria-label],li,p,span,div,td,th';
  const output = [];
  for (const el of document.querySelectorAll(SEL)) {
    const t = el.tagName.toLowerCase();
    const noOwnText = ['span', 'div', 'p', 'li', 'td', 'th'].includes(t) && ![...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (noOwnText) continue;
    const r = el.getBoundingClientRect();
    const role = roleOf(el);
    const name = nameOf(el).slice(0, 120);
    let p = 0;
    const reasons = [];
    if (orig.role) {
      if (role === orig.role) { p += 30; reasons.push(`same role (${role})`); } else if (role) p -= 10;
    }
    const sim = Math.max(similar(name, targetTxt), similar(el.getAttribute('placeholder'), targetTxt), similar(el.getAttribute('data-testid'), targetTxt),
      similar(el.id, targetTxt), similar(el.getAttribute('title'), targetTxt), similar(el.getAttribute('alt'), targetTxt));
    if (sim > 0) { p += Math.round(sim * 55); reasons.push(`similar text (${Math.round(sim * 100)} %)`); }
    if (cssHints) {
      if (cssHints.id && el.id && similar(el.id, cssHints.id) > 0.5) { p += 35; reasons.push(`similar id (#${el.id})`); }
      const cls = typeof el.className === 'string' ? el.className.split(/\s+/) : [];
      const common = cssHints.classes.filter((c) => cls.includes(c)).length;
      if (common) { p += 15 * common; reasons.push(`shares the class ${cssHints.classes.filter((c) => cls.includes(c)).join(', ')}`); }
    }
    if (r.width < 1 || r.height < 1) p -= 15;
    // Matching only on the role is not enough: it has to resemble it in something (text, id, class).
    if (targetTxt && sim === 0 && !(cssHints && reasons.length)) continue;
    if (p < 25) continue;
    el.setAttribute('data-k0-cand', String(output.length));
    output.push({ index: output.length, score: Math.min(100, p), reasons, tag: t, role, name, text: (el.innerText || '').trim().slice(0, 120),
      placeholder: el.getAttribute('placeholder'), testId: el.getAttribute('data-testid'), id: el.id || null, label: labelOf(el) || null,
      alt: el.getAttribute('alt'), visible: r.width > 0 && r.height > 0 });
  }
  return output.sort((a, b) => b.score - a.score).slice(0, 6);
}

// Screenshot of the saved DOM with the locator's elements marked (one or several), with context.
async function captureMarked(page, loc, file, color, rel) {
  const els = (await loc.all().catch(() => [])).slice(0, 8);
  const boxes = [];
  for (const el of els) {
    const c = await el.boundingBox().catch(() => null);
    if (!c) continue;
    boxes.push(c);
    await el.evaluate((x, col) => { x.style.outline = `3px solid ${col}`; x.style.outlineOffset = '2px'; }, color).catch(() => {});
  }
  if (!boxes.length) return undefined;
  const vp = page.viewportSize();
  const docHeight = await page.evaluate(() => document.documentElement.scrollHeight);
  const x0 = Math.max(0, Math.min(...boxes.map((c) => c.x)) - 140);
  const y0 = Math.max(0, Math.min(...boxes.map((c) => c.y)) - 100);
  const x1 = Math.min(vp.width, Math.max(...boxes.map((c) => c.x + c.width)) + 140);
  const y1 = Math.min(docHeight, Math.max(...boxes.map((c) => c.y + c.height)) + 100);
  await page.screenshot({ path: file, fullPage: true, clip: { x: x0, y: y0, width: Math.max(80, x1 - x0), height: Math.max(60, Math.min(1400, y1 - y0)) } }).catch(() => {});
  for (const el of els) await el.evaluate((x) => { x.style.outline = ''; }).catch(() => {});
  return fs.existsSync(file) ? rel(file) : undefined;
}

// In the browser: for each element marked with data-k0-match, the closest container that
// identifies it (a card or row with its own title) and the selector scoped to that container.
function _containers(orig) {
  const esc = (s) => String(s).replace(/"/g, '\\"');
  const output = [];
  const inner = orig.role ? `role=${orig.role}${orig.name && typeof orig.name === 'string' ? `[name="${esc(orig.name)}"]` : ''}`
    : orig.placeholder ? `[placeholder="${esc(orig.placeholder)}"]` : orig.text ? `text="${esc(orig.text)}"` : orig.css || null;
  if (!inner) return output;
  for (const el of document.querySelectorAll('[data-k0-match]')) {
    let a = el.parentElement;
    for (let level = 0; a && level < 6; level++, a = a.parentElement) {
      // [class*=nombre] kept so Spanish-language sites still match.
      const title = a.querySelector('h1,h2,h3,h4,h5,h6,strong,b,[class*=title],[class*=nombre],[class*=name]');
      const cls = (typeof a.className === 'string' ? a.className : '').trim().split(/\s+/).filter((c) => c && !/^(active|selected|open)$/.test(c))[0];
      if (!title || title.contains(el) || !cls) continue;
      const text = title.innerText.replace(/\s+/g, ' ').trim();
      if (!text || text.length > 60) continue;
      output.push({ index: el.getAttribute('data-k0-match'), reference: text,
        css: `${a.tagName.toLowerCase()}.${cls}:has(${title.tagName.toLowerCase()}:text-is("${esc(text)}")) >> ${inner}` });
      break;
    }
  }
  return output;
}

// Possible locators for a candidate, in k0lmena's order of preference.
function proposalsFor(c) {
  const p = [];
  const short = (s) => s && s.length <= 80;
  if (c.role && c.name && short(c.name)) p.push({ role: c.role, name: c.name }, { role: c.role, name: c.name, exact: true });
  if (c.label && short(c.label) && ['input', 'select', 'textarea'].includes(c.tag)) p.push({ label: c.label });
  if (c.placeholder) p.push({ placeholder: c.placeholder });
  if (c.testId) p.push({ testId: c.testId });
  if (c.text && short(c.text) && !['input', 'select', 'textarea'].includes(c.tag)) p.push({ text: c.text });
  if (c.id && !/^\d|[:\s]/.test(c.id)) p.push({ css: `#${c.id}` });
  return p;
}

async function analyzeFailure(browser, f, a, dirShots, rel, n) {
  const r = { id: `R-${String(n).padStart(2, '0')}`, scenario: f.scenario, feature: f.feature, uri: f.uri, line: f.line, story: f.story,
    case: f.case, step: f.step, error: (f.error || '').slice(0, 2500), url: f.url, analyst_category: f.analyst_category || null };
  // Gherkin keywords: English plus Spanish (Gherkin is multi-language).
  r.action = /^(Then|Entonces|Y entonces)\b/i.test(f.step || '') ? 'verification' : 'action';
  const loc = locatorFromError(f.error);
  if (!loc) {
    r.diagnosis = 'No locator in the error';
    r.detail = 'The error does not name a Playwright locator: it is not a locator failure (it may be a text assertion, a code, data or environment error). Review it with the failure-analyst.';
    return r;
  }
  r.locator = { type: loc.type, input: loc.input, text: loc.text, code: codeOf(loc.input) };
  r.location = locate(loc, f);
  if (!f.dom || !fs.existsSync(f.dom)) {
    r.diagnosis = 'No saved DOM';
    r.detail = 'There is no DOM of the failure (the run is older than this version of k0lmena or it was deleted). Run the scenario again with npm test and analyze again.';
    return r;
  }
  r.dom = rel(f.dom);
  const ctx = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  try {
    let html = fs.readFileSync(f.dom, 'utf8');
    const base = a.baseUrl || f.url;
    if (base && !/<base\s/i.test(html)) html = html.replace(/<head([^>]*)>/i, `<head$1><base href="${base}">`);
    await page.setContent(html, { waitUntil: 'load', timeout: 20000 }).catch(() => page.setContent(html, { waitUntil: 'domcontentloaded' }));
    const original = locatorOf(page, loc.input);
    const howMany = await original.count();
    const visibles = howMany ? (await Promise.all((await original.all()).map((x) => x.isVisible()))).filter(Boolean).length : 0;
    r.matches = howMany;
    if (howMany === 0) {
      r.diagnosis = 'No longer exists';
      r.detail = `${loc.text} does not find any element on the saved page: the text, the role or the attribute changed (or the element is gone).`;
    } else if (howMany > 1) {
      r.diagnosis = 'Matches several';
      r.detail = `${loc.text} finds ${howMany} elements: Playwright does not know which one to use (strict mode). It has to be made more specific.`;
    } else if (!visibles) {
      r.diagnosis = 'Exists but not visible';
      r.detail = `${loc.text} finds the element, but it is hidden: it may need a menu or tab to be opened first, a scroll, or the application does not show it (possible bug).`;
    } else {
      r.diagnosis = 'Exists and visible';
      r.detail = `${loc.text} finds a single visible element on the saved page: the locator is fine and the wait failed (the element took longer than the timeout) or the verification did (text, state).`;
    }
    // Several: first the exact match of the same name; if that is not enough, the locator inside the
    // container of each element (the card or row that identifies it by its title).
    if (howMany > 1) {
      if ('role' in loc.input && !loc.input.exact) {
        const v = { ...loc.input, exact: true };
        if ((await locatorOf(page, v).count().catch(() => 0)) === 1) {
          r.proposal = { input: v, code: codeOf(v), confidence: 'High', score: 100,
            reasons: ['with exact: true it finds a single element (the full name matches; the others only contain it)'] };
        }
      }
      if (!r.proposal) {
        await original.evaluateAll((els) => els.forEach((el, i) => el.setAttribute('data-k0-match', String(i))));
        const scopes = await page.evaluate(_containers, loc.input);
        r.alternatives = [];
        for (const s of scopes) {
          const n2 = await page.locator(s.css).count().catch(() => 0);
          if (n2 === 1) r.alternatives.push({ input: { css: s.css }, code: codeOf({ css: s.css }), reference: s.reference, index: s.index });
        }
        if (r.alternatives.length) {
          const pri = r.alternatives[0];
          r.proposal = { input: pri.input, code: pri.code, confidence: 'Medium', score: 60, candidate_match: pri.index,
            reasons: [`scoped to the container of “${pri.reference}” (the first of the ${howMany}); there are ${r.alternatives.length} alternative(s): pick the one that matches the case`] };
          r.detail += ` I propose scoping it to the container of each one (for example, the one of “${pri.reference}”).`;
        }
      }
      if (r.proposal) {
        const el = r.proposal.candidate_match != null ? page.locator(`[data-k0-match="${r.proposal.candidate_match}"]`) : locatorOf(page, r.proposal.input);
        r.screenshot = await captureMarked(page, el.first(), path.join(dirShots, `${r.id}-proposal.png`), '#F9B006', rel);
      }
    }
    // Candidates: if it does not exist. If it exists and is visible, the fix is about the wait, not the locator.
    if (howMany === 0) {
      const cands = await page.evaluate(_candidatesInPage, loc.input);
      for (const c of cands) {
        c.proposals = [];
        for (const p of proposalsFor(c)) {
          const n2 = await locatorOf(page, p).count().catch(() => 0);
          c.proposals.push({ input: p, code: codeOf(p), matches: n2 });
        }
        c.best = c.proposals.find((p) => p.matches === 1) || null;
      }
      r.candidates = cands;
      const eligible = cands.filter((c) => c.best);
      const top = eligible[0];
      if (top) {
        const second = eligible[1];
        let confidence = top.score >= 70 && (!second || second.score <= top.score - 15) ? 'High' : top.score >= 45 ? 'Medium' : 'Low';
        if (r.action === 'verification' && confidence === 'High') confidence = 'Medium';
        r.proposal = { input: top.best.input, code: top.best.code, candidate: top.index, confidence, score: top.score, reasons: top.reasons };
        // Screenshot of the DOM with the proposed element marked.
        r.screenshot = await captureMarked(page, page.locator(`[data-k0-cand="${top.index}"]`).first(), path.join(dirShots, `${r.id}-proposal.png`), '#F9B006', rel);
      } else {
        r.detail += ' I did not find a similar element that can be located uniquely: review it by hand with Playwright MCP.';
      }
    } else if (howMany === 1 && visibles) {
      r.wait_suggestion = 'Wait for the page to finish loading before the step (page.waitForLoadState) or raise the timeout of that helper; if the element appears after an action, wait for that response.';
    }
    if (howMany >= 1) {
      // Screenshot of what the original locator finds (all of them, if several) to compare.
      r.original_screenshot = await captureMarked(page, original, path.join(dirShots, `${r.id}-original.png`), '#ff2d2d', rel);
    }
    // What comes from a verification step (Then) may be an application bug.
    if (r.action === 'verification' && r.diagnosis === 'No longer exists') {
      r.risk = 'The failing step is a verification: if the element was supposed to be there (according to the case or the story), it is an application bug and the test should not be changed.';
    }
    if (r.location && r.location.type === 'feature') {
      r.risk = (r.risk ? `${r.risk} ` : '') + 'The value comes from the .feature (it is case data): changing it changes what the case expects; confirm it with the story.';
    }
  } finally {
    await ctx.close();
  }
  r.status = r.proposal ? 'Proposed' : 'No proposal';
  return r;
}

// ------------------------------------------------------------------ apply and verify
function replaceInLine(line, r) {
  const u = r.location;
  if (u.type === 'feature') {
    const fresh = r.proposal.input.name ?? r.proposal.input.text ?? r.proposal.input.label ?? r.proposal.input.placeholder ?? r.proposal.input.testId;
    return fresh == null ? null : line.replace(`"${u.value}"`, `"${fresh}"`);
  }
  // The object literal that contains the original input: { role: 'x', name: 'y' }
  const m = line.match(/\{[^{}]*\}/g);
  const target = (m || []).find((o) => Object.values(r.locator.input).every((v) => typeof v !== 'string' || o.includes(v)));
  if (!target) return null;
  return line.replace(target, r.proposal.code);
}

function apply(folder, data, which) {
  const ids = which === 'safe'
    ? data.repairs.filter((r) => r.proposal && r.proposal.confidence === 'High' && r.action === 'action' && r.location && r.location.type === 'locator').map((r) => r.id)
    : which.split(',').map((x) => x.trim().toUpperCase());
  const dirBackup = path.join(folder, 'backup');
  const diffs = fs.existsSync(path.join(folder, 'changes.diff')) ? [fs.readFileSync(path.join(folder, 'changes.diff'), 'utf8')] : [];
  let n = 0;
  for (const id of ids) {
    const r = data.repairs.find((x) => x.id === id);
    if (!r) { console.log(`  ${id}: does not exist`); continue; }
    if (!r.proposal || !r.location) { console.log(`  ${id}: has no proposal or I do not know which file it is in`); continue; }
    if (r.applied) { console.log(`  ${id}: was already applied`); continue; }
    if (r.location.type === 'step') { console.log(`  ${id}: the locator is written in a step: change it by hand (${r.location.file}:${r.location.line})`); continue; }
    const abs = path.join(ROOT, r.location.file);
    const text = fs.readFileSync(abs, 'utf8');
    const eol = text.includes('\r\n') ? '\r\n' : '\n';
    const lines = text.split(/\r?\n/);
    const i = r.location.line - 1;
    const replaced = replaceInLine(lines[i], r);
    if (!replaced || replaced === lines[i]) { console.log(`  ${id}: could not replace it automatically in ${r.location.file}:${r.location.line}`); continue; }
    const backup = path.join(dirBackup, r.location.file);
    if (!fs.existsSync(backup)) { fs.mkdirSync(path.dirname(backup), { recursive: true }); fs.writeFileSync(backup, text); }
    const before = lines[i];
    lines[i] = replaced;
    fs.writeFileSync(abs, lines.join(eol));
    const ctxStart = Math.max(0, i - 2);
    const ctxEnd = Math.min(lines.length, i + 3);
    const hunk = [`--- a/${r.location.file}`, `+++ b/${r.location.file}`, `@@ -${ctxStart + 1},${ctxEnd - ctxStart} +${ctxStart + 1},${ctxEnd - ctxStart} @@ ${r.id}`];
    for (let k = ctxStart; k < ctxEnd; k++) {
      if (k === i) { hunk.push(`-${before}`, `+${replaced}`); } else hunk.push(` ${lines[k]}`);
    }
    diffs.push(hunk.join('\n'));
    r.applied = { date: new Date().toISOString(), before: before.trim(), after: replaced.trim() };
    r.status = 'Applied';
    n++;
    console.log(`  ${id}: applied in ${r.location.file}:${r.location.line}`);
  }
  fs.writeFileSync(path.join(folder, 'changes.diff'), diffs.filter(Boolean).join('\n\n') + '\n');
  console.log(`${n} repair(s) applied. Copy of the original files in backup/.`);
}

function verify(folder, data) {
  const applied = data.repairs.filter((r) => r.applied);
  if (!applied.length) { console.log('There are no applied repairs to verify.'); return; }
  const tags = [...new Set(applied.map((r) => (r.story && r.case ? `(@${r.story} and @${r.case})` : r.case ? `@${r.case}` : null)).filter(Boolean))];
  if (!tags.length) { console.log('The repaired scenarios have no @US/@TC: run the full suite (npm test) to verify them.'); return; }
  const dir = path.join(folder, 'verification');
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
  const filter = tags.join(' or ');
  console.log(`Verifying ${applied.length} repair(s): TAGS="${filter}"`);
  const r = spawnSync('npx cucumber-js --profile web', { cwd: K0, shell: true, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024,
    env: { ...process.env, TAGS: filter, REPORT_DIR: dir, EVIDENCE: 'screenshot', HEADLESS: 'true', BROWSER: process.env.BROWSER || 'chromium' } });
  const { readCucumber } = require('../cross-browser/cross-browser.js');
  const scenarios = readCucumber(path.join(dir, 'cucumber-report.json'));
  for (const rep of applied) {
    const e = scenarios.find((x) => x.uri.split(path.sep).join('/') === rep.uri && x.line === rep.line) ||
      scenarios.find((x) => x.case === rep.case && x.story === rep.story);
    if (!e) { rep.verification = { status: 'No result', date: new Date().toISOString(), detail: (r.stderr || r.stdout || '').trim().split(/\r?\n/).slice(-3).join(' ') }; continue; }
    rep.verification = { status: e.status === 'Passed' ? 'Verified' : 'Still failing', date: new Date().toISOString(), step: e.step, error: (e.error || '').slice(0, 1500) };
    rep.status = rep.verification.status;
    console.log(`  ${rep.id}: ${rep.verification.status}`);
  }
  data.verification = { tags: filter, date: new Date().toISOString(), report: fs.existsSync(path.join(dir, 'front-report.html')) ? 'verification/front-report.html' : null };
}

function summarize(data) {
  const rs = data.repairs;
  const c = (f) => rs.filter(f).length;
  return { failures: rs.length, locator_failures: c((r) => r.locator), with_proposal: c((r) => r.proposal), high_confidence: c((r) => r.proposal && r.proposal.confidence === 'High'),
    applied: c((r) => r.applied), verified: c((r) => r.verification && r.verification.status === 'Verified'),
    still_failing: c((r) => r.verification && r.verification.status === 'Still failing'), no_proposal: c((r) => !r.proposal),
    possible_bugs: c((r) => r.risk && r.action === 'verification'), wait: c((r) => r.diagnosis === 'Exists and visible'),
    by_diagnosis: rs.reduce((acc, r) => { acc[r.diagnosis] = (acc[r.diagnosis] || 0) + 1; return acc; }, {}) };
}

function generateReport(folder) {
  const py = process.platform === 'win32' ? 'python' : 'python3';
  const args = [path.join(ROOT, 'scripts', 'generate_repair_report.py'), path.join(folder, 'repairs.json'), path.join(folder, 'repair-report.html')];
  if (fs.existsSync(path.join(folder, 'analysis.json'))) args.push('--analysis', path.join(folder, 'analysis.json'));
  const r = spawnSync(py, args, { encoding: 'utf8' });
  if (r.status !== 0) {
    const reason = (r.stderr || r.error || '').toString().trim().split(/\r?\n/).pop();
    console.log(`Could not generate the HTML report (${reason}). Generate it with: python scripts/generate_repair_report.py <folder>/repairs.json <folder>/repair-report.html`);
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
  const folder = a.output ? fromCwd(a.output) : path.join(ROOT, 'output', 'repairs', a.story || 'suite');
  const dataFile = path.join(folder, 'repairs.json');
  const relRoot = (p) => path.relative(ROOT, p).split(path.sep).join('/');
  const save = (d) => { d.summary = summarize(d); fs.writeFileSync(dataFile, JSON.stringify(d, null, 2), 'utf8'); };

  if (a.apply || a.verify || a.reportOnly) {
    if (!fs.existsSync(dataFile)) throw new Error(`There is no analysis in ${relRoot(folder)}: run npm run repair without options first.`);
    const data = JSON.parse(fs.readFileSync(dataFile, 'utf8'));
    if (a.apply) apply(folder, data, a.apply);
    if (a.verify) verify(folder, data);
    save(data);
    if (generateReport(folder)) console.log(`Report: ${relRoot(path.join(folder, 'repair-report.html'))}`);
    return;
  }

  const source = a.failures ? fromCwd(a.failures) : (a.report ? fromCwd(a.report) : path.resolve(K0, (process.env.REPORT_DIR || '').trim() || 'reports/web', 'cucumber-report.json')); // the same REPORT_DIR as npm test
  if (!fs.existsSync(source)) throw new Error(`Could not find ${source}. Run npm test first (or pass --report / --failures).`);
  const failures = a.failures ? analystFailures(source, a.story) : reportFailures(source, a.story);
  archive(folder, GENERATED, 'repairs.json'); // the previous run moves to history/ (last 5)
  for (const n of GENERATED) fs.rmSync(path.join(folder, n), { recursive: true, force: true });
  const dirShots = path.join(folder, 'screenshots');
  fs.mkdirSync(dirShots, { recursive: true });
  const rel = (p) => path.relative(folder, p).split(path.sep).join('/');
  console.log(`Repairer · ${failures.length} web scenario(s) with failures${a.story ? ` of ${a.story}` : ''} · source: ${relRoot(source)}`);
  const { chromium } = require('playwright');
  const browser = await chromium.launch();
  const repairs = [];
  for (const [i, f] of failures.entries()) {
    process.stdout.write(`[${i + 1}/${failures.length}] ${f.case || ''} ${f.scenario} `);
    const r = await analyzeFailure(browser, f, a, dirShots, rel, i + 1);
    console.log(`→ ${r.diagnosis}${r.proposal ? ` · proposal ${r.proposal.code} (confidence ${r.proposal.confidence})` : ''}`);
    repairs.push(r);
  }
  await browser.close();
  const data = { story: a.story || null, date: new Date().toISOString(), source: relRoot(source), source_type: a.failures ? 'failure-analyst' : 'npm test',
    tool: `Playwright ${require('playwright/package.json').version}`, repairs };
  save(data);
  const r = data.summary;
  console.log(`\nFailures: ${r.failures} · locator: ${r.locator_failures} · with proposal: ${r.with_proposal} (high confidence: ${r.high_confidence}) · wait: ${r.wait} · no proposal: ${r.no_proposal}`);
  console.log(`Data: ${relRoot(dataFile)}`);
  if (generateReport(folder)) console.log(`Report: ${relRoot(path.join(folder, 'repair-report.html'))}`);
}

if (require.main === module) {
  main().catch((e) => { console.error(`Error: ${e.message}`); process.exit(1); });
}

module.exports = { parseArgs, locatorFromError, codeOf, proposalsFor, replaceInLine, reportFailures, GENERATED };
