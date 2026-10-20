// Tests for the npm run configure wizard: write the .env without breaking it and build the plan from the choices.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const cfg = require(path.join(ROOT, 'scripts/configure.js'));
const CATALOG = JSON.parse(fs.readFileSync(path.join(ROOT, 'scripts/mcp/catalog.json'), 'utf8')).connectors;

test('configure: fills an active line, uncomments the commented one or appends at the end', () => {
  let t = '# URL\nAPP_URL=https://old.test\n# Token\n# GITHUB_TOKEN=\nOTHER=1\n';
  t = cfg.setValue(t, 'APP_URL', 'https://new.test');
  t = cfg.setValue(t, 'GITHUB_TOKEN', 'ghp_123');
  t = cfg.setValue(t, 'NEW', 'with space');
  assert.equal(t, '# URL\nAPP_URL=https://new.test\n# Token\nGITHUB_TOKEN=ghp_123\nOTHER=1\n\n# --- Added by npm run configure ---\nNEW="with space"\n');
  assert.equal(cfg.readValue(t, 'GITHUB_TOKEN'), 'ghp_123');
  assert.equal(cfg.readValue(t, 'NEW'), 'with space');
  assert.equal(cfg.readValue('# GITHUB_TOKEN=x\n', 'GITHUB_TOKEN'), '', 'a commented line is not a value');
  assert.equal(cfg.readValue(cfg.setValue('', 'A', '$x'), 'A'), '$x');
});

test('configure: the plan gathers connectors and data without duplicates', () => {
  const step = (id) => cfg.STEPS.find((p) => p.id === id);
  const op = (id, name) => step(id).options.find((o) => o.name.startsWith(name));
  const p = cfg.plan([op('stories', 'Azure DevOps'), op('cases', 'Azure Test Plans'), op('code', 'GitHub'), op('figma', 'Yes')]);
  assert.deepEqual(p.connectors, ['azure-devops', 'github', 'figma']);
  assert.deepEqual(p.fixed, { REPO_PROVIDER: 'github' });
  const keys = p.data.map((d) => d.key);
  assert.equal(new Set(keys).size, keys.length, 'each value is asked only once');
  assert.ok(keys.includes('ADO_PAT') && keys.includes('GITHUB_TOKEN'));
});

test('configure: every connector in the wizard exists in the catalog', () => {
  for (const step of cfg.STEPS) for (const o of step.options) for (const c of o.connectors || []) assert.ok(CATALOG[c], `${o.name} → ${c}`);
});

test('configure: the values it asks for are documented in .env.example', () => {
  const example = fs.readFileSync(path.join(ROOT, '.env.example'), 'utf8');
  const data = [...cfg.APP, ...cfg.STEPS.flatMap((p) => p.options.flatMap((o) => [...(o.data || []), ...Object.keys(o.fixed || {}).map((key) => ({ key }))]))];
  for (const { key } of data) assert.match(example, new RegExp(`^#? ?${key}=`, 'm'), key);
});
