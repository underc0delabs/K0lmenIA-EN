// Tests for the project management tool connectors (Linear, ClickUp, monday.com, Asana,
// Trello, Notion, YouTrack, Shortcut): generic headersHelper, activation with its own OAuth client and catalog.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..', '..');
const VARIABLES = /^(LINEAR_API_KEY|MONDAY_API_TOKEN|YOUTRACK_TOKEN|YOUTRACK_URL|ASANA_CLIENT_ID|ASANA_CLIENT_SECRET)$/;

function helper(args, env) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'k0-management-'));
  const file = path.join(dir, '.env');
  fs.writeFileSync(file, Object.entries(env).map(([k, v]) => `${k}=${v}`).join('\n'));
  const clean = Object.fromEntries(Object.entries(process.env).filter(([k]) => !VARIABLES.test(k)));
  const r = spawnSync(process.execPath, [path.join(ROOT, 'scripts/mcp/bearer-headers.js'), ...args],
    { encoding: 'utf8', env: { ...clean, K0LMENA_ENV_FILE: file } });
  fs.rmSync(dir, { recursive: true, force: true });
  return r;
}

test('bearer-headers: token as Bearer; optional without a token leaves OAuth; required without a token stops', () => {
  const ok = helper(['linear', 'LINEAR_API_KEY', '--optional'], { LINEAR_API_KEY: 'lin_api_test' });
  assert.equal(ok.status, 0, ok.stderr);
  assert.deepEqual(JSON.parse(ok.stdout), { Authorization: 'Bearer lin_api_test' });
  const oauth = helper(['monday', 'MONDAY_API_TOKEN', '--optional'], {});
  assert.deepEqual(JSON.parse(oauth.stdout), {});
  const missing = helper(['youtrack', 'YOUTRACK_TOKEN'], {});
  assert.equal(missing.status, 1);
  assert.match(missing.stderr, /youtrack: YOUTRACK_TOKEN is missing/);
  assert.equal(helper(['x', 'invalid-name'], {}).status, 1);
});

test('catalog: the project management connectors are remote, over https and without secrets', () => {
  const { connectors } = JSON.parse(fs.readFileSync(path.join(ROOT, 'scripts/mcp/catalog.json'), 'utf8'));
  for (const n of ['linear', 'clickup', 'monday', 'asana', 'trello', 'notion', 'youtrack', 'shortcut']) {
    const s = connectors[n] && connectors[n].server;
    assert.ok(s, `missing ${n}`);
    assert.equal(s.type, 'http', n);
    assert.match(s.url, /^(https:\/\/|\$\{[A-Z_]+\}\/)/, n);
    assert.doesNotMatch(JSON.stringify(connectors[n]), /Bearer [\w-]|token=|secret=/, n);
  }
  assert.match(connectors.linear.server.url, /\/readonly$/);
});

test('activation: Asana is registered with its own OAuth client and the secret goes through an environment variable', () => {
  const { activationCommand, withAbsolutePaths, CATALOG } = require(path.join(ROOT, 'scripts/mcp/connector.js'));
  const previous = { id: process.env.ASANA_CLIENT_ID, secret: process.env.ASANA_CLIENT_SECRET };
  try {
    process.env.ASANA_CLIENT_ID = '1234567890';
    process.env.ASANA_CLIENT_SECRET = 'test-secret';
    const c = activationCommand('asana', CATALOG.asana, withAbsolutePaths(CATALOG.asana.server));
    assert.deepEqual(c.args, ['mcp', 'add', '--transport', 'http', '--client-id', '1234567890', '--client-secret',
      '--callback-port', '8080', '--scope', 'local', 'asana', 'https://mcp.asana.com/v2/mcp']);
    assert.equal(c.env.MCP_CLIENT_SECRET, 'test-secret');
    assert.ok(!c.args.join(' ').includes('test-secret'), 'the secret is not on the command line');
    process.env.ASANA_CLIENT_ID = '';
    assert.throws(() => activationCommand('asana', CATALOG.asana, CATALOG.asana.server), /ASANA_CLIENT_ID is missing/);
    // The rest are registered with add-json, as always.
    const linear = activationCommand('linear', CATALOG.linear, withAbsolutePaths(CATALOG.linear.server));
    assert.equal(linear.args[1], 'add-json');
    assert.match(JSON.parse(linear.args[3]).headersHelper, /bearer-headers\.js" linear LINEAR_API_KEY --optional$/);
  } finally {
    for (const [k, v] of [['ASANA_CLIENT_ID', previous.id], ['ASANA_CLIENT_SECRET', previous.secret]]) {
      if (v === undefined) delete process.env[k]; else process.env[k] = v;
    }
  }
});
