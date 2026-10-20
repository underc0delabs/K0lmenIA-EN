// Form validation testing (form-tester agent).
//
// Usage (from the repo root):
//   npm run forms -- [--url https://my-app.com/signup] [--pages url1,url2] [--max-pages 6]
//                          [--depth 1] [--story US-001] [--submit-empty] [--headed]
//
// It finds the forms on the pages and, field by field, tests their validations WITHOUT SUBMITTING anything:
// it fills in a value, leaves the field and checks whether the field rejects it (browser validation, aria-invalid or
// an application error message) and which message it shows. Tests by field:
//   required empty and only spaces · maximum length (and whether it has one) · minimum length · email with invalid
//   formats and a valid one · number with letters, out of range and at the limits · phone and URL with text ·
//   pattern · names with accents, ñ and apostrophe (they must be accepted) · required list and checkbox.
// It also reviews: field label, visual indication of required, field type (email as text),
// autocomplete on name, email and phone, visible password rules.
// With --submit-empty (only with confirmation: if the form does not validate, it IS SUBMITTED) it presses the
// submit button with everything empty and captures which messages it shows.
//
// It leaves everything in output/forms/<US or host>/ (forms.json, forms-report.html, screenshots/); the
// previous run moves to history/ (the last 5 are kept).
const fs = require('fs');
const path = require('path');
const { normalize, slug, stamp, load } = require('../explorer/explore.js');
const { discover } = require('../pixel-perfect/pixel-perfect.js');
const visual = require('../visual/compare.js');
const { archive } = require('../history/history.js');

const ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const fromCwd = (p) => path.resolve(process.env.INIT_CWD || process.cwd(), p);
const GENERATED = ['forms.json', 'analysis.json', 'forms-report.html', 'screenshots'];
const SEV_ORDER = { 'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3 };

function parseArgs(argv) {
  const a = { maxPages: 6, depth: 1, headed: false, submitEmpty: false };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    const v = () => argv[++i];
    if (k === '--url') a.url = v();
    else if (k === '--pages') a.pages = v().split(',').map((x) => x.trim()).filter(Boolean);
    else if (k === '--max-pages') a.maxPages = parseInt(v(), 10);
    else if (k === '--depth') a.depth = parseInt(v(), 10);
    else if (k === '--story') a.story = v();
    else if (k === '--submit-empty') a.submitEmpty = true;
    else if (k === '--output') a.output = v();
    else if (k === '--headed') a.headed = true;
    else if (k === '-h' || k === '--help') a.help = true;
    else throw new Error(`Unknown option: ${k}`);
  }
  if (a.story && !/^[A-Za-z]+-\d+$/.test(a.story)) throw new Error('--story must be an ID like US-001.');
  return a;
}

// In the page: forms and their fields (marks each field with data-k0-field to find it later).
function _forms() {
  const visible = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const labelOf = (c) => {
    const lab = (c.id && document.querySelector(`label[for="${CSS.escape(c.id)}"]`)) || c.closest('label');
    if (lab) return { text: lab.innerText.replace(/\s+/g, ' ').trim(), source: 'label' };
    if (c.getAttribute('aria-label')) return { text: c.getAttribute('aria-label'), source: 'aria-label' };
    const ids = (c.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean);
    if (ids.length) return { text: ids.map((i) => (document.getElementById(i) || {}).innerText || '').join(' ').trim(), source: 'aria-labelledby' };
    if (c.getAttribute('placeholder')) return { text: c.getAttribute('placeholder'), source: 'placeholder' };
    return { text: '', source: null };
  };
  const SEL = 'input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=reset]):not([type=image]):not([type=file]), textarea, select';
  let groups = [...document.querySelectorAll('form')].filter(visible).map((f) => ({ el: f, fields: [...f.querySelectorAll(SEL)].filter(visible) }));
  const loose = [...document.querySelectorAll(SEL)].filter((c) => visible(c) && !c.closest('form'));
  if (loose.length >= 2) groups.push({ el: null, fields: loose });
  groups = groups.filter((g) => g.fields.length);
  let n = 0;
  return groups.map((g, i) => {
    const fields = g.fields.map((c) => {
      n++;
      c.setAttribute('data-k0-field', String(n));
      const lb = labelOf(c);
      const type = c.tagName === 'SELECT' ? 'select' : c.tagName === 'TEXTAREA' ? 'textarea' : (c.getAttribute('type') || 'text').toLowerCase();
      const req = c.required || c.getAttribute('aria-required') === 'true';
      const mark = /\*|required|mandatory|obligatori|requerid/i.test(lb.text + ' ' + (c.getAttribute('placeholder') || ''));
      const num = (x) => (c.getAttribute(x) != null && c.getAttribute(x) !== '' ? Number(c.getAttribute(x)) : null);
      const near = (c.closest('div, fieldset, p, li') || c.parentElement || document.body).innerText || '';
      return { n, name: c.name || c.id || lb.text || `field ${n}`, label: lb.text, label_source: lb.source, type, required: req, required_mark: mark,
        maxlength: c.maxLength > 0 ? c.maxLength : null, minlength: c.minLength > 0 ? c.minLength : null, min: num('min'), max: num('max'), step: num('step'),
        pattern: c.getAttribute('pattern'), autocomplete: c.getAttribute('autocomplete'), inputmode: c.getAttribute('inputmode'),
        placeholder: c.getAttribute('placeholder'), options: c.tagName === 'SELECT' ? [...c.options].map((o) => ({ value: o.value, text: o.text.trim() })) : null,
        visible_rules: /\d+\s*(characters|digits|caracteres|dígitos)|uppercase|upper-case|capital letter|number|symbol|special character|mayúscula|número|símbolo/i.test(near) };
    });
    const f = g.el;
    const button = f ? f.querySelector('button[type=submit], input[type=submit], button:not([type])') : null;
    return { index: i, name: (f && (f.getAttribute('name') || f.id || f.getAttribute('aria-label'))) || (f ? `form ${i + 1}` : 'fields without a form'),
      action: f ? f.getAttribute('action') : null, method: f ? (f.getAttribute('method') || 'get').toUpperCase() : null, fields, button: Boolean(button) };
  });
}

// Submit button of THAT form (not the first one on the page): it is located from its first field, which
// _forms marks with data-k0-field (the numbering is the same when the page is reloaded).
function submitButton(page, f) {
  return page.locator(`[data-k0-field="${f.fields[0].n}"]`).locator('xpath=ancestor::form[1]')
    .locator('button[type=submit], input[type=submit], button:not([type])').first();
}

// Tests that apply to a field: [{rule, value, expected: 'rejects'|'accepts'}].
function testsFor(c) {
  const p = [];
  const hint = `${c.name} ${c.label} ${c.placeholder || ''} ${c.autocomplete || ''}`.toLowerCase();
  const isEmail = c.type === 'email' || /e-?mail|correo/.test(hint);
  const isTel = c.type === 'tel' || /phone|mobile|cell|whatsapp|tel[eé]fono|celular/.test(hint);
  const isName = /name|surname|nombre|apellido/.test(hint) && !isEmail;
  const text = ['text', 'search', 'textarea', 'password', 'tel', 'url', 'email'].includes(c.type);
  if (c.type === 'checkbox' || c.type === 'radio') {
    if (c.required) p.push({ rule: 'Required not checked', value: null, action: 'uncheck', expected: 'rejects' });
    return p;
  }
  if (c.type === 'select') {
    if (c.required && c.options && c.options.some((o) => o.value === '')) p.push({ rule: 'Required not selected', value: '', action: 'select', expected: 'rejects' });
    return p;
  }
  if (c.required) p.push({ rule: 'Required empty', value: '', expected: 'rejects' });
  if (c.required && text) p.push({ rule: 'Only spaces', value: '   ', expected: 'rejects' });
  if (text && c.maxlength) p.push({ rule: `More than ${c.maxlength} characters`, value: 'a'.repeat(c.maxlength + 1), expected: 'truncates' });
  if (c.minlength) p.push({ rule: `Fewer than ${c.minlength} characters`, value: 'a'.repeat(Math.max(1, c.minlength - 1)), expected: 'rejects' });
  if (isEmail) {
    p.push({ rule: 'Email without @', value: 'ana.test.com', expected: 'rejects' });
    p.push({ rule: 'Email without domain', value: 'ana@', expected: 'rejects' });
    p.push({ rule: 'Valid email', value: 'ana@test.com', expected: 'accepts' });
  }
  if (c.type === 'number' || c.type === 'range') {
    if (c.min != null) { p.push({ rule: `Below the minimum (${c.min})`, value: String(c.min - 1), expected: 'rejects' }); p.push({ rule: `At the minimum (${c.min})`, value: String(c.min), expected: 'accepts' }); }
    if (c.max != null) { p.push({ rule: `Above the maximum (${c.max})`, value: String(c.max + 1), expected: 'rejects' }); p.push({ rule: `At the maximum (${c.max})`, value: String(c.max), expected: 'accepts' }); }
    if (!c.step || Number.isInteger(c.step)) p.push({ rule: 'With decimals', value: '1.5', expected: c.step ? 'rejects' : 'reports' });
  }
  if (isTel && c.type !== 'number') p.push({ rule: 'Phone with letters', value: 'abc-defg', expected: 'rejects' });
  if (c.type === 'url') p.push({ rule: 'Invalid URL', value: 'not a url', expected: 'rejects' });
  if (c.pattern) p.push({ rule: `Does not match the pattern (${c.pattern.slice(0, 30)})`, value: '¿?', expected: 'rejects' });
  if (isName && text) p.push({ rule: 'Name with accents, ñ and apostrophe', value: "José Ñandú O'Brien", expected: 'accepts' });
  if (text && !c.maxlength && ['text', 'textarea'].includes(c.type)) p.push({ rule: 'Very long text (300 characters)', value: 'a'.repeat(300), expected: 'reports' });
  return p;
}

// Tests a value: fills it in, leaves the field and checks whether it is rejected and which message appears.
async function runTest(page, c, test) {
  const sel = `[data-k0-field="${c.n}"]`;
  const field = page.locator(sel).first();
  const before = await page.evaluate(() => [...document.querySelectorAll('[role=alert], [class*=error i], [class*=invalid i], [class*=feedback i], [aria-live]')]
    .map((x) => (x.innerText || '').trim()).join('|'));
  if (test.action === 'uncheck') await field.uncheck({ timeout: 3000 }).catch(() => {});
  else if (test.action === 'select') await field.selectOption(test.value, { timeout: 3000 }).catch(() => {});
  else {
    await field.fill('', { timeout: 3000 }).catch(() => {});
    if (test.value) await field.pressSequentially(test.value.length > 60 ? test.value.slice(0, 1) : test.value, { timeout: 8000 }).catch(() => {});
    if (test.value && test.value.length > 60) await field.fill(test.value, { timeout: 3000 }).catch(() => {});
  }
  await field.press('Tab', { timeout: 3000 }).catch(() => field.evaluate((e) => e.blur()));
  await page.waitForTimeout(250);
  const r = await page.evaluate(({ s, before }) => {
    const el = document.querySelector(s);
    const now = [...document.querySelectorAll('[role=alert], [class*=error i], [class*=invalid i], [class*=feedback i], [aria-live]')]
      .filter((x) => { const b = x.getBoundingClientRect(); return b.width > 0 && b.height > 0; }).map((x) => (x.innerText || '').trim()).filter(Boolean);
    const fresh = now.filter((t) => !before.split('|').includes(t));
    // The app message that belongs to THIS field: the one it references (aria-describedby / aria-errormessage) or the
    // one right after it; otherwise, one that just appeared (not the one another field left).
    const vis = (x) => { const b = x.getBoundingClientRect(); return b.width > 0 && b.height > 0 && (x.innerText || '').trim(); };
    let own = '';
    for (const at of ['aria-errormessage', 'aria-describedby']) {
      for (const id of (el.getAttribute(at) || '').split(/\s+/).filter(Boolean)) {
        const x = document.getElementById(id);
        if (x && vis(x) && !own) own = x.innerText.trim();
      }
    }
    for (let s = el.nextElementSibling, k = 0; s && k < 2 && !own; s = s.nextElementSibling, k++) {
      if (/^(LABEL|INPUT|SELECT|TEXTAREA|BUTTON)$/.test(s.tagName)) break;
      if (vis(s) && /error|invalid|feedback|help|alert/i.test(`${s.className} ${s.getAttribute('role') || ''}`)) own = s.innerText.trim();
    }
    const valid = typeof el.checkValidity === 'function' ? el.checkValidity() : true;
    return { valid, browser_message: el.validationMessage || '', aria_invalid: el.getAttribute('aria-invalid') === 'true',
      app_message: own || fresh[0] || '', final_value: el.type === 'checkbox' ? String(el.checked) : String(el.value) };
  }, { s: sel, before });
  const rejects = !r.valid || r.aria_invalid || Boolean(r.app_message && /required|mandatory|invalid|not valid|error|must|please (enter|provide|fill|select)|enter a|format|minimum|maximum|at least|at most|cannot|can't|obligatori|requerid|inv[aá]lid|debe|ingres[aá]|complet[aá]|formato|m[ií]nimo|m[aá]ximo|no (es|puede)/i.test(r.app_message));
  let result = rejects ? 'rejects' : 'accepts';
  if (test.expected === 'truncates' && r.final_value.length <= (c.maxlength || 0)) result = 'truncates';
  const ok = test.expected === 'reports' ? null : test.expected === 'truncates' ? result === 'truncates' || result === 'rejects' : result === test.expected;
  return { rule: test.rule, value: test.value == null ? '(not checked)' : test.value.length > 40 ? `${test.value.slice(0, 20)}… (${test.value.length})` : test.value,
    expected: test.expected, result, ok, message: r.app_message || r.browser_message || '', source: r.app_message ? 'application' : r.browser_message ? 'browser' : null };
}

function findingsOf(f, c) {
  const h = [];
  const add = (severity, type, title, detail) => h.push({ severity, type, title, detail, form: f.id, field: c ? c.name : null });
  if (!c) return h;
  const name = c.label || c.name;
  if (!c.label_source) add('Medium', 'Label', `“${name}” has no label`, 'Without a label, the screen reader does not know which field it is, and neither does the person filling it in.');
  else if (c.label_source === 'placeholder') add('Low', 'Label', `“${name}” uses the placeholder as its label`, 'It disappears when typing: use a visible label.');
  if (c.required && !c.required_mark) add('Medium', 'Required', `“${name}” is required and does not say so`, 'Mark the required fields (an asterisk with its explanation, or "required").');
  const hint = `${c.name} ${c.label} ${c.placeholder || ''}`.toLowerCase();
  if (c.type === 'text' && /e-?mail|correo/.test(hint)) add('Medium', 'Field type', `“${name}” asks for an email but is a text field`, 'With type="email" the phone shows the keyboard with @ and the browser validates the format.');
  if (['text', 'email', 'tel'].includes(c.type) && /name|e-?mail|phone|mobile|address|nombre|correo|tel[eé]fono|celular|direcci[oó]n/.test(hint) && !c.autocomplete) {
    add('Low', 'Autocomplete', `“${name}” has no autocomplete`, 'With autocomplete (name, email, tel, street-address) the browser fills it in automatically.');
  }
  if (c.type === 'password' && !c.minlength && !c.visible_rules) add('Low', 'Password', 'The password does not show its rules', 'Say before typing how many characters it needs and what it must contain.');
  for (const p of c.tests) {
    if (p.ok === false && p.expected === 'rejects') {
      const serious = /Required|Email/.test(p.rule);
      add(serious ? 'High' : 'Medium', 'Accepts an invalid value', `“${name}” accepts: ${p.rule}`, `Tested value: “${p.value}”. It should reject it with a clear message.`);
    } else if (p.ok === false && p.expected === 'accepts') {
      add('High', 'Rejects a valid value', `“${name}” rejects: ${p.rule}`, `Tested value: “${p.value}”${p.message ? `; message: “${p.message}”` : ''}. It prevents real people from completing the form.`);
    } else if (p.ok === false && p.expected === 'truncates') {
      add('Medium', 'Maximum length', `“${name}” allows typing more than ${c.maxlength} characters`, 'The maximum length is not enforced.');
    } else if (p.ok && p.expected === 'rejects' && p.source === 'browser') {
      add('Low', 'Error message', `“${name}”: the message for “${p.rule}” comes from the browser`, `Message: “${p.message}”. It is generic and shows in the browser's language: show your own next to the field.`);
    }
    if (p.rule.startsWith('Very long text') && p.result === 'accepts') add('Low', 'Maximum length', `“${name}” has no maximum length`, 'It accepts 300 characters or more: set a maximum that matches what the database stores.');
  }
  return h;
}

function generateReport(folder) {
  const py = process.platform === 'win32' ? 'python' : 'python3';
  const r = require('child_process').spawnSync(py, [path.join(ROOT, 'scripts', 'generate_forms_report.py'), path.join(folder, 'forms.json'),
    path.join(folder, 'forms-report.html')], { encoding: 'utf8' });
  if (r.status !== 0) {
    const reason = (r.stderr || r.error || '').toString().trim().split(/\r?\n/).pop();
    console.log(`Could not generate the HTML report (${reason}). Generate it with: python scripts/generate_forms_report.py <folder>/forms.json <folder>/forms-report.html`);
    return false;
  }
  return true;
}

async function formScreenshot(page, f, file) {
  const boxes = [];
  for (const c of f.fields) {
    const b = await page.locator(`[data-k0-field="${c.n}"]`).first().boundingBox().catch(() => null);
    if (b) boxes.push({ x: b.x, y: b.y, w: b.width, h: b.height });
  }
  if (!boxes.length) return false;
  const vp = page.viewportSize();
  const height = await page.evaluate(() => document.documentElement.scrollHeight);
  const v = visual.windowOf(boxes, 90, 360, 200);
  await page.screenshot({ path: file, fullPage: true, clip: { x: v.x, y: v.y, width: Math.min(v.w, vp.width - v.x), height: Math.min(v.h, height - v.y, 2400) } }).catch(() => {});
  return fs.existsSync(file);
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
  const folder = a.output ? fromCwd(a.output) : path.join(ROOT, 'output', 'forms', a.story || host);
  archive(folder, GENERATED, 'forms.json');
  for (const n of GENERATED) fs.rmSync(path.join(folder, n), { recursive: true, force: true });
  const shotsDir = path.join(folder, 'screenshots');
  fs.mkdirSync(shotsDir, { recursive: true });
  const rel = (p) => path.relative(folder, p).split(path.sep).join('/');
  const relRoot = (p) => path.relative(ROOT, p).split(path.sep).join('/');
  const { chromium } = require('playwright');
  const browser = await chromium.launch({ headless: !a.headed });
  const t0 = Date.now();
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, locale: process.env.LOCALE || 'en-US' });
  const page = await ctx.newPage();
  // Nothing is ever submitted (except --submit-empty): any navigation caused by a submit is aborted.
  let submit = false;
  await page.route('**/*', (route) => {
    const rq = route.request();
    if (!submit && rq.isNavigationRequest() && rq.method() !== 'GET') return route.abort();
    return route.continue();
  });
  const pages = await discover(page, start, a);
  console.log(`Forms: ${pages.length} page(s) · output ${relRoot(folder)}`);
  const forms = [];
  let findings = [];
  for (const [i, u] of pages.entries()) {
    await load(page, u).catch(() => {});
    const fs0 = await page.evaluate(_forms).catch(() => []);
    process.stdout.write(`[${i + 1}/${pages.length}] ${u} → ${fs0.length} form(s)\n`);
    for (const f of fs0) {
      f.id = `F-${String(forms.length + 1).padStart(2, '0')}`;
      f.url = u;
      f.page = `${String(i + 1).padStart(2, '0')}-${slug(u)}`;
      const before = path.join(shotsDir, `${f.id}-before.png`);
      if (await formScreenshot(page, f, before)) f.screenshot = rel(before);
      for (const c of f.fields) {
        c.tests = [];
        for (const pr of testsFor(c)) c.tests.push(await runTest(page, c, pr));
        process.stdout.write(`    ${String(c.label || c.name).slice(0, 30).padEnd(30)} ${c.type.padEnd(9)} ${c.tests.filter((p) => p.ok === false).length}/${c.tests.length} failing\n`);
      }
      // State with errors: each field with its first invalid value, to see all the messages together.
      for (const c of f.fields) {
        const inval = testsFor(c).find((p) => p.expected === 'rejects');
        if (inval) await runTest(page, c, inval).catch(() => {});
      }
      const errors = path.join(shotsDir, `${f.id}-errors.png`);
      if (await formScreenshot(page, f, errors)) f.errors_screenshot = rel(errors);
      if (a.submitEmpty && f.button) {
        await load(page, u).catch(() => {});
        await page.evaluate(_forms).catch(() => []);
        submit = true;
        await submitButton(page, f).click({ timeout: 5000 }).catch(() => {});
        await page.waitForTimeout(1200);
        submit = false;
        const env = path.join(shotsDir, `${f.id}-empty-submit.png`);
        await page.screenshot({ path: env, fullPage: true }).catch(() => {});
        if (fs.existsSync(env)) f.empty_submit_screenshot = rel(env);
        f.url_after_submit = page.url();
      }
      f.findings = f.fields.flatMap((c) => findingsOf(f, c));
      if (!f.button && f.name !== 'fields without a form') f.findings.push({ severity: 'Low', type: 'Submit', title: 'The form has no submit button', detail: 'Without a button, it is not clear how it is submitted (not even with Enter).', form: f.id, field: null });
      findings.push(...f.findings.map((h) => ({ ...h, url: u, screenshot: f.errors_screenshot || f.screenshot })));
      forms.push(f);
      await load(page, u).catch(() => {});
      await page.evaluate(_forms).catch(() => []);
    }
  }
  await browser.close();
  findings.sort((x, y) => SEV_ORDER[x.severity] - SEV_ORDER[y.severity]);
  findings.forEach((h, i) => { h.id = `V-${String(i + 1).padStart(2, '0')}`; });
  const tests = forms.flatMap((f) => f.fields.flatMap((c) => c.tests));
  const result = {
    url: start, host, story: a.story || null, date: new Date().toISOString(), stamp: stamp(), duration_s: Math.round((Date.now() - t0) / 1000),
    tool: `Playwright ${require('playwright/package.json').version}`, empty_submit: a.submitEmpty,
    summary: { pages: pages.length, forms: forms.length, fields: forms.reduce((s, f) => s + f.fields.length, 0), tests: tests.length,
      tests_ok: tests.filter((p) => p.ok === true).length, tests_failing: tests.filter((p) => p.ok === false).length, findings: findings.length,
      accepts_invalid: findings.filter((h) => h.type === 'Accepts an invalid value').length, rejects_valid: findings.filter((h) => h.type === 'Rejects a valid value').length,
      by_severity: Object.fromEntries(['Critical', 'High', 'Medium', 'Low'].map((s) => [s, findings.filter((h) => h.severity === s).length])) },
    findings, forms,
  };
  const output = path.join(folder, 'forms.json');
  fs.writeFileSync(output, JSON.stringify(result, null, 2), 'utf8');
  const r = result.summary;
  console.log(`\nForms: ${r.forms} · fields: ${r.fields} · tests: ${r.tests} (${r.tests_failing} failing) · findings: ${r.findings}`);
  console.log(`Data: ${relRoot(output)}`);
  if (generateReport(folder)) console.log(`Report: ${relRoot(path.join(folder, 'forms-report.html'))}`);
}

if (require.main === module) {
  main().catch((e) => { console.error(`Error: ${e.message}`); process.exit(1); });
}

// extractForms is reused by the project-documenter's functional map (tools/functional-map).
module.exports = { parseArgs, testsFor, findingsOf, submitButton, GENERATED, extractForms: _forms };
