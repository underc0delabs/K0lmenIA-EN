// Tests of the resilience tester (k0lmena tools/resilience).
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');

const r = require(path.resolve(__dirname, '..', '..', 'tools/k0lmena/tools/resilience/resilience.js'));

test('resilience: arguments and scenarios', () => {
  assert.equal(r.parseArgs([]).scenarios.length, Object.keys(r.SCENARIOS).length);
  assert.deepEqual(r.parseArgs(['--scenarios', 'api-500, offline']).scenarios, ['api-500', 'offline']);
  assert.throws(() => r.parseArgs(['--scenarios', 'ddos']), /Unknown scenario/);
  assert.throws(() => r.parseArgs(['--timeout-ms', '10']));
  assert.throws(() => r.parseArgs(['--api-pattern', '(']));
});

test('resilience: what counts as an API call (without telemetry)', () => {
  assert.ok(r.isApi('https://app.com/api/products', 'fetch'));
  assert.ok(!r.isApi('https://app.com/app.js', 'script'));
  assert.ok(!r.isApi('https://app.com/cdn-cgi/rum?', 'xhr'));
  assert.ok(!r.isApi('https://www.google-analytics.com/g/collect', 'fetch'));
  assert.ok(r.isApi('https://app.com/graphql', 'other', '/graphql'));
});

test('resilience: simulated responses and nulled fields', () => {
  assert.equal(r.mockResponse('api-503').status, 503);
  assert.equal(r.mockResponse('empty').body, '');
  assert.throws(() => JSON.parse(r.mockResponse('malformed').body));
  assert.equal(r.mockResponse('timeout'), null);
  assert.deepEqual(JSON.parse(r.mockResponse('nulls', '{"a":1,"b":{"c":"x"},"d":[1,2]}').body), { a: null, b: { c: null }, d: [null, null] });
  assert.equal(r.mockResponse('nulls', '<html>').body, 'null');
});

test('resilience: retries of the same call', () => {
  assert.deepEqual(r.countRetries(['a', 'b', 'a', 'a']), { retries: 2, url: 'a' });
  assert.deepEqual(r.countRetries(['a', 'b']), { retries: 0, url: null });
});

test('resilience: findings of a scenario', () => {
  const base = { text_len: 1000, elements: 200, spinners: 0, js_errors: [], sample: 'Products' };
  const types = (res) => r.evaluate(base, res).map((h) => `${h.severity}:${h.type}`);
  // The API fails: it goes blank, with a spinner, a technical error and JS errors, and does not recover.
  assert.deepEqual(types({ scenario: 'api-500', status: 'ok', intercepted: 2, wait_ms: 6000, retries: 5, url_retries: '/api/x',
    js_errors: ['TypeError: x is undefined'], recovery: { recovers: false, text_len: 10 },
    observed: { url: 'https://app.com', text_len: 20, elements: 8, messages: [], spinners: 1, sample: 'undefined' } }),
  ['High:Blank screen', 'Medium:Infinite loading', 'Medium:Technical message', 'Medium:JavaScript error', 'Medium:Uncontrolled retries', 'High:Does not recover']);
  // Silent failure: content is missing and there is no message.
  assert.deepEqual(types({ scenario: 'empty', status: 'ok', intercepted: 1, content_change: true,
    observed: { url: 'https://app.com', text_len: 600, elements: 150, messages: [], spinners: 0, sample: '' } }), ['Medium:Silent failure']);
  // With a clear message, it holds up.
  assert.deepEqual(types({ scenario: 'api-500', status: 'ok', intercepted: 1, content_change: true, recovery: { recovers: true },
    observed: { url: 'https://app.com', text_len: 600, elements: 150, messages: ['We could not load the products. Retry'], spinners: 0, sample: '' } }), []);
  // No connection: the browser's error page.
  assert.deepEqual(types({ scenario: 'offline', status: 'ok', navigated: true, observed: { url: 'chrome-error://chromewebdata/', text_len: 0, elements: 0 } }), ['Low:No connection']);
  assert.deepEqual(r.evaluate(base, { scenario: 'api-500', status: 'not-applicable' }), []);
});

test('resilience: run summary', () => {
  const s = r.summarize([{ results: [{ scenario: 'a', status: 'ok' }, { scenario: 'b', status: 'finding' }, { scenario: 'c', status: 'not-applicable' }] }],
    [{ severity: 'High', type: 'Blank screen' }, { severity: 'Medium', type: 'Silent failure' }]);
  assert.equal(s.tests, 3);
  assert.equal(s.ok, 1);
  assert.equal(s.not_applicable, 1);
  assert.equal(s.blank_screens, 1);
  assert.equal(s.silent_failures, 1);
  assert.equal(s.by_severity.High, 1);
});
