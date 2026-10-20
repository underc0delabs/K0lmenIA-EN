// Email verification with Mailpit (email-verifier agent).
//
// Usage (from the repo root):
//   npm run emails -- [--to ana@test.com] [--from no-reply@app.com] [--subject "Confirm"] [--search "Mailpit query"]
//                      [--since-min 30] [--last 20] [--wait 1 --timeout-s 60] [--expect expected.json]
//                      [--links yes|no] [--story US-001] [--mailpit http://localhost:8025]
//   npm run emails -- --clean-mailbox        → deletes ALL the messages in the test mailbox (with confirmation)
//
// Mailpit is a test mailbox: the app (in the test environment) sends its emails over SMTP to Mailpit
// (port 1025) and Mailpit stores them without delivering them to anyone. This tool reads them through its API
// (MAILPIT_URL in the .env; by default http://localhost:8025) and reviews each one:
//   - that what was expected arrived (--expect: recipient, subject, texts, links and attachments of each case),
//   - subject, sender and recipients; unreplaced variables ({{name}}, ${x}, undefined, null…),
//   - plain-text version, HTML size (Gmail clips from 102 KB), images without alt or that
//     point to localhost, broken links, links to localhost or without https (Mailpit link-check),
//   - HTML compatibility with email clients (Mailpit html-check: Outlook, Gmail, Apple Mail…),
//   - how it looks on desktop (700 px) and on mobile (375 px), with a screenshot of each and whether it overflows.
// With --wait N it waits until N matching emails arrive (after triggering the send).
//
// It leaves everything in output/emails/<US or mailbox>/: emails.json, emails-report.html, screenshots/ and eml/ (the
// original message). The previous run moves to history/ (the last 5 are kept). It only reads the
// mailbox: deleting it (--clean-mailbox) is done with confirmation.
const fs = require('fs');
const path = require('path');
const { archive } = require('../history/history.js');

const ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const fromCwd = (p) => path.resolve(process.env.INIT_CWD || process.cwd(), p); // npm run changes the cwd to tools/k0lmena
const GENERATED = ['emails.json', 'analysis.json', 'emails-report.html', 'screenshots', 'eml'];
const SEV_ORDER = { 'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3 };
// Template variables that were left unreplaced (or empty JavaScript values).
const VARIABLE = /\{\{\s*[\w.]+\s*\}\}|\$\{[\w.]+\}|%\([\w]+\)s|\[\[[\w ]+\]\]|\[(?:NOMBRE|NAME|USUARIO|USER|EMAIL|LINK|URL)\]|\bundefined\b|\[object Object\]|\bNaN\b|(?<![\w.])null(?![\w.])/g;
const LOCAL = /^https?:\/\/(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]|[\w-]+\.local)(:\d+)?\b/i;

function parseArgs(argv) {
  const a = { last: 50, timeoutS: 60, links: true, mailpit: process.env.MAILPIT_URL || 'http://localhost:8025' };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    const v = () => argv[++i];
    if (k === '--to') a.to = v();
    else if (k === '--from') a.from = v();
    else if (k === '--subject') a.subject = v();
    else if (k === '--search') a.search = v();
    else if (k === '--since-min') a.sinceMin = parseFloat(v());
    else if (k === '--last') a.last = parseInt(v(), 10);
    else if (k === '--wait') a.wait = parseInt(v(), 10);
    else if (k === '--timeout-s') a.timeoutS = parseInt(v(), 10);
    else if (k === '--expect') a.expect = v();
    else if (k === '--links') a.links = !/^(no|false|0)$/i.test(v());
    else if (k === '--story') a.story = v();
    else if (k === '--mailpit') a.mailpit = v();
    else if (k === '--output') a.output = v();
    else if (k === '--clean-mailbox') a.clean = true;
    else if (k === '-h' || k === '--help') a.help = true;
    else throw new Error(`Unknown option: ${k}`);
  }
  if (a.story && !/^[A-Za-z]+-\d+$/.test(a.story)) throw new Error('--story must be an ID like US-001.');
  a.mailpit = a.mailpit.replace(/\/+$/, '');
  return a;
}

// ------------------------------------------------------------------ Mailpit API
function headers() {
  const h = { Accept: 'application/json' };
  if (process.env.MAILPIT_USER) h.Authorization = `Basic ${Buffer.from(`${process.env.MAILPIT_USER}:${process.env.MAILPIT_PASSWORD || ''}`).toString('base64')}`;
  return h;
}

async function api(base, route, { method = 'GET', body, text = false } = {}) {
  let r;
  try {
    r = await fetch(`${base}${route}`, { method, headers: { ...headers(), ...(body ? { 'Content-Type': 'application/json' } : {}) },
      body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(30000) });
  } catch (e) {
    throw new Error(`Could not connect to Mailpit at ${base} (${e.cause ? e.cause.code || e.cause.message : e.message}). ` +
      'Is it running? See tools/mailpit/README.md');
  }
  if (!r.ok) throw Object.assign(new Error(`Mailpit responded ${r.status} on ${route}`), { status: r.status });
  return text ? r.text() : r.json();
}

const address = (x) => (x && (x.Address || x.address)) || '';
const addresses = (xs) => (xs || []).map(address).filter(Boolean);

// Mailpit search query built from the filters.
function searchQuery(a) {
  const parts = [];
  if (a.to) parts.push(`to:"${a.to}"`);
  if (a.from) parts.push(`from:"${a.from}"`);
  if (a.subject) parts.push(`subject:"${a.subject}"`);
  if (a.search) parts.push(a.search);
  return parts.join(' ');
}

async function list(a) {
  const q = searchQuery(a);
  const route = q ? `/api/v1/search?query=${encodeURIComponent(q)}&limit=${a.last}` : `/api/v1/messages?limit=${a.last}`;
  let items = (await api(a.mailpit, route)).messages || [];
  if (a.sinceMin) {
    const limit = Date.now() - a.sinceMin * 60000;
    items = items.filter((m) => new Date(m.Created || m.Date || 0).getTime() >= limit);
  }
  return items;
}

async function waitFor(a) {
  const end = Date.now() + a.timeoutS * 1000;
  let items = [];
  while (Date.now() < end) {
    items = await list(a);
    if (items.length >= a.wait) return items;
    await new Promise((r) => setTimeout(r, 2000));
  }
  return items;
}

// ------------------------------------------------------------------ review of an email
function plainText(html) {
  return String(html || '').replace(/<style[\s\S]*?<\/style>|<script[\s\S]*?<\/script>/gi, ' ').replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/\s+/g, ' ').trim();
}

function linksOf(html, text) {
  const hrefs = [...String(html || '').matchAll(/<a\b[^>]*href\s*=\s*["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi)]
    .map((m) => ({ url: m[1].replace(/&amp;/g, '&'), text: plainText(m[2]).slice(0, 80) }));
  const loose = [...String(text || '').matchAll(/https?:\/\/[^\s<>"')]+/g)].map((m) => ({ url: m[0], text: '' }));
  const seen = new Set();
  return [...hrefs, ...loose].filter((l) => !seen.has(l.url) && seen.add(l.url));
}

function imagesOf(html) {
  return [...String(html || '').matchAll(/<img\b[^>]*>/gi)].map((m) => {
    const tag = m[0];
    const src = (tag.match(/\bsrc\s*=\s*["']([^"']*)["']/i) || [])[1] || '';
    const alt = tag.match(/\balt\s*=\s*["']([^"']*)["']/i);
    return { src, alt: alt ? alt[1] : null };
  });
}

function review(m, extras) {
  const h = [];
  const add = (type, severity, title, detail) => h.push({ type, severity, title, detail });
  const subject = m.Subject || '';
  const html = m.HTML || '';
  const text = m.Text || '';
  if (!subject.trim()) add('Subject', 'High', 'The email has no subject', 'Without a subject, clients show it as "(no subject)" and it often goes to spam.');
  else if (subject.length > 78) add('Subject', 'Low', `Long subject (${subject.length} characters)`, 'On mobile it is cut at 30–40 characters: the important part must come first.');
  if (!address(m.From)) add('Sender', 'High', 'No sender', 'The From field is empty.');
  if (!addresses(m.To).length) add('Recipient', 'High', 'No recipient', 'The To field is empty (BCC only?).');
  for (const [where, content] of [['subject', subject], ['text', text], ['HTML', plainText(html)]]) {
    const vs = [...new Set((content.match(VARIABLE) || []).map((x) => x.trim()))];
    if (vs.length) add('Unreplaced variable', 'High', `${vs.slice(0, 3).join(', ')} in the ${where}`,
      `The template sent ${vs.join(', ')} without the real value: the person sees it as is.`);
  }
  if (html && !text.trim()) add('Plain text', 'Medium', 'It has no plain-text version', 'Some clients and screen readers use the text version; without it the spam score goes up.');
  const kb = Buffer.byteLength(html, 'utf8') / 1024;
  if (kb > 102) add('Size', 'Medium', `${Math.round(kb)} KB of HTML`, 'Gmail clips messages over 102 KB and hides the rest behind "View entire message".');
  const imgs = imagesOf(html);
  const noAlt = imgs.filter((i) => i.alt === null);
  if (noAlt.length) add('Images', 'Low', `${noAlt.length} image(s) without alternative text`, 'Many clients block images: without alt, nobody knows what they said.');
  const imgLocal = imgs.filter((i) => LOCAL.test(i.src) || /^(file:|\/[^/]|\.\.?\/)/i.test(i.src));
  if (imgLocal.length) add('Images', 'High', `${imgLocal.length} image(s) that will not be displayed`, `They point to a local or relative path: ${imgLocal.slice(0, 3).map((i) => i.src).join(', ')}`);
  const links = linksOf(html, text);
  for (const l of links) {
    if (LOCAL.test(l.url)) l.problem = { severity: 'High', text: 'points to a local environment' };
    else if (/^http:\/\//i.test(l.url)) l.problem = { severity: 'Medium', text: 'without https' };
    const chk = (extras.links || []).find((x) => x.URL === l.url);
    if (chk) {
      l.status = chk.StatusCode;
      // A link to localhost is already flagged for that (it is the cause, not that it "does not respond").
      if ((!chk.StatusCode || chk.StatusCode >= 400) && !LOCAL.test(l.url)) {
        l.problem = { severity: 'High', text: chk.StatusCode ? `broken (${chk.StatusCode})` : `no response (${chk.Status || 'error'})` };
      }
    }
  }
  for (const l of links.filter((x) => x.problem)) {
    add('Link', l.problem.severity, `Link ${l.problem.text}: ${l.text || l.url}`.slice(0, 140), l.url);
  }
  const lu = m.ListUnsubscribe || {};
  if (lu.Errors) add('Unsubscribe', 'Low', 'The List-Unsubscribe header has errors', lu.Errors);
  const compat = extras.compat;
  if (compat && compat.problems.length) {
    add('Compatibility', compat.pct < 80 ? 'Medium' : 'Low', `${compat.problems.length} HTML feature(s) not supported in some clients (${compat.pct} % compatible)`,
      compat.problems.slice(0, 5).map((p) => `${p.title}: ${p.clients.join(', ')}`).join(' · '));
  }
  if (extras.overflow > 4) add('Responsive', 'Medium', `On mobile (375 px) it overflows ${extras.overflow} px in width`, 'A horizontal scroll appears: the design does not adapt to the phone.');
  return { findings: h, links, images: imgs.length };
}

// Compatibility: summary of the Mailpit html-check (which features the main clients do not support).
function summarizeCompat(hc) {
  if (!hc || !hc.Total) return null;
  const t = hc.Total;
  const pct = typeof t.Supported === 'number' ? Math.round(t.Supported) : null;
  const problems = (hc.Warnings || []).map((w) => {
    const no = (w.Results || []).filter((r) => r.Support === 'no').map((r) => `${r.Family}${r.Platform ? ` (${r.Platform})` : ''}`);
    return { title: w.Title, category: w.Category, clients: [...new Set(no)].slice(0, 6), url: w.URL };
  }).filter((p) => p.clients.length);
  return { pct, problems };
}

// ------------------------------------------------------------------ expectations (what had to arrive)
function evaluateExpectations(expected, emails) {
  return expected.map((x, i) => {
    const cand = emails.filter((c) => (!x.to || c.to.some((p) => p.toLowerCase() === String(x.to).toLowerCase()))
      && (!x.subject || c.subject.toLowerCase().includes(String(x.subject).toLowerCase())));
    const r = { id: `E-${String(i + 1).padStart(2, '0')}`, ...x, checks: [] };
    if (!cand.length) { r.status = 'Not received'; return r; }
    const c = cand[0];
    r.email = c.id;
    const body = `${c.text} ${c.html_text}`.toLowerCase();
    const ctl = (name, ok, detail = '') => r.checks.push({ name, ok, detail });
    if (x.sender) ctl(`Sender ${x.sender}`, c.from.toLowerCase() === String(x.sender).toLowerCase(), c.from);
    for (const t of x.contains || []) ctl(`Contains “${t}”`, body.includes(String(t).toLowerCase()));
    for (const t of x.not_contains || []) ctl(`Does not contain “${t}”`, !body.includes(String(t).toLowerCase()));
    for (const t of x.links || []) {
      const l = c.links.find((y) => y.url.includes(t));
      ctl(`Link to “${t}”`, Boolean(l) && !(l.problem && l.problem.severity === 'High'), l ? l.url : 'not present');
    }
    for (const t of x.attachments || []) ctl(`Attachment ${t}`, c.attachments.some((y) => y.name.toLowerCase().includes(String(t).toLowerCase())));
    if (x.max_minutes && c.delay_min != null) ctl(`Arrives in less than ${x.max_minutes} min`, c.delay_min <= x.max_minutes, `${c.delay_min} min`);
    r.status = r.checks.every((y) => y.ok) ? 'Met' : 'Not met';
    return r;
  });
}

// ------------------------------------------------------------------ HTML screenshot (desktop and mobile)
async function screenshots(browser, html, base) {
  const output = {};
  for (const [name, width] of [['desktop', 700], ['mobile', 375]]) {
    const page = await browser.newPage({ viewport: { width, height: 900 }, javaScriptEnabled: false });
    try {
      await page.setContent(html || '<p style="font-family:sans-serif;color:#888">(no HTML: text only)</p>', { waitUntil: 'load', timeout: 20000 })
        .catch(() => page.setContent(html, { waitUntil: 'domcontentloaded' }));
      const file = `${base}-${name}.png`;
      const height = await page.evaluate(() => Math.min(document.documentElement.scrollHeight, 6000));
      await page.screenshot({ path: file, clip: { x: 0, y: 0, width, height: Math.max(200, height) } });
      output[name] = file;
      if (name === 'mobile') output.overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    } finally {
      await page.close();
    }
  }
  return output;
}

function generateReport(folder) {
  const py = process.platform === 'win32' ? 'python' : 'python3';
  const r = require('child_process').spawnSync(py, [path.join(ROOT, 'scripts', 'generate_emails_report.py'),
    path.join(folder, 'emails.json'), path.join(folder, 'emails-report.html')], { encoding: 'utf8' });
  if (r.status !== 0) {
    const reason = (r.stderr || r.error || '').toString().trim().split(/\r?\n/).pop();
    console.log(`Could not generate the HTML report (${reason}). Generate it with: python scripts/generate_emails_report.py <folder>/emails.json <folder>/emails-report.html`);
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
  if (a.clean) {
    await api(a.mailpit, '/api/v1/messages', { method: 'DELETE', body: {} });
    console.log(`Test mailbox emptied (${a.mailpit}).`);
    return;
  }
  const info = await api(a.mailpit, '/api/v1/info').catch((e) => { if (e.status) return {}; throw e; });
  const items = a.wait ? await waitFor(a) : await list(a);
  const name = a.story || (a.to ? a.to.replace(/[^\w.@-]+/g, '_') : 'mailbox');
  const folder = a.output ? fromCwd(a.output) : path.join(ROOT, 'output', 'emails', name);
  archive(folder, GENERATED, 'emails.json');
  for (const n of GENERATED) fs.rmSync(path.join(folder, n), { recursive: true, force: true });
  const shotsDir = path.join(folder, 'screenshots');
  const emlDir = path.join(folder, 'eml');
  for (const d of [shotsDir, emlDir]) fs.mkdirSync(d, { recursive: true });
  const rel = (p) => path.relative(folder, p).split(path.sep).join('/');
  const relRoot = (p) => path.relative(ROOT, p).split(path.sep).join('/');
  console.log(`Mailpit ${info.Version || ''} at ${a.mailpit} · ${items.length} email(s)${searchQuery(a) ? ` for «${searchQuery(a)}»` : ''}`);

  const { chromium } = require('playwright');
  const browser = await chromium.launch();
  const emails = [];
  try {
    for (const [i, summary] of items.entries()) {
      const id = summary.ID;
      const m = await api(a.mailpit, `/api/v1/message/${id}`);
      const n = String(i + 1).padStart(2, '0');
      process.stdout.write(`[${i + 1}/${items.length}] ${m.Subject || '(no subject)'} → ${addresses(m.To).join(', ')} `);
      const raw = await api(a.mailpit, `/api/v1/message/${id}/raw`, { text: true }).catch(() => null);
      let eml = null;
      if (raw) { eml = path.join(emlDir, `${n}-${id}.eml`); fs.writeFileSync(eml, raw); }
      const hc = await api(a.mailpit, `/api/v1/message/${id}/html-check`).catch(() => null);
      const lc = a.links ? await api(a.mailpit, `/api/v1/message/${id}/link-check?follow=true`).catch(() => null) : null;
      const cap = await screenshots(browser, m.HTML, path.join(shotsDir, `${n}-${id}`));
      const compat = summarizeCompat(hc);
      const rev = review(m, { links: lc && lc.Links, compat, overflow: cap.overflow });
      const created = new Date(m.Date || summary.Created || Date.now());
      const received = new Date(summary.Created || m.Date || Date.now());
      emails.push({
        id: `M-${n}`, mailpit_id: id, subject: m.Subject || '', from: address(m.From), to: addresses(m.To), cc: addresses(m.Cc),
        reply_to: addresses(m.ReplyTo), date: received.toISOString(), delay_min: Math.max(0, Math.round((received - created) / 6000) / 10),
        size_kb: Math.round((m.Size || 0) / 1024 * 10) / 10, html_kb: Math.round(Buffer.byteLength(m.HTML || '', 'utf8') / 102.4) / 10,
        has_html: Boolean(m.HTML), has_text: Boolean((m.Text || '').trim()), text: (m.Text || '').slice(0, 4000),
        html_text: plainText(m.HTML).slice(0, 4000), attachments: (m.Attachments || []).map((x) => ({ name: x.FileName, type: x.ContentType, kb: Math.round((x.Size || 0) / 102.4) / 10 })),
        images: rev.images, links: rev.links, compatibility: compat, mobile_overflow: cap.overflow,
        desktop_screenshot: cap.desktop && rel(cap.desktop), mobile_screenshot: cap.mobile && rel(cap.mobile), eml: eml && rel(eml),
        view_in_mailpit: `${a.mailpit}/view/${id}`, findings: rev.findings,
      });
      console.log(`→ ${rev.findings.length} finding(s)`);
    }
  } finally {
    await browser.close();
  }
  const expected = a.expect ? JSON.parse(fs.readFileSync(fromCwd(a.expect), 'utf8')) : [];
  const expectations = evaluateExpectations(Array.isArray(expected) ? expected : expected.emails || [], emails);
  const findings = [];
  for (const c of emails) for (const h of c.findings) findings.push({ ...h, email: c.id, subject: c.subject, screenshot: c.desktop_screenshot });
  for (const x of expectations.filter((y) => y.status !== 'Met')) {
    findings.push({ type: 'Expectation', severity: x.status === 'Not received' ? 'Critical' : 'High', email: x.email || null,
      title: x.status === 'Not received' ? `The expected email did not arrive${x.subject ? ` «${x.subject}»` : ''}${x.to ? ` to ${x.to}` : ''}`
        : `The email «${x.subject || x.email}» does not meet the expectation: ${x.checks.filter((y) => !y.ok).map((y) => y.name).join(', ')}`,
      detail: x.case ? `Case ${x.case}` : '' });
  }
  findings.sort((x, y) => SEV_ORDER[x.severity] - SEV_ORDER[y.severity]);
  findings.forEach((h, i) => { h.id = `C-${String(i + 1).padStart(2, '0')}`; });
  const compats = emails.map((c) => c.compatibility && c.compatibility.pct).filter((x) => x != null);
  const stamp = () => { const d = new Date(); const p = (x) => String(x).padStart(2, '0'); return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`; };
  const result = {
    mailpit: a.mailpit, mailpit_version: info.Version || null, story: a.story || null, filter: searchQuery(a) || null,
    date: new Date().toISOString(), stamp: stamp(), tool: 'Mailpit API · Playwright',
    summary: { emails: emails.length, expectations: expectations.length, met: expectations.filter((x) => x.status === 'Met').length,
      not_received: expectations.filter((x) => x.status === 'Not received').length, findings: findings.length,
      links: emails.reduce((s, c) => s + c.links.length, 0), problem_links: emails.reduce((s, c) => s + c.links.filter((l) => l.problem).length, 0),
      unreplaced_variables: findings.filter((h) => h.type === 'Unreplaced variable').length,
      compatibility_avg: compats.length ? Math.round(compats.reduce((s, x) => s + x, 0) / compats.length) : null,
      by_severity: Object.fromEntries(['Critical', 'High', 'Medium', 'Low'].map((s) => [s, findings.filter((h) => h.severity === s).length])) },
    expectations, findings, emails,
  };
  const output = path.join(folder, 'emails.json');
  fs.writeFileSync(output, JSON.stringify(result, null, 2), 'utf8');
  const r = result.summary;
  console.log(`\nEmails: ${r.emails} · expectations: ${r.met}/${r.expectations} met (${r.not_received} not received) · findings: ${r.findings}`);
  console.log(`Data: ${relRoot(output)}`);
  if (generateReport(folder)) console.log(`Report: ${relRoot(path.join(folder, 'emails-report.html'))}`);
}

if (require.main === module) {
  main().catch((e) => { console.error(`Error: ${e.message}`); process.exit(1); });
}

module.exports = { parseArgs, searchQuery, review, summarizeCompat, evaluateExpectations, linksOf, imagesOf, plainText, VARIABLE, GENERATED };
