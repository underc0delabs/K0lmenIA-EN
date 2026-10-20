// Tests for the email verifier, the translation analyst and the run history (k0lmena tools).
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const K0 = path.resolve(__dirname, '..', '..', 'tools/k0lmena');
const emails = require(path.join(K0, 'tools/emails/emails.js'));
const trad = require(path.join(K0, 'tools/translator/translator.js'));
const history = require(path.join(K0, 'tools/history/history.js'));

test('emails: unreplaced variables, links to localhost, images and plain text', () => {
  const m = { Subject: 'Your order {{number}} is ready', From: { Address: 'a@b.com' }, To: [{ Address: 'ana@test.com' }], Text: '',
    HTML: '<p>Hi undefined</p><img src="/logo.png"><a href="http://localhost:3000/x">View</a><a href="https://ok.com/y">Ok</a>' };
  const r = emails.review(m, { links: [{ URL: 'https://ok.com/y', StatusCode: 404 }] });
  const types = r.findings.map((h) => h.type);
  assert.ok(types.filter((t) => t === 'Unreplaced variable').length >= 2);
  assert.ok(types.includes('Plain text') && types.includes('Images'));
  const link = r.findings.filter((h) => h.type === 'Link').map((h) => h.title).join(' | ');
  assert.match(link, /local environment/);
  assert.match(link, /broken \(404\)/);
  assert.equal(emails.searchQuery({ to: 'ana@test.com', subject: 'Hello' }), 'to:"ana@test.com" subject:"Hello"');
});

test('emails: expectations that are met, not met and not received', () => {
  const c = [{ id: 'M-01', to: ['ana@test.com'], subject: 'Welcome to the store', from: 'no-reply@x.com', text: 'Hi Ana', html_text: 'Hi Ana',
    links: [{ url: 'https://x.com/confirm?t=1' }], attachments: [{ name: 'invoice.pdf' }] }];
  const r = emails.evaluateExpectations([
    { to: 'ana@test.com', subject: 'welcome', contains: ['Hi Ana'], links: ['/confirm'], attachments: ['invoice'] },
    { to: 'ana@test.com', subject: 'welcome', not_contains: ['Ana'] },
    { to: 'ana@test.com', subject: 'Reset your password' }], c);
  assert.deepEqual(r.map((x) => x.status), ['Met', 'Not met', 'Not received']);
  const compat = emails.summarizeCompat({ Total: { Supported: 71.4 }, Warnings: [{ Title: 'border-radius', Results: [{ Family: 'Outlook', Platform: 'windows', Support: 'no' }] }] });
  assert.equal(compat.pct, 71);
  assert.deepEqual(compat.problems[0].clients, ['Outlook (windows)']);
});

test('translator: detects the language of long and short texts', () => {
  assert.equal(trad.detectLanguage('Comprá lo que necesites con envío gratis a todo el país'), 'es');
  assert.equal(trad.detectLanguage('Welcome to the store, find all the products you need'), 'en');
  assert.equal(trad.detectLanguage('Buscar produtos'), 'pt');
  assert.equal(trad.detectLanguage('Buscar productos'), 'es');
  assert.equal(trad.detectLanguage('Hola Ana'), null);
});

test('translator: keys, encoding, formats and months', () => {
  assert.ok(trad.KEY.test('checkout.add_to_cart') && trad.KEY.test('translation missing: en.home.title'));
  assert.ok(!trad.KEY.test('www.example'.toUpperCase()));
  assert.ok(trad.MOJIBAKE.test('EnvÃ­o gratis') && !trad.MOJIBAKE.test('Envío gratis'));
  assert.deepEqual(trad.oddNumberFormat('Price: $ 1.234,56', 'en-US'), ['1.234,56']);
  assert.deepEqual(trad.oddNumberFormat('Precio: $ 1.234,56', 'es-AR'), []);
  assert.deepEqual(trad.oddNumberFormat('Total 1,234.56', 'es-AR'), ['1,234.56']);
  assert.deepEqual(trad.otherLanguageMonths('Deals valid until 15 de octubre', 'en-US'), ['octubre']);
  assert.deepEqual(trad.otherLanguageMonths('Válido hasta el 15 de octubre', 'es-AR'), []);
});

test('translator: URL of each language and findings of a screen', () => {
  const alt = [{ language: 'en', url: 'https://x.com/en/' }, { language: 'pt-BR', url: 'https://x.com/pt/' }];
  assert.deepEqual(trad.urlInLanguage('https://x.com/en/', 'en-US', alt, '', 'es'), { url: 'https://x.com/en/', method: 'hreflang' });
  assert.equal(trad.urlInLanguage('https://x.com/en/productos', 'pt', null, 'https://x.com/{short_language}/', 'es').url, 'https://x.com/pt/productos');
  assert.equal(trad.urlInLanguage('https://x.com/', 'en', null, '?lang={short_language}', 'es').url, 'https://x.com/?lang=en');
  const ref = { lang: 'es', overflow: 0, texts: [{ key: 'main:1>p:1', text: 'Envío gratis a todo el país hoy' }] };
  const en = { lang: 'es', overflow: 0, texts: [{ key: 'main:1>p:1', text: 'Envío gratis a todo el país hoy', x: 0, y: 0, w: 10, h: 10 },
    { key: 'main:1>button:1', text: 'checkout.pay', x: 0, y: 0, w: 10, h: 10 },
    { key: 'main:1>button:2', text: 'Add to cart now please', truncated: true, x: 0, y: 0, w: 10, h: 10 }] };
  const types = trad.screenFindings(en, ref, 'en-US', 'es-AR').map((h) => h.type);
  assert.ok(types.includes('Lang attribute') && types.includes('Untranslated') && types.includes('Translation key') && types.includes('Truncated text'));
});

test('history: keeps the previous run and only the last 5', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'k0hist-'));
  for (let i = 1; i <= 7; i++) {
    fs.writeFileSync(path.join(dir, 'data.json'), JSON.stringify({ stamp: `2026101${i}-120000` }));
    fs.mkdirSync(path.join(dir, 'screenshots'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'screenshots', 'a.png'), 'x');
    const target = history.archive(dir, ['data.json', 'screenshots'], 'data.json', 5);
    assert.ok(fs.existsSync(path.join(target, 'screenshots', 'a.png')));
    assert.ok(!fs.existsSync(path.join(dir, 'data.json')));
  }
  const kept = fs.readdirSync(path.join(dir, 'history')).sort();
  assert.equal(kept.length, 4);   // 4 previous + the current one = 5
  assert.equal(kept[0], '20261014-120000');
  fs.writeFileSync(path.join(dir, 'data.json'), '[]');
  assert.equal(history.archive(dir, ['data.json'], 'data.json'), null); // an empty report is not a run
  fs.rmSync(dir, { recursive: true, force: true });
});
