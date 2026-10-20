// Tests for synthetic monitoring (k0lmena tools/monitoring): checks, evaluation, changes and notification.
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');

const m = require(path.resolve(__dirname, '..', '..', 'tools/k0lmena/tools/monitoring/monitor.js'));
const base = { slowMs: 3000 };

test('monitoring: builds the checks from the config, --urls or MONITORING_URLS, GET or HEAD only', () => {
  const config = { checks: [{ name: 'Home', url: 'https://a.com/', text: 'Hello', max_ms: 1500 }, { url: 'https://a.com/health', method: 'head', status: [200, 204] }] };
  const cs = m.buildChecks(config, base, {});
  assert.deepEqual(cs.map((c) => [c.id, c.name, c.method, c.max_ms]), [
    ['GET a.com/', 'Home', 'GET', 1500], ['HEAD a.com/health', '/health', 'HEAD', 3000]]);
  assert.deepEqual(m.buildChecks(null, base, { MONITORING_URLS: 'https://b.com/x, https://b.com/' }).map((c) => c.name), ['/x', 'b.com']);
  assert.equal(m.buildChecks(config, base, { MONITORING_URLS: 'https://other.com' }).length, 2, 'with a config, MONITORING_URLS is not added');
  assert.throws(() => m.buildChecks({ checks: [{ url: 'https://a.com', method: 'POST' }] }, base, {}), /read-only/);
  assert.throws(() => m.buildChecks({ checks: [{ url: 'ftp://a.com' }] }, base, {}), /URL/);
  assert.throws(() => m.parseArgs(['--name', 'with space']));
  assert.throws(() => m.parseArgs(['--method']));
});

test('monitoring: evaluates status, texts and time', () => {
  const c = { method: 'GET', status: null, text: 'Welcome', no_text: 'Error 500', max_ms: 1000 };
  assert.equal(m.evaluate(c, { status: 200, ms: 300, body: 'Welcome' }).state, 'OK');
  assert.deepEqual(m.evaluate(c, { error: 'ECONNREFUSED' }), { state: 'Down', reason: 'ECONNREFUSED' });
  assert.match(m.evaluate(c, { status: 503, ms: 50, body: '' }).reason, /HTTP 503/);
  assert.match(m.evaluate(c, { status: 200, ms: 50, body: 'something else' }).reason, /does not appear/);
  assert.match(m.evaluate(c, { status: 200, ms: 50, body: 'Welcome Error 500' }).reason, /appears/);
  assert.deepEqual(m.evaluate(c, { status: 200, ms: 1500, body: 'Welcome' }), { state: 'Slow', reason: '1500 ms (maximum 1000 ms)' });
  assert.equal(m.evaluate({ ...c, status: [301], text: null }, { status: 301, ms: 10 }).state, 'OK');
  assert.equal(m.evaluate({ ...c, method: 'HEAD' }, { status: 200, ms: 10, body: '' }).state, 'OK', 'HEAD does not look for text');
});

test('monitoring: overall state, certificates and what changed', () => {
  assert.equal(m.overallState([{ state: 'OK' }, { state: 'Slow' }]), 'Degraded');
  assert.equal(m.overallState([{ state: 'Expiring' }, { state: 'Down' }]), 'Down');
  assert.equal(m.overallState([{ state: 'OK' }]), 'OK');
  assert.equal(m.remainingDays('2026-10-24T12:00:00Z', new Date('2026-10-14T12:00:00Z')), 10);
  assert.equal(m.remainingDays('not a date'), null);

  const previous = { state: 'Down', results: [{ id: 'a', state: 'Down' }, { id: 'b', state: 'OK' }] };
  const current = { state: 'Down', results: [{ id: 'a', state: 'OK' }, { id: 'b', state: 'Down' }, { id: 'c', state: 'Down' }] };
  assert.deepEqual(m.compare(previous, current), { previous: 'Down', broke: ['b', 'c'], recovered: ['a'], changed: true });
  assert.equal(m.compare({ state: 'OK', results: [{ id: 'a', state: 'OK' }] }, { state: 'OK', results: [{ id: 'a', state: 'OK' }] }).changed, false);
  assert.equal(m.compare(null, { state: 'OK', results: [{ id: 'a', state: 'Down' }] }).broke.length, 0, 'without a previous run there is no "broke"');
});

test('monitoring: the notification says what fails and what recovered', () => {
  const down = m.buildNotification({ name: 'prod', state: 'Down', changes: { previous: 'OK', broke: ['GET a.com/login'], recovered: [] },
    results: [{ name: '/login', state: 'Down', reason: 'HTTP 502' }, { name: '/', state: 'OK' }] });
  assert.equal(down.title, 'Monitoring prod: Down');
  assert.equal(down.level, 'error');
  assert.equal(down.text, 'Failing: /login (HTTP 502).');
  assert.deepEqual(down.fields, [['Checks', '1/2 OK'], ['Before', 'OK']]);
  const ok = m.buildNotification({ name: 'prod', state: 'OK', changes: { previous: 'Down', broke: [], recovered: ['GET a.com/login'] }, results: [{ name: '/login', state: 'OK' }] });
  assert.equal(ok.level, 'ok');
  assert.equal(ok.text, 'Recovered: GET a.com/login.');
});
