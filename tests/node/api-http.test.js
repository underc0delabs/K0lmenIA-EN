// Tests for the API step helpers (k0lmena tools/api/http.js): URLs, JSON, big ids,
// masked credentials and OpenAPI types.
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');

const http = require(path.resolve(__dirname, '..', '..', 'tools/k0lmena/tools/api/http.js'));

test('api: joins the base (with its basePath) and the spec path with a single slash', () => {
  for (const base of ['https://petstore.swagger.io/v2', 'https://petstore.swagger.io/v2/']) {
    for (const route of ['/pet/10', 'pet/10']) assert.equal(http.joinUrl(base, route), 'https://petstore.swagger.io/v2/pet/10');
  }
  assert.equal(http.joinUrl('https://a.test/api', '?q=1'), 'https://a.test/api?q=1');
  assert.equal(http.joinUrl('https://a.test', 'https://other.test/x'), 'https://other.test/x');
  assert.throws(() => http.joinUrl('', '/pet'), /API_BASEURL/);
});

test('api: detects the variables left without a value', () => {
  assert.deepEqual(http.variablesWithoutValue('/pet/{petId}/photo/{petId}'), ['petId']);
  assert.deepEqual(http.variablesWithoutValue('{"a":{"b":1}}'), []);
});

test('api: int64 ids do not lose precision', () => {
  const r = http.parseResponse('{"id":9223372036854775807,"price":10.5,"n":-3,"name":"a 9223372036854775807 \\" x","l":[12345678901234567890]}');
  assert.equal(r.id, '9223372036854775807');
  assert.equal(r.price, 10.5);
  assert.equal(r.n, -3);
  assert.equal(r.name, 'a 9223372036854775807 " x');
  assert.deepEqual(r.l, ['12345678901234567890']);
  assert.equal(http.parseResponse('logged in user session:123'), 'logged in user session:123');
  assert.equal(http.parseResponse(''), '');
  assert.equal(http.parseResponse('true'), true);
});

test('api: a badly written body gives a clear error', () => {
  assert.throws(() => http.parseJson('{"a": 1,}', 'The body'), /The body is not valid JSON/);
});

test('api: masks the credentials in headers and parameters', () => {
  assert.deepEqual(http.hideHeaders({ Authorization: 'Bearer abc', api_key: 'xyz', 'X-Tenant': 'demo', Cookie: 's=1' }),
    { Authorization: 'Bearer ***', api_key: '***', 'X-Tenant': 'demo', Cookie: '***' });
  assert.deepEqual(http.hideParameters({ key: 'x', apikey: 'y', q: 'dog' }), { key: 'x', apikey: '***', q: 'dog' });
});

test('api: OpenAPI types and their common aliases', () => {
  assert.ok(http.typeOf(10, 'integer').ok);
  assert.ok(!http.typeOf(10.5, 'integer').ok);
  assert.ok(http.typeOf(10.5, 'number').ok);
  assert.ok(http.typeOf('9223372036854775807', 'integer').ok);
  assert.ok(http.typeOf([], 'list').ok);
  assert.ok(http.typeOf(null, 'null').ok);
  assert.ok(http.typeOf('a', 'text').ok);
  assert.equal(http.typeOf('a', 'integer').actual, 'string');
  assert.throws(() => http.typeOf(1, 'date'), /Unknown type/);
});
