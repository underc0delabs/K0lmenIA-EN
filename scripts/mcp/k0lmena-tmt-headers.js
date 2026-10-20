#!/usr/bin/env node
// headersHelper for the k0lmena-tmt MCP connector (see CONNECTORS.md).
// Takes K0LMENA_TMT_TOKEN from the environment or, if it's not there, from the repo's root .env, and
// prints the authorization header as JSON to stdout. The token is never written
// to .mcp.json or shown on screen.
const { variable } = require('./read-env');

const token = variable('K0LMENA_TMT_TOKEN');

if (!token) {
  console.error('k0lmena-tmt: K0LMENA_TMT_TOKEN is missing from the root .env (see .env.example and CONNECTORS.md).');
  process.exit(1);
}
process.stdout.write(JSON.stringify({ Authorization: `Bearer ${token}` }));
