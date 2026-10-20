// Saved browser session (npm run login): where it is stored and when it is used.
//
// It is shared by the k0lmena web suites (web/hooks/hook.ts) and the agents' browser
// (scripts/mcp/playwright.js), so it lives at the repo root: .auth/ (gitignored).
//   .auth/session.json           the default session
//   .auth/session-<name>.json    one per role or user (npm run login -- --name admin)
//
// SESSION in the .env decides whether it is used:
//   empty / 0 / no / off   -> not used (each scenario starts without a session)
//   yes / on / 1 / true    -> .auth/session.json
//   <name>                 -> .auth/session-<name>.json
// No dependencies: it is also loaded by the MCP launcher, which has no node_modules.
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const FOLDER = path.join(ROOT, '.auth');
const VALID_NAME = /^[\w-]+$/;

const OFF = ['', '0', 'no', 'off', 'false'];
const DEFAULT = ['yes', 'y', 'on', '1', 'true'];

/** Absolute path of the session file for <name> (or the default one, with no name). */
function sessionFile(name) {
  if (!name) return path.join(FOLDER, 'session.json');
  if (!VALID_NAME.test(name)) throw new Error(`invalid session name: "${name}" (only letters, numbers, - and _)`);
  return path.join(FOLDER, `session-${name}.json`);
}

/** Which session SESSION asks for: null if it is off; otherwise { name, file }. */
function requestedSession(value) {
  const v = String(value ?? '').trim();
  if (OFF.includes(v.toLowerCase())) return null;
  const name = DEFAULT.includes(v.toLowerCase()) ? '' : v;
  return { name, file: sessionFile(name) };
}

/**
 * File to use according to SESSION, or null if it is off. If it was requested but the file does not exist,
 * it warns (once) with `warn` and returns null: the run continues without a session instead of stopping.
 */
function activeSession(value, warn = () => {}) {
  const requested = requestedSession(value);
  if (!requested) return null;
  if (!fs.existsSync(requested.file)) {
    const how = requested.name ? `npm run login -- --name ${requested.name}` : 'npm run login';
    warn(`SESSION=${String(value).trim()} but ${path.relative(ROOT, requested.file)} does not exist: continuing without a session. Save it with "${how}".`);
    return null;
  }
  return requested.file;
}

module.exports = { ROOT, FOLDER, sessionFile, requestedSession, activeSession };
