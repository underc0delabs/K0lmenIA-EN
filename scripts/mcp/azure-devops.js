#!/usr/bin/env node
// Launcher for the azure-devops MCP connector (see CONNECTORS.md).
// Reads the Azure DevOps configuration from the environment or, if it's not there, from the root .env,
// and starts Microsoft's official server (@azure-devops/mcp) over stdio. The PAT is passed to the
// server only as an environment variable (PERSONAL_ACCESS_TOKEN, base64-encoded as the server expects);
// it never ends up in .mcp.json and is never printed.
//
// Only the MCP server talks on stdout: this script's messages go to stderr.
const { variable } = require('./read-env');
const { launchNpx } = require('./launch');

function exitWithError(message) {
  console.error(`azure-devops: ${message} (see .env.example and CONNECTORS.md).`);
  process.exit(1);
}

const organization = variable('ADO_ORGANIZATION');
const pat = variable('ADO_PAT');
const authentication = variable('ADO_AUTHENTICATION') || 'pat';
const domains = (variable('ADO_DOMAINS') || 'core work work-items repositories test-plans wiki search')
  .split(/[\s,]+/)
  .filter(Boolean);

if (!organization) exitWithError('ADO_ORGANIZATION is missing from the root .env');
if (!/^[A-Za-z0-9][A-Za-z0-9-]*$/.test(organization)) {
  exitWithError('ADO_ORGANIZATION must be just the organization name (e.g. "my-company"), not the URL');
}
if (!['pat', 'interactive', 'azcli', 'env', 'envvar'].includes(authentication)) {
  exitWithError(`ADO_AUTHENTICATION="${authentication}" is not valid; use pat, interactive, azcli, env or envvar`);
}
if (authentication === 'pat' && !pat) exitWithError('ADO_PAT is missing from the root .env');
const invalidDomain = domains.find((d) => !/^[a-z-]+$/.test(d));
if (invalidDomain) exitWithError(`ADO_DOMAINS has an invalid value: "${invalidDomain}"`);

const env = { ...process.env };
if (authentication === 'pat') {
  // The server expects base64 of "<email>:<pat>"; the email can be any non-empty value.
  env.PERSONAL_ACCESS_TOKEN = Buffer.from(`k0lmenia:${pat}`).toString('base64');
}
const project = variable('ADO_PROJECT');
const team = variable('ADO_TEAM');
if (project) env.ado_mcp_project = project;
if (team) env.ado_mcp_team = team;

const args = [organization, '-a', authentication, '-d', ...domains];
const tenant = variable('ADO_TENANT');
if (tenant) {
  if (!/^[A-Za-z0-9.-]+$/.test(tenant)) exitWithError('ADO_TENANT must be the tenant ID (GUID) or domain');
  args.push('-t', tenant);
}

launchNpx('azure-devops', '@azure-devops/mcp', args, env);
