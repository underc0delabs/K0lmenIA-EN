#!/usr/bin/env node
// Generic launcher for stdio MCP connectors that read their configuration from the .env (see CONNECTORS.md).
// Claude Code doesn't read the .env for the ${VARIABLE} references in .mcp.json: this script takes each
// requested variable from the environment or, if it's not there, from the root .env, and starts the server
// with only those variables added (it doesn't pass it the rest of the .env). It never prints the values.
//
// Usage (in .mcp.json):
//   node scripts/mcp/with-env.js <connector> [--required A,B] [--optional C,D=value] -- <npm package> [args...]
// The package version is the pinned one from scripts/mcp/launch.js.
const { variable } = require('./read-env');
const { launchNpx, exitWithError } = require('./launch');

const args = process.argv.slice(2);
const separator = args.indexOf('--');
const connector = args[0];
if (!connector || separator < 1 || separator === args.length - 1) {
  console.error('with-env: usage: node scripts/mcp/with-env.js <connector> [--required A,B] [--optional C=value] -- <package> [args...]');
  process.exit(1);
}

function list(option) {
  const i = args.indexOf(option);
  return i > 0 && i < separator ? args[i + 1].split(',').filter(Boolean) : [];
}

const env = { ...process.env };
const missing = [];
for (const name of list('--required')) {
  const value = variable(name);
  if (value) env[name] = value;
  else missing.push(name);
}
for (const item of list('--optional')) {
  const [name, ...defaultValue] = item.split('=');
  const value = variable(name) || defaultValue.join('=');
  if (value) env[name] = value;
}
if (missing.length) exitWithError(connector, `${missing.join(', ')} missing from the root .env`);

const [pkg, ...rest] = args.slice(separator + 1);
launchNpx(connector, pkg, rest, env);
