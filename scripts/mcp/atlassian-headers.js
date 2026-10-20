#!/usr/bin/env node
// headersHelper for the atlassian MCP connector (Jira and Confluence; see CONNECTORS.md).
// ATLASSIAN_MCP_AUTHENTICATION chooses how to connect:
//   oauth (default) → adds no headers: you authorize with your account from /mcp.
//   token           → Authorization: Basic base64(JIRA_EMAIL:JIRA_API_TOKEN), or
//                     Authorization: Bearer ATLASSIAN_API_KEY (service account).
//                     An admin has to enable the API token in Atlassian Administration
//                     > Rovo > Rovo MCP server > Authentication.
// The values come from the environment or the root .env and are never shown.
const { variable } = require('./read-env');

function exitWithError(message) {
  console.error(`atlassian: ${message} (see .env.example and CONNECTORS.md).`);
  process.exit(1);
}

const mode = (variable('ATLASSIAN_MCP_AUTHENTICATION') || 'oauth').toLowerCase();
if (mode === 'oauth') {
  process.stdout.write('{}');
} else if (mode === 'token') {
  const apiKey = variable('ATLASSIAN_API_KEY');
  const email = variable('JIRA_EMAIL');
  const token = variable('JIRA_API_TOKEN');
  if (apiKey) {
    process.stdout.write(JSON.stringify({ Authorization: `Bearer ${apiKey}` }));
  } else if (email && token) {
    const basic = Buffer.from(`${email}:${token}`).toString('base64');
    process.stdout.write(JSON.stringify({ Authorization: `Basic ${basic}` }));
  } else {
    exitWithError('with ATLASSIAN_MCP_AUTHENTICATION=token, JIRA_EMAIL and JIRA_API_TOKEN (or ATLASSIAN_API_KEY) are missing from the .env');
  }
} else {
  exitWithError(`ATLASSIAN_MCP_AUTHENTICATION="${mode}" is not valid; use oauth or token`);
}
