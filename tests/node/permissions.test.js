// Tests for the permissions tester (k0lmena tools/permissions): pure functions, no browser.
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');

const p = require(path.resolve(__dirname, '..', '..', 'tools/k0lmena/tools/permissions/permissions.js'));

test('permissions: arguments and side-effect-free endpoints only', () => {
  assert.deepEqual(p.parseArgs(['--roles', 'admin, operator']).roles, ['admin', 'operator']);
  assert.equal(p.parseArgs(['--map', 'no']).map, false);
  assert.throws(() => p.parseArgs(['--story', 'bad']));
  assert.throws(() => p.parseArgs(['--max-pages', '0']));
  assert.deepEqual(p.parseEndpoints('GET /api/a, /api/b, head /api/c'),
    [{ method: 'GET', path: '/api/a' }, { method: 'GET', path: '/api/b' }, { method: 'HEAD', path: '/api/c' }]);
  assert.throws(() => p.parseEndpoints('DELETE /api/users/1'), /no side effects/);
});

test('permissions: roles from the .env, always with anonymous and without exposing passwords', () => {
  assert.equal(p.envKey('área manager', 'USER'), 'PERMISSIONS_AREA_MANAGER_USER');
  const env = { PERMISSIONS_ROLES: 'admin,operator', PERMISSIONS_ADMIN_USER: 'a', PERMISSIONS_ADMIN_PASSWORD: 'secret', PERMISSIONS_OPERATOR_USER: 'o', PERMISSIONS_OPERATOR_TOKEN: 't' };
  const roles = p.rolesFromEnv(env);
  assert.deepEqual(roles.map((r) => r.id), ['anonymous', 'admin', 'operator']);
  assert.equal(roles[1].has_credentials, true);
  assert.equal(roles[2].has_credentials, false);
  assert.equal(roles[2].has_token, true);
  assert.doesNotMatch(JSON.stringify(roles), /secret/);
  assert.deepEqual(p.rolesFromEnv({ APP_USER: 'u', APP_PASSWORD: 'c' }).map((r) => r.id), ['anonymous', 'user']);
  assert.deepEqual(p.rolesFromEnv(env, ['operator']).map((r) => r.id), ['anonymous', 'operator']);
  assert.deepEqual(p.rolesFromEnv({}).map((r) => r.id), ['anonymous']);
});

test('permissions: classifies each visit', () => {
  const base = { requestedUrl: 'https://a.com/admin', finalUrl: 'https://a.com/admin', requiresPassword: false, text: '', loginUrl: 'https://a.com/login' };
  assert.equal(p.classifyAccess({ ...base, status: 200 }), 'allowed');
  assert.equal(p.classifyAccess({ ...base, status: 403 }), 'denied');
  assert.equal(p.classifyAccess({ ...base, status: 404 }), 'not-found');
  assert.equal(p.classifyAccess({ ...base, status: 0 }), 'error');
  assert.equal(p.classifyAccess({ ...base, status: 200, finalUrl: 'https://a.com/login?next=/admin' }), 'requires-login');
  assert.equal(p.classifyAccess({ ...base, status: 200, requiresPassword: true }), 'requires-login');
  assert.equal(p.classifyAccess({ ...base, status: 200, text: "You don't have permission to view this page" }), 'denied');
  assert.equal(p.classifyAccess({ ...base, status: 200, requestedUrl: 'https://a.com/login', finalUrl: 'https://a.com/login', requiresPassword: true }), 'allowed');
});

test('permissions: findings with evidence in the matrix', () => {
  const roles = [{ id: 'anonymous', authenticated: false }, { id: 'admin', authenticated: true, has_credentials: true, login_ok: true },
    { id: 'operator', authenticated: true, has_credentials: true, login_ok: true }, { id: 'auditor', authenticated: true, has_credentials: true, login_ok: false, login_error: 'password' }];
  const A = 'https://a.com/admin';
  const R = 'https://a.com/reports';
  const paths = [{ url: A, path: '/admin', discovered_by: ['admin'] }, { url: R, path: '/reports', discovered_by: ['operator'] }];
  const matrix = [
    { role: 'anonymous', url: A, access: 'allowed', status: 200 }, { role: 'admin', url: A, access: 'allowed', status: 200 }, { role: 'operator', url: A, access: 'denied', status: 403 },
    { role: 'anonymous', url: R, access: 'requires-login', status: 200 }, { role: 'admin', url: R, access: 'allowed', status: 200 }, { role: 'operator', url: R, access: 'denied', status: 200 },
  ];
  const endpoints = [{ method: 'GET', path: '/api/x', url: 'https://a.com/api/x', results: { anonymous: { status: 200 }, admin: { status: 200 }, operator: { status: 403 } } }];
  const h = p.buildFindings({ roles, paths, matrix, endpoints });
  const t = h.map((x) => `${x.severity}|${x.type}|${x.role}`);
  assert.ok(t.includes('Critical|No login|anonymous'), t);
  assert.ok(t.includes('Critical|API without authentication|anonymous'), t);
  assert.ok(t.includes('High|Configuration|auditor'), t);
  assert.ok(t.includes('Medium|Option without permission|operator'), t);
  assert.ok(t.includes('High|Direct URL|admin'), t);
  assert.equal(h[0].severity, 'Critical');
  assert.deepEqual(h.map((x) => x.id), h.map((_, i) => `P-${String(i + 1).padStart(2, '0')}`));
  const r = p.summarize({ roles, paths, matrix, endpoints, findings: h });
  assert.equal(r.allowed, 3);
  assert.equal(r.denied, 2);
  assert.equal(r.require_login, 1);
  assert.equal(r.roles_with_session, 2);
});
