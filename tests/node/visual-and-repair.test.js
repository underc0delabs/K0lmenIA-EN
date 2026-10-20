// Tests for pixel-perfect, cross-browser and the automation repairer (k0lmena tools).
// The image comparison uses pngjs (a k0lmena dependency): if it is not installed, those tests are skipped.
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const K0 = path.join(ROOT, 'tools/k0lmena');
const visual = require(path.join(K0, 'tools/visual/compare.js'));
const pixel = require(path.join(K0, 'tools/pixel-perfect/pixel-perfect.js'));
const cross = require(path.join(K0, 'tools/cross-browser/cross-browser.js'));
const repair = require(path.join(K0, 'tools/repair/repair.js'));

let PNG = null;
try { ({ PNG } = require(require.resolve('pngjs', { paths: [K0] }))); } catch { /* k0lmena not installed */ }

const el = (key, tag, x, y, w = 100, h = 20, style = { background: '#ffffff', color: '#000000', font_size: '16px', font_weight: '400' }) =>
  ({ key, tag, text: key.split('|')[1] || '', desc: tag, x, y, w, h, style });

test('visual: detects shifted, missing, new, changed texts and styles', () => {
  const ref = [el('a|Home|1', 'a', 10, 10), el('a|Help|1', 'a', 200, 10), el('h1|Welcome|1', 'h1', 10, 60, 300, 40),
    el('button|Buy|1', 'button', 10, 120)];
  const act = [el('a|Home|1', 'a', 50, 10), el('h1|Deals|1', 'h1', 10, 60, 300, 40),
    el('button|Buy|1', 'button', 10, 120, 100, 20, { background: '#ff0000', color: '#000000', font_size: '16px', font_weight: '400' }),
    el('div|Promo|1', 'div', 0, 300, 400, 40)];
  const c = visual.compareElements(ref, act, { tolerance: 3 });
  assert.equal(c.moved.length, 1);
  assert.equal(c.moved[0].dx, 40);
  assert.deepEqual(c.missing.map((x) => x.key), ['a|Help|1']);
  assert.deepEqual(c.changed.map((x) => `${x.key}→${x.actual.key}`), ['h1|Welcome|1→h1|Deals|1']);
  assert.deepEqual(c.added.map((x) => x.key), ['div|Promo|1']);
  assert.equal(c.styles[0].prop, 'background');
  assert.equal(c.styles[0].to, '#ff0000');
});

test('visual: many elements that moved the same are a single block', () => {
  const ref = Array.from({ length: 6 }, (_, i) => el(`p|t${i}|1`, 'p', 10, 100 + i * 30));
  const act = ref.map((x) => ({ ...x, y: x.y + 46 }));
  const c = visual.compareElements(ref, act);
  assert.equal(c.blocks.length, 1);
  assert.equal(c.blocks[0].dy, 46);
  assert.equal(c.blocks[0].elements, 6);
  assert.equal(c.moved.length, 0);
});

test('visual: the pixel difference and its regions', { skip: !PNG && 'pngjs is not installed' }, () => {
  const canvas = (paint) => {
    const p = new PNG({ width: 64, height: 48 });
    p.data.fill(255);
    if (paint) for (let y = 8; y < 24; y++) for (let x = 8; x < 24; x++) { const o = (y * 64 + x) * 4; p.data[o] = p.data[o + 1] = p.data[o + 2] = 0; }
    return PNG.sync.write(p);
  };
  assert.equal(visual.comparePng(canvas(false), canvas(false)).pct, 0);
  const r = visual.comparePng(canvas(false), canvas(true));
  assert.equal(r.different, 256);
  assert.equal(r.regions.length, 1);
  const crop = PNG.sync.read(visual.markedCrop(canvas(true), { x: 0, y: 0, w: 40, h: 30 }, { x: 8, y: 8, w: 16, h: 16 }));
  assert.equal(crop.width, 40);
});

test('pixel-perfect: resolutions, screen IDs and findings with a cause', () => {
  assert.deepEqual(pixel.parseResolutions('390x844,1366x768').map((r) => r.name), ['Mobile', 'Desktop']);
  assert.throws(() => pixel.parseResolutions('large'));
  assert.equal(pixel.screenId(1, 'https://x.com/', '390x844'), '01-home-390x844');
  const added = el('div|Free shipping|1', 'div', 0, 54, 1366, 46);
  const from = el('p|Buy now|1', 'p', 10, 200);
  const p = { pct: 10, regions: [], height: 1046, height_ref: 1000,
    elements_cmp: { blocks: [{ dx: 0, dy: 46, elements: 8, from, box: {}, examples: [] }], moved: [], resized: [], changed: [],
      missing: [], added: [added], styles: [] } };
  const h = pixel.findingsOf(p, { pctMax: 0.2 });
  const block = h.find((x) => x.type === 'Shifted block');
  assert.match(block.title, /8 elements moved down 46 px/);
  assert.match(block.detail, /Probable cause: “Free shipping” appeared/);
  assert.ok(h.some((x) => x.type === 'Page height'));
});

test('cross-browser: what fails only in some browsers is a difference', () => {
  const sc = (status) => ({ key: 'f:3', scenario: 'Pay', uri: 'f', line: 3, story: 'US-1', case: 'TC-001', status,
    step: status === 'Failed' ? 'Then sees the ok' : null, error: status === 'Failed' ? 'Error: no' : '' });
  const runs = [{ id: 'chromium-1366x768', scenarios: [sc('Passed')] }, { id: 'firefox-1366x768', scenarios: [sc('Failed')] },
    { id: 'webkit-1366x768', scenarios: [sc('Passed')] }];
  const { rows, findings } = cross.analyzeSuite(runs, 'chromium');
  assert.equal(rows[0].class, 'Browser difference');
  assert.deepEqual(findings[0].failing, ['firefox-1366x768']);
  assert.match(findings[0].title, /fails in Firefox 1366x768/);
  const all = cross.analyzeSuite(runs.map((c) => ({ ...c, scenarios: [sc('Failed')] })), 'chromium');
  assert.equal(all.rows[0].class, 'Fails in all');
  assert.equal(cross.stripAnsi('\x1b[2m- hello\x1b[22m'), '- hello');
});

test('repairer: extracts the locator from the Playwright error', () => {
  const l = repair.locatorFromError("locator.click: Timeout 8000ms exceeded.\nCall log:\n  - waiting for getByRole('button', { name: 'Subscribe' })");
  assert.deepEqual(l.input, { role: 'button', name: 'Subscribe' });
  assert.deepEqual(repair.locatorFromError("Locator: getByPlaceholder('you@email.com')\nExpected: visible").input, { placeholder: 'you@email.com' });
  assert.deepEqual(repair.locatorFromError("strict mode violation: getByText('Tea') resolved to 2 elements").input, { text: 'Tea' });
  assert.deepEqual(repair.locatorFromError("waiting for locator('#btn-pay')").input, { css: '#btn-pay' });
  assert.deepEqual(repair.locatorFromError("getByRole('heading', { name: /deals/i, exact: true })").input,
    { role: 'heading', name: { regex: 'deals', flags: 'i' }, exact: true });
  assert.equal(repair.locatorFromError('AssertionError: expected 1 to equal 2'), null);
});

test('repairer: builds the locator code and replaces it in its line', () => {
  assert.equal(repair.codeOf({ role: 'button', name: "Pay now" }), "{ role: 'button', name: 'Pay now' }");
  assert.equal(repair.codeOf({ text: "l'agenda" }), "{ text: 'l\\'agenda' }");
  const r = { locator: { input: { role: 'button', name: 'Subscribe' } }, location: { type: 'locator' },
    proposal: { code: "{ role: 'button', name: 'Sign me up' }", input: { role: 'button', name: 'Sign me up' } } };
  assert.equal(repair.replaceInLine("  btn: { role: 'button', name: 'Subscribe' },", r), "  btn: { role: 'button', name: 'Sign me up' },");
  const f = { ...r, location: { type: 'feature', value: 'Coupons' }, proposal: { input: { role: 'heading', name: 'Promos' } } };
  assert.equal(repair.replaceInLine('    Then sees the "Coupons" card', f), '    Then sees the "Promos" card');
  const props = repair.proposalsFor({ tag: 'button', role: 'button', name: 'Add', text: 'Add', id: 'add-1' });
  assert.deepEqual(props[0], { role: 'button', name: 'Add' });
  assert.ok(props.some((p) => p.css === '#add-1'));
});

test('pixel-perfect: without --hide the reference\'s hidden areas are reused', () => {
  const ref = { config: { hide: ['.banner', '.date'] } };
  assert.deepEqual(pixel.effectiveHide({ hide: [] }, ref), ['.banner', '.date']);
  assert.deepEqual(pixel.effectiveHide({ hide: ['.other'] }, ref), ['.other']);
  assert.deepEqual(pixel.effectiveHide({ hide: [] }, null), []);
});
