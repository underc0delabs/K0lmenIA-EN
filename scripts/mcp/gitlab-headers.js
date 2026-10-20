#!/usr/bin/env node
// headersHelper for the gitlab MCP connector (GitLab's official server, /api/v4/mcp; see CONNECTORS.md).
// Without GITLAB_TOKEN it adds no authorization: you authorize with your account (OAuth) from /mcp.
// With GITLAB_TOKEN (a *fine-grained* personal access token with the "MCP tool" resource and the
// Execute permission; classic tokens are rejected with 403) it sends it as Bearer.
// It always limits the toolsets to the ones the project-documenter uses (GITLAB_TOOLSETS to change them).
// The values come from the environment or the root .env and are never shown.
const { variable } = require('./read-env');

function exitWithError(message) {
  console.error(`gitlab: ${message} (see .env.example and CONNECTORS.md).`);
  process.exit(1);
}

const token = variable('GITLAB_TOKEN');
const toolsets = variable('GITLAB_TOOLSETS') || 'meta,core,merge_requests,work_items,repository,wikis';
if (!/^[a-z_,\s]+$/.test(toolsets)) exitWithError(`GITLAB_TOOLSETS has an invalid value: "${toolsets}"`);

const headers = { 'X-Gitlab-Enabled-Mcp-Server-Toolsets': toolsets.replace(/\s+/g, '') };
if (token) headers.Authorization = `Bearer ${token}`;
process.stdout.write(JSON.stringify(headers));
