#!/usr/bin/env node
// k0lmenIA setup wizard (npm run configure).
//
// Asks a few questions in English, with numbered options, and gets everything ready:
//   1. creates the .env (if it doesn't exist) and fills in the app under test;
//   2. asks which tools the team uses (stories, test cases, code, designs);
//   3. asks only for the data of those tools (tokens aren't shown while you type them);
//   4. saves everything to the .env and activates the connectors that are needed.
//
// You can run it as many times as you want: it shows what's already set and Enter keeps it.
// For advanced use (activating or deactivating a specific connector) there's still npm run connector.
const fs = require('fs');
const path = require('path');
const readline = require('readline');

const ROOT = path.resolve(__dirname, '..');
const ENV = process.env.K0LMENA_ENV_FILE || path.join(ROOT, '.env');
const EXAMPLE = path.join(ROOT, '.env.example');

// ------------------------------------------------------------------ what gets asked
// Each option: the connectors it activates, the fixed values it writes and the data it asks for.
// A data item: { key, text, secret?, optional?, default?, help? }.
const JIRA_URL = { key: 'JIRA_BASE_URL', text: 'Your Jira URL', help: 'e.g. https://my-company.atlassian.net' };
const JIRA_EMAIL = { key: 'JIRA_EMAIL', text: 'Your Jira email' };
const JIRA_TOKEN = { key: 'JIRA_API_TOKEN', text: 'Jira API token', secret: true, help: 'create it at https://id.atlassian.com/manage-profile/security/api-tokens' };
const ADO = [
  { key: 'ADO_ORGANIZATION', text: 'Azure DevOps organization', help: 'just the name: the one in https://dev.azure.com/<organization>' },
  { key: 'ADO_PAT', text: 'Azure DevOps Personal Access Token', secret: true, help: 'User settings > Personal access tokens' },
  { key: 'ADO_PROJECT', text: 'Azure DevOps project', optional: true },
];
const JIRA_PROJECT = { key: 'MANAGEMENT_PROJECT', text: 'Jira project key', help: 'e.g. PROJ' };
const OAUTH = 'No data needed: the first time you use it, Claude asks you to sign in with your account.';

const STEPS = [
  {
    id: 'stories',
    title: 'Where are the user stories?',
    options: [
      { name: 'Jira', data: [JIRA_URL], note: 'Jira is already connected. The first time you use it, Claude asks you to sign in with your account.' },
      { name: 'Azure DevOps (Boards)', connectors: ['azure-devops'], data: ADO },
      { name: 'Linear', connectors: ['linear'], note: OAUTH },
      { name: 'ClickUp', connectors: ['clickup'], note: OAUTH },
      { name: 'monday.com', connectors: ['monday'], note: OAUTH },
      { name: 'Trello', connectors: ['trello'], note: OAUTH },
      { name: 'Notion', connectors: ['notion'], note: OAUTH },
      { name: 'Shortcut', connectors: ['shortcut'], note: OAUTH },
      { name: 'YouTrack', connectors: ['youtrack'], data: [
        { key: 'YOUTRACK_URL', text: 'YouTrack URL', help: 'e.g. https://my-company.youtrack.cloud' },
        { key: 'YOUTRACK_TOKEN', text: 'YouTrack token', secret: true }] },
      { name: 'Asana', connectors: ['asana'], data: [
        { key: 'ASANA_CLIENT_ID', text: 'Client ID of the Asana MCP app' },
        { key: 'ASANA_CLIENT_SECRET', text: 'Client secret of the Asana MCP app', secret: true }],
        note: 'Asana requires creating your own MCP app (see CONNECTORS.md).' },
      { name: 'In files (I put them in input/stories)', note: 'Copy the stories as .md or .txt into input/stories/.' },
    ],
  },
  {
    id: 'cases',
    title: 'Where do you keep the test cases?',
    options: [
      { name: 'In Excel (no tool)', note: 'Test cases are generated as a spreadsheet in output/test-cases/.' },
      { name: 'Xray Cloud', fixed: { MANAGEMENT_TOOL: 'xray-cloud' }, data: [JIRA_PROJECT,
        { key: 'XRAY_CLOUD_CLIENT_ID', text: 'Xray Client ID', help: 'Xray > Global Settings > API Keys' },
        { key: 'XRAY_CLOUD_CLIENT_SECRET', text: 'Xray Client secret', secret: true },
        JIRA_URL, JIRA_EMAIL, JIRA_TOKEN] },
      { name: 'Xray Server / Data Center', fixed: { MANAGEMENT_TOOL: 'xray-dc' }, data: [JIRA_PROJECT,
        { key: 'XRAY_DC_URL', text: 'Your Jira URL', help: 'e.g. https://jira.my-company.com' },
        { key: 'XRAY_DC_TOKEN', text: 'Jira Personal Access Token', secret: true }] },
      { name: 'QMetry for Jira (QTM4J)', connectors: ['qtm4j'], fixed: { MANAGEMENT_TOOL: 'qtm4j' }, data: [JIRA_PROJECT,
        { key: 'QTM4J_API_KEY', text: 'QMetry Open API key', secret: true, help: 'QMetry > Configuration > Open API' }] },
      { name: 'AIO Tests', connectors: ['aio-tests'], fixed: { MANAGEMENT_TOOL: 'aio' }, data: [JIRA_PROJECT,
        { key: 'AIO_API_TOKEN', text: 'AIO Tests API token', secret: true, help: 'AIO Tests > My Settings > API Token' },
        { key: 'AIO_MCP_URL', text: 'AIO MCP server URL', help: 'AIO Tests > My Settings > MCP Authorization' }] },
      { name: 'Azure Test Plans', connectors: ['azure-devops'], data: ADO },
      { name: 'k0lmenaTMT', connectors: ['k0lmena-tmt'], data: [
        { key: 'K0LMENA_TMT_TOKEN', text: 'k0lmenaTMT personal token (kolm_pat_...)', secret: true },
        { key: 'K0LMENA_TMT_URL', text: 'k0lmenaTMT URL', optional: true, default: 'http://localhost:4000/api/v1/mcp' }] },
    ],
  },
  {
    id: 'code',
    title: 'Where is the application code? (optional: used to document the project)',
    options: [
      { name: "I'd rather not connect it (or I'll do it later)" },
      { name: 'GitHub', connectors: ['github'], fixed: { REPO_PROVIDER: 'github' }, data: [
        { key: 'REPO_NAME', text: 'Repository', help: 'owner/repo, e.g. my-company/my-app (several, comma-separated)' },
        { key: 'GITHUB_TOKEN', text: 'Read-only GitHub token', secret: true, help: 'https://github.com/settings/personal-access-tokens' }] },
      { name: 'GitLab', connectors: ['gitlab'], fixed: { REPO_PROVIDER: 'gitlab' }, data: [
        { key: 'REPO_NAME', text: 'Repository', help: 'group/project (several, comma-separated)' },
        { key: 'GITLAB_URL', text: 'GitLab URL', optional: true, default: 'https://gitlab.com' }],
        note: 'No token: the first time you use it, Claude asks you to sign in with your account.' },
      { name: 'Azure Repos', connectors: ['azure-devops'], fixed: { REPO_PROVIDER: 'azure-repos' }, data: [
        { key: 'REPO_NAME', text: 'Repository', help: 'project/repo' }, ...ADO] },
    ],
  },
  {
    id: 'figma',
    title: 'Do you use Figma for designs?',
    options: [
      { name: 'No' },
      { name: 'Yes', connectors: ['figma'], note: OAUTH },
    ],
  },
];

const APP = [
  { key: 'APP_URL', text: "URL of the application you're going to test", help: 'e.g. https://staging.my-app.com · a test environment, not production' },
  { key: 'APP_USER', text: 'Test user to sign in to the app', optional: true },
  { key: 'APP_PASSWORD', text: "That user's password", secret: true, optional: true },
];

// ------------------------------------------------------------------ the .env
const LINE = (key) => new RegExp(`^[ \\t]*#?[ \\t]*(?:export[ \\t]+)?${key}[ \\t]*=.*$`, 'm');

/** Current value of a key (active lines only, without #). */
function readValue(text, key) {
  const m = new RegExp(`^[ \\t]*(?:export[ \\t]+)?${key}[ \\t]*=[ \\t]*(.*?)[ \\t]*$`, 'm').exec(text);
  if (!m) return '';
  const v = m[1];
  if (/^(['"]).*\1$/.test(v)) return v.slice(1, -1);
  return v.replace(/\s+#.*$/, '');
}

const format = (value) => (/[\s#'"]/.test(value) ? `"${value.replace(/"/g, '')}"` : value);

/**
 * Writes KEY=value: replaces the active line or, if there isn't one, the first commented one ("uncomments"
 * it in place, keeping its explanation above); if the key isn't there, appends it at the end.
 */
function setValue(text, key, value) {
  const line = `${key}=${format(value)}`;
  const active = new RegExp(`^[ \\t]*(?:export[ \\t]+)?${key}[ \\t]*=.*$`, 'm');
  if (active.test(text)) return text.replace(active, () => line);
  if (LINE(key).test(text)) return text.replace(LINE(key), () => line);
  const end = text.endsWith('\n') || !text ? '' : '\n';
  const title = text.includes('# --- Added by npm run configure ---') ? '' : '\n# --- Added by npm run configure ---\n';
  return `${text}${end}${title}${line}\n`;
}

/** What to do for the chosen options: connectors, fixed values and data to ask for (no duplicates). */
function plan(chosen) {
  const connectors = new Set();
  const fixed = {};
  const data = [];
  const notes = [];
  for (const o of chosen) {
    for (const c of o.connectors || []) connectors.add(c);
    Object.assign(fixed, o.fixed || {});
    for (const d of o.data || []) if (!data.some((x) => x.key === d.key)) data.push(d);
    if (o.note) notes.push(`${o.name}: ${o.note}`);
  }
  return { connectors: [...connectors], fixed, data, notes };
}

// ------------------------------------------------------------------ the terminal
function createTerminal() {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  const original = rl._writeToOutput.bind(rl);
  let hidden = false;
  rl._writeToOutput = (s) => {
    if (!hidden) return original(s);
    if (/[\r\n]/.test(s)) original('\n'); // what you type isn't shown
  };
  const ask = (text, { secret = false } = {}) => new Promise((resolve) => {
    rl.question(text, (r) => { hidden = false; resolve(r.trim()); });
    hidden = secret;
  });
  return { rl, ask };
}

const bold = (s) => (process.stdout.isTTY ? `\x1b[1m${s}\x1b[0m` : s);
const gray = (s) => (process.stdout.isTTY ? `\x1b[2m${s}\x1b[0m` : s);
const green = (s) => (process.stdout.isTTY ? `\x1b[32m${s}\x1b[0m` : s);

async function choose(t, step) {
  console.log(`\n${bold(step.title)}`);
  step.options.forEach((o, i) => console.log(`  ${i + 1}. ${o.name}`));
  for (;;) {
    const r = await t.ask('Pick a number: ');
    const n = Number(r);
    if (Number.isInteger(n) && n >= 1 && n <= step.options.length) return step.options[n - 1];
    console.log(`Type a number from 1 to ${step.options.length}.`);
  }
}

async function askValue(t, d, current) {
  const help = d.help ? gray(` (${d.help})`) : '';
  let hint = '';
  if (current) hint = d.secret ? gray(' [already set: Enter keeps it]') : gray(` [${current}: Enter keeps it]`);
  else if (d.default) hint = gray(` [${d.default}]`);
  else if (d.optional) hint = gray(' [optional: Enter to skip]');
  for (;;) {
    const r = await t.ask(`  ${d.text}${help}${hint}: `, { secret: d.secret });
    if (r) return r;
    if (current) return current;
    if (d.default) return d.default;
    if (d.optional) return '';
    console.log("  This value is required. (If you don't have it yet, stop with Ctrl+C and run npm run configure again when you do.)");
  }
}

async function main() {
  if (!process.stdin.isTTY) {
    console.log('npm run configure asks questions: run it in a terminal (for example, the VS Code one: Terminal > New Terminal).');
    process.exit(1);
  }
  console.log(bold('\nk0lmenIA setup'));
  console.log("I'll ask you a few questions and get everything ready. Enter keeps what was already set. Ctrl+C cancels without saving.");

  let text;
  if (fs.existsSync(ENV)) text = fs.readFileSync(ENV, 'utf8');
  else {
    text = fs.existsSync(EXAMPLE) ? fs.readFileSync(EXAMPLE, 'utf8') : '';
    console.log(gray('(There was no .env: creating it from .env.example.)'));
  }

  const t = createTerminal();
  const values = {};
  try {
    console.log(`\n${bold('Your application')}`);
    for (const d of APP) values[d.key] = await askValue(t, d, readValue(text, d.key).replace(/^https:\/\/your-test-app\.com$|^your_(user|password)$/, ''));

    const chosen = [];
    for (const step of STEPS) chosen.push(await choose(t, step));
    const p = plan(chosen);
    if (p.data.length) console.log(`\n${bold('Data for the tools you chose')}`);
    for (const d of p.data) {
      const current = readValue(text, d.key).replace(/^https:\/\/your-site\.atlassian\.net$/, '');
      values[d.key] = await askValue(t, d, current);
    }
    Object.assign(values, p.fixed);

    for (const [key, value] of Object.entries(values)) if (value) text = setValue(text, key, value);
    fs.writeFileSync(ENV, text, 'utf8');
    console.log(`\n${green('✓')} Saved the configuration to the .env (it isn't pushed to the repository).`);

    if (p.connectors.length) {
      console.log(`\n${bold('Connectors')}`);
      const { activate } = require('./mcp/connector.js');
      activate(p.connectors);
    }
    for (const n of p.notes) console.log(`· ${n}`);

    console.log(`\n${bold('Done.')} Next steps:`);
    console.log('  1. Close Claude Code and open it again (so it picks up the changes).');
    console.log('  2. Type /mcp to see the connectors. The ones that say "needs authentication" ask you to sign in.');
    console.log('  3. If you want to check that everything is fine: npm run doctor');
    console.log('  4. To get started, ask Claude for something, for example: "analyze story PROJ-123".\n');
  } finally {
    t.rl.close();
  }
}

if (require.main === module) {
  main().catch((e) => {
    console.error(`\nI couldn't finish the setup: ${e.message}`);
    process.exit(1);
  });
}

module.exports = { main, setValue, readValue, plan, STEPS, APP };
