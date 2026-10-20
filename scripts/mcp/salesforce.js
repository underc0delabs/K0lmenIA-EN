#!/usr/bin/env node
// Launcher for the salesforce MCP connector (see CONNECTORS.md).
// Starts the official Salesforce DX server (@salesforce/mcp) over stdio against ONE org: the one in
// SALESFORCE_ORG, which has to be in SALESFORCE_AUTHORIZED_ORGS (never ALLOW_ALL_ORGS).
// The org is authorized beforehand with the CLI (sf org login web --alias <alias>); the server uses that
// local authorization, so no token travels through here.
//
// Only read and test tools are enabled: the SOQL query (data toolset) and Apex tests
// (run_apex_test). No metadata (deploy/retrieve) and no users (assigning permissions).
// No telemetry to Salesforce.
//
// Only the MCP server talks on stdout: this script's messages go to stderr.
const { variable } = require('./read-env');
const { launchNpx } = require('./launch');

function exitWithError(message) {
  console.error(`salesforce: ${message} (see .env.example and CONNECTORS.md).`);
  process.exit(1);
}

const org = variable('SALESFORCE_ORG');
const authorized = variable('SALESFORCE_AUTHORIZED_ORGS').split(/[\s,]+/).filter(Boolean);

if (!org) exitWithError('SALESFORCE_ORG (the org alias) is missing from the root .env');
if (!/^[\w.@+-]+$/.test(org)) exitWithError(`SALESFORCE_ORG="${org}" is not a valid alias`);
if (/^(ALLOW_ALL_ORGS|DEFAULT_TARGET_ORG|DEFAULT_TARGET_DEV_HUB)$/.test(org)) {
  exitWithError('SALESFORCE_ORG has to be the alias of a specific org, not a wildcard');
}
if (!authorized.includes(org)) exitWithError(`${org} is not in SALESFORCE_AUTHORIZED_ORGS`);

launchNpx('salesforce', '@salesforce/mcp', ['--orgs', org, '--toolsets', 'data', '--tools', 'run_apex_test', '--no-telemetry']);
