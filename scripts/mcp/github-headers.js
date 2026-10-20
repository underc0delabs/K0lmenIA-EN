#!/usr/bin/env node
// headersHelper for the github MCP connector (GitHub's official remote server; see CONNECTORS.md).
// Takes GITHUB_TOKEN from the environment or, if it's not there, from the root .env, and prints the
// headers as JSON to stdout: the token as Bearer, read-only mode (X-MCP-Readonly) and the toolsets the
// project-documenter uses (GITHUB_TOOLSETS to change them). The token is never shown.
const { variable } = require('./read-env');

function exitWithError(message) {
  console.error(`github: ${message} (see .env.example and CONNECTORS.md).`);
  process.exit(1);
}

const token = variable('GITHUB_TOKEN');
const toolsets = variable('GITHUB_TOOLSETS') || 'context,repos,issues,pull_requests';

if (!token) exitWithError('GITHUB_TOKEN is missing from the root .env');
if (!/^[a-z_,\s]+$/.test(toolsets)) exitWithError(`GITHUB_TOOLSETS has an invalid value: "${toolsets}"`);

process.stdout.write(JSON.stringify({
  Authorization: `Bearer ${token}`,
  'X-MCP-Readonly': 'true',
  'X-MCP-Toolsets': toolsets.replace(/\s+/g, ''),
}));
