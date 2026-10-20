// Reads the root .env for the MCP connector scripts (see CONNECTORS.md).
// Claude Code doesn't read the .env for the ${VARIABLE} references in .mcp.json: these scripts take each
// value from the environment and, if it's not there, from the .env. They never print the values.
const fs = require('fs');
const path = require('path');

function readEnv(file) {
  const values = {};
  if (!fs.existsSync(file)) return values;
  // Without BOM (files saved on Windows); same rules as scripts/_env.py and dotenv.
  for (const line of fs.readFileSync(file, 'utf8').replace(/^﻿/, '').split(/\r?\n/)) {
    const m = line.match(/^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/);
    if (!m) continue;
    let value = m[2];
    if (/^(['"]).*\1$/.test(value)) value = value.slice(1, -1);
    else value = value.replace(/\s+#.*$/, '');
    values[m[1]] = value;
  }
  return values;
}

const envFile = process.env.K0LMENA_ENV_FILE || path.resolve(__dirname, '..', '..', '.env');
const fromFile = readEnv(envFile);

// A variable's value: first the environment, then the .env. Empty = not defined.
function variable(name) {
  return process.env[name] || fromFile[name] || '';
}

module.exports = { variable };
