#!/usr/bin/env node
// Activates and deactivates k0lmenIA's optional MCP connectors (see CONNECTORS.md).
//
//   npm run connector                        lists the connectors and which ones you have active
//   npm run connector -- activate azure-devops [qtm4j ...]
//   npm run connector -- deactivate azure-devops
//
// The optional ones aren't in .mcp.json so that Claude Code starts without asking for approvals.
// "activate" registers them with `claude mcp add-json --scope local`: they're just for you, in this
// project, and aren't versioned. Credentials still come from the .env (the scripts in
// scripts/mcp/ read them at startup). After activating or deactivating, restart Claude Code.
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const { variable } = require('./read-env');

const ROOT = path.resolve(__dirname, '..', '..');
const CATALOG = JSON.parse(fs.readFileSync(path.join(__dirname, 'catalog.json'), 'utf8')).connectors;
const DEFAULTS = Object.keys(JSON.parse(fs.readFileSync(path.join(ROOT, '.mcp.json'), 'utf8')).mcpServers);

// Variables that "activate" checks (it only warns: the connector can be activated before the .env is complete).
const REQUIRED = {
  'azure-devops': () => (/^(interactive|azcli|env|envvar)$/i.test(variable('ADO_AUTHENTICATION')) ? ['ADO_ORGANIZATION'] : ['ADO_ORGANIZATION', 'ADO_PAT']),
  qtm4j: () => ['QTM4J_API_KEY'],
  qmetry: () => ['QMETRY_API_KEY'],
  'aio-tests': () => ['AIO_MCP_URL', 'AIO_API_TOKEN'],
  'k0lmena-tmt': () => ['K0LMENA_TMT_TOKEN'],
  github: () => ['GITHUB_TOKEN'],
  asana: () => ['ASANA_CLIENT_ID', 'ASANA_CLIENT_SECRET'],
  youtrack: () => ['YOUTRACK_URL', 'YOUTRACK_TOKEN'],
};

/**
 * Replaces ${VAR:-value} in the URL with the value from the .env (or the environment), if defined: that way,
 * for example, GITLAB_URL is taken from the .env. If it isn't defined, it stays as is and Claude Code resolves it
 * from the environment.
 */
function withEnvVariables(url) {
  return url.replace(/\$\{([A-Z_][A-Z0-9_]*)(:-[^}]*)?\}/g, (all, name) => {
    const value = variable(name);
    return value ? value.replace(/\/+$/, '') : all;
  });
}

/** The repo's scripts with absolute paths: that way the connector starts even if you open Claude Code in another folder. */
function withAbsolutePaths(server) {
  const abs = (r) => path.join(ROOT, r).split(path.sep).join('/');
  const s = JSON.parse(JSON.stringify(server));
  if (Array.isArray(s.args)) s.args = s.args.map((a) => (a.startsWith('scripts/') ? abs(a) : a));
  if (s.headersHelper) s.headersHelper = s.headersHelper.replace(/scripts\/[\w./-]+/, (r) => `"${abs(r)}"`);
  if (s.url) s.url = withEnvVariables(s.url);
  return s;
}

/**
 * How to register a connector. By default, `claude mcp add-json` with the catalog entry.
 * Servers that don't accept dynamic OAuth client registration (Asana V2) have in the catalog
 * "oauth": {clientId, clientSecret, callbackPort} with the NAMES of the .env variables: they're
 * registered with `claude mcp add --client-id ... --client-secret --callback-port ...`. The secret goes
 * through the MCP_CLIENT_SECRET variable (if Claude Code doesn't pick it up, it asks for it in the terminal,
 * hidden) and is stored in the system keychain, never in a file.
 */
function activationCommand(name, entry, server) {
  if (!entry.oauth) {
    return { args: ['mcp', 'add-json', name, JSON.stringify(server), '--scope', 'local'] };
  }
  const { clientId, clientSecret, callbackPort } = entry.oauth;
  const id = variable(clientId);
  if (!id) throw new Error(`${clientId} is missing from the root .env`);
  if (!/^[\w.-]+$/.test(id)) throw new Error(`${clientId} has an invalid value`);
  const env = { ...process.env };
  const secret = clientSecret && variable(clientSecret);
  if (secret) env.MCP_CLIENT_SECRET = secret;
  return {
    args: ['mcp', 'add', '--transport', server.type, '--client-id', id, '--client-secret',
      '--callback-port', String(callbackPort), '--scope', 'local', name, server.url],
    env,
    interactive: true,
  };
}

/** Connectors registered with local scope for this project (from ~/.claude.json; names only). */
function localActive() {
  try {
    const data = JSON.parse(fs.readFileSync(path.join(os.homedir(), '.claude.json'), 'utf8'));
    const key = ROOT.split(path.sep).join('/').toLowerCase();
    const project = Object.entries(data.projects || {}).find(([k]) => k.toLowerCase() === key);
    return Object.keys((project && project[1].mcpServers) || {});
  } catch {
    return null; // couldn't tell
  }
}

// interactive: the output goes to the terminal (for example, if Claude Code asks for the client secret).
function claude(args, { env, interactive } = {}) {
  const base = { encoding: 'utf8', cwd: ROOT, env: env || process.env, ...(interactive ? { stdio: 'inherit' } : {}) };
  let r = spawnSync('claude', args, base);
  if (r.error && process.platform === 'win32') {
    // Installed with npm: claude.cmd needs a shell (the JSON goes with its quotes escaped for cmd).
    const line = ['claude', ...args.map((a) => (/[\s"{}]/.test(a) ? `"${a.replace(/"/g, '\\"')}"` : a))].join(' ');
    r = spawnSync(line, { ...base, shell: true });
  }
  if (r.error) {
    console.error("Can't find the \"claude\" command. Install Claude Code (see README) and try again.");
    process.exit(1);
  }
  return r;
}

function list() {
  const active = localActive();
  console.log('k0lmenIA MCP connectors\n');
  console.log('Enabled for everyone (in .mcp.json):');
  for (const n of DEFAULTS) console.log(`  ✓ ${n}`);
  console.log('\nOptional (activate with: npm run connector -- activate <name>):');
  for (const [n, c] of Object.entries(CATALOG)) {
    const mark = active === null ? '?' : active.includes(n) ? '✓' : ' ';
    console.log(`  ${mark} ${n.padEnd(14)} ${c.description}\n      variables: ${c.variables}`);
  }
  if (active === null) console.log("\n(Couldn't read which connectors you have active: try  claude mcp list)");
  console.log('\nAfter activating or deactivating, restart Claude Code and check with /mcp.');
}

function activate(names) {
  for (const n of names) {
    const c = CATALOG[n];
    if (!c) {
      console.error(`"${n}" is not in the catalog. Options: ${Object.keys(CATALOG).join(', ')}.`);
      process.exitCode = 1;
      continue;
    }
    const server = withAbsolutePaths(c.server);
    let command;
    try {
      command = activationCommand(n, c, server);
    } catch (e) {
      console.error(`Could not activate ${n}: ${e.message} (see .env.example and CONNECTORS.md).`);
      process.exitCode = 1;
      continue;
    }
    const unresolved = (server.url || '').match(/\$\{([A-Z_][A-Z0-9_]*)\}/);
    if (unresolved) console.log(`  Warning: ${unresolved[1]} is missing from the .env; the URL stays as ${server.url} (fill it in and activate again).`);
    if ((localActive() || []).includes(n)) claude(['mcp', 'remove', n, '--scope', 'local']); // it gets replaced
    const r = claude(command.args, command);
    if (r.status !== 0) {
      console.error(`Could not activate ${n}: ${((r.stderr || r.stdout || '').trim()) || `claude exited with code ${r.status}`}`);
      process.exitCode = 1;
      continue;
    }
    const missing = (REQUIRED[n] ? REQUIRED[n]() : []).filter((v) => !variable(v));
    console.log(`✓ ${n} activated (just for you, in this project).`);
    if (missing.length) console.log(`  Still to fill in the .env: ${missing.join(', ')} (see .env.example).`);
  }
  console.log('Restart Claude Code and check with /mcp.');
}

function deactivate(names) {
  for (const n of names) {
    const r = claude(['mcp', 'remove', n, '--scope', 'local']);
    console.log(r.status === 0 ? `✓ ${n} deactivated.` : `${n} was not active.`);
  }
}

if (require.main === module) {
  const [action, ...names] = process.argv.slice(2);
  if (!action || action === 'list') list();
  else if (action === 'activate' && names.length) activate(names);
  else if (action === 'deactivate' && names.length) deactivate(names);
  else {
    console.error('Usage: npm run connector -- [list | activate <name> [...] | deactivate <name> [...]]');
    process.exit(1);
  }
}

module.exports = { activate, activationCommand, withAbsolutePaths, withEnvVariables, CATALOG };
