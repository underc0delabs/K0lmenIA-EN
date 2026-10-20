// Tests for the saved session (k0lmena tools/login): npm run login arguments and which file SESSION uses.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const k0 = path.resolve(__dirname, '..', '..', 'tools/k0lmena/tools/login');
const s = require(path.join(k0, 'session.js'));
const { parseArgs } = require(path.join(k0, 'login.js'));

test('login: default and named session file, inside .auth/', () => {
  assert.equal(s.sessionFile(''), path.join(s.FOLDER, 'session.json'));
  assert.equal(s.sessionFile('admin'), path.join(s.FOLDER, 'session-admin.json'));
  assert.equal(path.basename(s.FOLDER), '.auth');
  assert.ok(fs.existsSync(path.join(s.ROOT, 'package.json')), 'ROOT is the repo root');
  for (const bad of ['../x', 'a b', 'a/b', 'a&b']) assert.throws(() => s.sessionFile(bad), /invalid/);
});

test('login: SESSION off, default or named', () => {
  for (const v of [undefined, '', ' ', '0', 'no', 'OFF', 'false']) assert.equal(s.requestedSession(v), null);
  for (const v of ['yes', 'y', 'on', '1', 'true', 'YES']) assert.equal(s.requestedSession(v).name, '');
  assert.equal(s.requestedSession('operator').file, path.join(s.FOLDER, 'session-operator.json'));
});

test('login: activeSession warns and continues without a session if the file is missing', () => {
  const warnings = [];
  assert.equal(s.activeSession('nonexistent-role-xyz', (m) => warnings.push(m)), null);
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /npm run login -- --name nonexistent-role-xyz/);
  assert.equal(s.activeSession('', () => assert.fail('does not warn if it is off')), null);
});

test('login: activeSession returns the file if it exists', () => {
  const name = `test-${process.pid}`;
  const file = s.sessionFile(name);
  const createdFolder = !fs.existsSync(s.FOLDER);
  fs.mkdirSync(s.FOLDER, { recursive: true });
  fs.writeFileSync(file, '{"cookies":[],"origins":[]}');
  try {
    assert.equal(s.activeSession(name), file);
  } finally {
    fs.rmSync(file, { force: true });
    if (createdFolder) fs.rmSync(s.FOLDER, { recursive: true, force: true });
  }
});

test('login: npm run login arguments', () => {
  assert.deepEqual(parseArgs([]), { url: '', name: '' });
  assert.deepEqual(parseArgs(['--name', 'admin', '--url', 'https://a.com/login']), { url: 'https://a.com/login', name: 'admin' });
  assert.throws(() => parseArgs(['--url', 'ftp://a.com']), /invalid URL/);
  assert.throws(() => parseArgs(['--name']), /missing value/);
  assert.throws(() => parseArgs(['--name', 'a b']), /invalid/);
  assert.throws(() => parseArgs(['--other']), /unknown/);
});
