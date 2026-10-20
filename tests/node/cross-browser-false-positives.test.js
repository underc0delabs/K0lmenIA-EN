// Cross-browser tests against false positives: the same error worded by each engine, the
// console noise, the resources each browser requests differently, the suite repetitions and the
// confirmation reload of the pages. No browser: the analysis functions are tested.
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');

const K0 = path.resolve(__dirname, '..', '..', 'tools/k0lmena');
const cross = require(path.join(K0, 'tools/cross-browser/cross-browser.js'));
const { slug } = require(path.join(K0, 'tools/explorer/explore.js'));
const PAGE = `01-${slug('https://app.test/')}`;

const CHROMIUM = { message: "Cannot read properties of undefined (reading 'total')", source: 'https://app.test/app.js:1:2045' };
const FIREFOX = { message: "can't access property \"total\", e is undefined", source: 'https://app.test/app.js:1:2045' };
const WEBKIT = { message: "undefined is not an object (evaluating 'e.total')", source: null };

test('cross-browser: the same error worded by each engine is the same error', () => {
  assert.ok(cross.sameError(CHROMIUM, FIREFOX), 'same source');
  assert.ok(cross.sameError({ ...CHROMIUM, source: null }, WEBKIT), 'same property: total');
  assert.ok(!cross.sameError(CHROMIUM, { message: "Cannot read properties of null (reading 'items')", source: null }));
  assert.deepEqual([...cross.errorTokens("Cannot read properties of undefined (reading 'total')")], ['total']);
  assert.equal(cross.sourceOf('TypeError: x\n    at pay (https://app.test/app.js?v=3:10:5)'), 'https://app.test/app.js:10:5');
  assert.equal(cross.sourceOf('pay@https://app.test/app.js:10:5\n'), 'https://app.test/app.js:10:5');
});

test('cross-browser: console noise, cancellations and the browser\'s own resources', () => {
  assert.ok(cross.isConsoleNoise('Failed to load resource: the server responded with a status of 404 (Not Found)'));
  assert.ok(cross.isConsoleNoise('Source map error: request failed with status 404'));
  assert.ok(!cross.isConsoleNoise('Uncaught (in promise) Error: payment rejected'));
  for (const t of ['net::ERR_ABORTED', 'NS_BINDING_ABORTED', 'NS_ERROR_ABORT', 'Load request cancelled']) assert.ok(cross.isCanceled(t), t);
  assert.ok(!cross.isCanceled('net::ERR_CONNECTION_REFUSED'));
  assert.ok(cross.isBrowserOwnResource('https://app.test/favicon.ico'));
  assert.equal(cross.resourceKey('https://app.test/a.css?v=123#x'), 'https://app.test/a.css');
  assert.equal(cross.colorDistance('#ff0000', '#fd0102'), 2);
  assert.equal(cross.colorDistance('#ff0000', 'transparent'), Infinity);
});

test('cross-browser: Firefox does not emulate isMobile but does emulate the touch screen', () => {
  const res = { width: 390, height: 844 };
  assert.equal(cross.contextOptions({ browser: 'firefox', res }).isMobile, undefined);
  assert.equal(cross.contextOptions({ browser: 'firefox', res }).hasTouch, true);
  assert.equal(cross.contextOptions({ browser: 'webkit', res }).isMobile, true);
  assert.equal(cross.contextOptions({ browser: 'firefox', res: { width: 1366, height: 768 } }).hasTouch, undefined);
});

const combos = ['chromium', 'firefox', 'webkit'].map((n) => ({ id: `${n}-1366x768`, browser: n, res: { id: '1366x768', width: 1366, height: 768 } }));
const measure = (nav, extra = {}) => ({ page: PAGE, url: 'https://app.test/', combo: `${nav}-1366x768`, browser: nav, status: 200,
  overflow: 0, js_errors_det: [], console_errors_det: [], js_errors: [], console_errors: [], failed_resources: [],
  _requests: new Set(), ...extra });
const analyze = (measures) => cross.analyzePages({ base: 'chromium', tolerance: 6, threshold: 0.1 }, combos, ['https://app.test/'],
  Object.fromEntries(measures.map((m) => [`${PAGE}|${m.combo}`, m])), '.', (p) => p);

test('cross-browser: an error that happens in all of them (with another text) is not "only in Firefox"', () => {
  const { findings } = analyze([measure('chromium', { js_errors_det: [CHROMIUM] }), measure('firefox', { js_errors_det: [FIREFOX] }),
    measure('webkit', { js_errors_det: [WEBKIT] })]);
  assert.equal(findings.length, 0);
});

test('cross-browser: a real error only in Firefox is still High', () => {
  const { findings } = analyze([measure('chromium'), measure('firefox', { js_errors_det: [{ message: 'structuredClone is not defined', source: null }] }), measure('webkit')]);
  assert.equal(findings.length, 1);
  assert.equal(findings[0].severity, 'High');
  assert.equal(findings[0].browser, 'firefox');
});

test('cross-browser: different errors in all engines weigh little (it may be the same one)', () => {
  const { findings } = analyze([measure('chromium', { js_errors_det: [{ message: 'Script error.', source: null }] }),
    measure('firefox', { js_errors_det: [{ message: 'e is undefined', source: null }] }), measure('webkit')]);
  assert.ok(findings.length >= 1);
  assert.ok(findings.every((h) => h.severity === 'Low'));
});

test('cross-browser: if a browser did not load the page, what the others have does not become exclusive', () => {
  const err = { message: 'Error: backend failure', source: null };
  const { findings } = analyze([measure('chromium', { js_errors_det: [err] }), measure('firefox', { js_errors_det: [err] }),
    measure('webkit', { error: 'Timeout 30000ms exceeded' })]);
  assert.equal(findings.length, 0);
});

test('cross-browser: resources: fails and another one loaded it (Medium); nobody else requested it (Low)', () => {
  const requests = new Set(['https://app.test/font.woff2', 'https://app.test/photo.webp']);
  const { findings } = analyze([measure('chromium', { _requests: requests }),
    measure('firefox', { failed_resources: [{ url: 'https://app.test/font.woff2?v=2', error: 'HTTP 404' }, { url: 'https://app.test/photo.avif', error: 'HTTP 404' }] }),
    measure('webkit', { _requests: requests })]);
  const sev = Object.fromEntries(findings.map((h) => [h.resource.split('/').pop(), h.severity]));
  assert.deepEqual(sev, { 'font.woff2': 'Medium', 'photo.avif': 'Low' });
});

test('cross-browser: the reload confirms, lowers the intermittent and discards what appears in another one', () => {
  const hz = (detail, extra) => ({ type: 'JavaScript error', severity: 'High', url: 'https://app.test/', resolution: '1366x768',
    combo: 'firefox-1366x768', browser: 'firefox', detail, error_det: { message: detail, source: null }, ...extra });
  const real = hz('structuredClone is not defined');
  const intermittent = hz('ChunkLoadError: Loading chunk 7 failed');
  const inOther = hz('Error: invalid sessionId');
  const findings = [real, intermittent, inOther];
  const of = (messages) => ({ js_errors_det: messages.map((message) => ({ message, source: null })), console_errors_det: [], failed_resources: [] });
  const fresh = {
    'https://app.test/|firefox-1366x768': of(['structuredClone is not defined', 'Error: invalid sessionId']),
    'https://app.test/|chromium-1366x768': of(['Error: invalid sessionId']),
    'https://app.test/|webkit-1366x768': of([]),
  };
  const r = cross.applyConfirmation([...findings], combos, fresh, findings);
  assert.deepEqual([r.confirmed, r.intermittent, r.discarded.length], [1, 1, 1]);
  assert.equal(real.confirmed, true);
  assert.equal(intermittent.severity, 'Low');
  assert.deepEqual(findings, [real, intermittent]);
});

test('cross-browser: an element is not "missing" if it is there with the same text (only the order changed)', () => {
  const f = [{ tag: 'a', text: 'Help' }, { tag: 'button', text: 'Pay' }];
  assert.deepEqual(cross.filterMissing(f, [{ tag: 'a', text: 'Help' }]), [{ tag: 'button', text: 'Pay' }]);
});

test('cross-browser: suite: what passes when repeated is Flaky; what fails again is confirmed', () => {
  const sc = (status, retries) => ({ key: 'f:3', scenario: 'Pay', uri: 'f', line: 3, story: 'US-1', case: 'TC-001', status,
    step: status === 'Failed' ? 'Then sees the ok' : null, error: status === 'Failed' ? 'Error: no' : '', ...(retries ? { retries } : {}) });
  const runs = (ff) => [{ id: 'chromium-1366x768', scenarios: [sc('Passed')] }, { id: 'firefox-1366x768', scenarios: [ff] }];

  const flaky = cross.analyzeSuite(runs(sc('Failed', ['Failed', 'Passed'])));
  assert.equal(flaky.rows[0].class, 'Flaky');
  assert.equal(flaky.findings[0].type, 'Flaky');
  assert.equal(flaky.findings[0].severity, 'Low');

  const confirmed = cross.analyzeSuite(runs(sc('Failed', ['Failed', 'Failed'])));
  assert.equal(confirmed.rows[0].class, 'Browser difference');
  assert.equal(confirmed.findings[0].severity, 'High');
  assert.equal(confirmed.findings[0].confirmed, true);
  assert.match(confirmed.findings[0].detail, /3 of 3/);

  const noRepeat = cross.analyzeSuite(runs(sc('Failed')));
  assert.equal(noRepeat.findings[0].severity, 'Medium');

  const timeout = { ...sc('Failed', ['Failed', 'Failed']), error: 'locator.click: Timeout 8000ms exceeded.' };
  assert.equal(cross.analyzeSuite(runs(timeout)).findings[0].severity, 'Medium');
});

test('cross-browser: --retries', () => {
  assert.equal(cross.parseArgs([]).retries, 2);
  assert.equal(cross.parseArgs(['--retries', '0']).retries, 0);
  assert.throws(() => cross.parseArgs(['--retries', '9']), /0 to 5/);
});
