#!/usr/bin/env node
// Launcher for the aio-tests MCP connector (see CONNECTORS.md).
// The AIO Tests server is remote and its URL is specific to each tenant, so it can't be hardcoded
// in .mcp.json. This script takes AIO_MCP_URL and AIO_API_TOKEN from the environment or, if they're
// not there, from the root .env, and connects it over stdio with mcp-remote. The token travels only as
// an environment variable (mcp-remote expands it into the header); it never ends up in .mcp.json or in
// the arguments.
//
// Only the MCP server talks on stdout: this script's messages go to stderr.
const { variable } = require('./read-env');
const { launchNpx } = require('./launch');

function exitWithError(message) {
  console.error(`aio-tests: ${message} (see .env.example and CONNECTORS.md).`);
  process.exit(1);
}

const url = variable('AIO_MCP_URL');
const token = variable('AIO_API_TOKEN');
if (!url) exitWithError('AIO_MCP_URL is missing from the root .env');
if (!/^https:\/\/[A-Za-z0-9.\-/_:]+$/.test(url)) exitWithError('AIO_MCP_URL is not a valid https URL');
if (!token) exitWithError('AIO_API_TOKEN is missing from the root .env');

const env = { ...process.env, AIO_AUTH_HEADER: `Bearer ${token}` };
launchNpx('aio-tests', 'mcp-remote', [url, '--header', 'Authorization:${AIO_AUTH_HEADER}'], env);
