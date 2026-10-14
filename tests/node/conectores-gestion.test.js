// Tests de los conectores de herramientas de gestión de proyecto (Linear, ClickUp, monday.com, Asana,
// Trello, Notion, YouTrack, Shortcut): headersHelper genérico, activación con cliente OAuth propio y catálogo.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const RAIZ = path.resolve(__dirname, '..', '..');
const VARIABLES = /^(LINEAR_API_KEY|MONDAY_API_TOKEN|YOUTRACK_TOKEN|YOUTRACK_URL|ASANA_CLIENT_ID|ASANA_CLIENT_SECRET)$/;

function helper(args, env) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'k0-gestion-'));
  const archivo = path.join(dir, '.env');
  fs.writeFileSync(archivo, Object.entries(env).map(([k, v]) => `${k}=${v}`).join('\n'));
  const limpio = Object.fromEntries(Object.entries(process.env).filter(([k]) => !VARIABLES.test(k)));
  const r = spawnSync(process.execPath, [path.join(RAIZ, 'scripts/mcp/bearer-headers.js'), ...args],
    { encoding: 'utf8', env: { ...limpio, K0LMENA_ENV_FILE: archivo } });
  fs.rmSync(dir, { recursive: true, force: true });
  return r;
}

test('bearer-headers: token como Bearer; opcional sin token deja OAuth; obligatorio sin token corta', () => {
  const ok = helper(['linear', 'LINEAR_API_KEY', '--opcional'], { LINEAR_API_KEY: 'lin_api_prueba' });
  assert.equal(ok.status, 0, ok.stderr);
  assert.deepEqual(JSON.parse(ok.stdout), { Authorization: 'Bearer lin_api_prueba' });
  const oauth = helper(['monday', 'MONDAY_API_TOKEN', '--opcional'], {});
  assert.deepEqual(JSON.parse(oauth.stdout), {});
  const falta = helper(['youtrack', 'YOUTRACK_TOKEN'], {});
  assert.equal(falta.status, 1);
  assert.match(falta.stderr, /youtrack: falta YOUTRACK_TOKEN/);
  assert.equal(helper(['x', 'nombre-invalido'], {}).status, 1);
});

test('catálogo: los conectores de gestión de proyecto son remotos, por https y sin secretos', () => {
  const { conectores } = JSON.parse(fs.readFileSync(path.join(RAIZ, 'scripts/mcp/catalogo.json'), 'utf8'));
  for (const n of ['linear', 'clickup', 'monday', 'asana', 'trello', 'notion', 'youtrack', 'shortcut']) {
    const s = conectores[n] && conectores[n].servidor;
    assert.ok(s, `falta ${n}`);
    assert.equal(s.type, 'http', n);
    assert.match(s.url, /^(https:\/\/|\$\{[A-Z_]+\}\/)/, n);
    assert.doesNotMatch(JSON.stringify(conectores[n]), /Bearer [\w-]|token=|secret=/, n);
  }
  assert.match(conectores.linear.servidor.url, /\/readonly$/);
});

test('activación: Asana se registra con su cliente OAuth propio y el secret va por variable de entorno', () => {
  const { comandoActivacion, conRutasAbsolutas, CATALOGO } = require(path.join(RAIZ, 'scripts/mcp/conector.js'));
  const previos = { id: process.env.ASANA_CLIENT_ID, secreto: process.env.ASANA_CLIENT_SECRET };
  try {
    process.env.ASANA_CLIENT_ID = '1234567890';
    process.env.ASANA_CLIENT_SECRET = 'secreto-de-prueba';
    const c = comandoActivacion('asana', CATALOGO.asana, conRutasAbsolutas(CATALOGO.asana.servidor));
    assert.deepEqual(c.args, ['mcp', 'add', '--transport', 'http', '--client-id', '1234567890', '--client-secret',
      '--callback-port', '8080', '--scope', 'local', 'asana', 'https://mcp.asana.com/v2/mcp']);
    assert.equal(c.env.MCP_CLIENT_SECRET, 'secreto-de-prueba');
    assert.ok(!c.args.join(' ').includes('secreto-de-prueba'), 'el secret no va en la línea de comandos');
    process.env.ASANA_CLIENT_ID = '';
    assert.throws(() => comandoActivacion('asana', CATALOGO.asana, CATALOGO.asana.servidor), /falta ASANA_CLIENT_ID/);
    // El resto se registra con add-json, como siempre.
    const linear = comandoActivacion('linear', CATALOGO.linear, conRutasAbsolutas(CATALOGO.linear.servidor));
    assert.equal(linear.args[1], 'add-json');
    assert.match(JSON.parse(linear.args[3]).headersHelper, /bearer-headers\.js" linear LINEAR_API_KEY --opcional$/);
  } finally {
    for (const [k, v] of [['ASANA_CLIENT_ID', previos.id], ['ASANA_CLIENT_SECRET', previos.secreto]]) {
      if (v === undefined) delete process.env[k]; else process.env[k] = v;
    }
  }
});
