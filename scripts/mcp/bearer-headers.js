#!/usr/bin/env node
// Generic headersHelper for remote MCP connectors that accept a token as Bearer (see CONNECTORS.md).
//
// Usage (in catalog.json):
//   "headersHelper": "node scripts/mcp/bearer-headers.js <connector> <VARIABLE> [--optional]"
//
// Takes <VARIABLE> from the environment or, if it's not there, from the root .env, and prints
// {"Authorization": "Bearer <token>"} to stdout. With --optional, if the variable is empty it prints {}
// and the connector is authorized with your account (OAuth) from /mcp. Without --optional, if it's
// missing it stops with a clear message. The token is never shown.
const { variable } = require('./read-env');

const [connector, name, ...rest] = process.argv.slice(2);
if (!connector || !/^[A-Z_][A-Z0-9_]*$/.test(name || '')) {
  console.error('bearer-headers: usage: node scripts/mcp/bearer-headers.js <connector> <VARIABLE> [--optional]');
  process.exit(1);
}
const optional = rest.includes('--optional');
const token = variable(name);

if (token) {
  process.stdout.write(JSON.stringify({ Authorization: `Bearer ${token}` }));
} else if (optional) {
  process.stdout.write('{}');
} else {
  console.error(`${connector}: ${name} is missing from the root .env (see .env.example and CONNECTORS.md).`);
  process.exit(1);
}
