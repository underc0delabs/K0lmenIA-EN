// Loads the SINGLE k0lmenIA .env (the one at the repo root) for all of k0lmena.
//
// Used by run-tests.js, cucumber.js, mobile/support/wdio.conf.ts and the npm
// scripts (node -r ./env.js). To use another file (e.g. in CI): K0LMENA_ENV_FILE=path/.env
// Variables already defined in the environment take precedence over the file.
const path = require('path');

const envFile = process.env.K0LMENA_ENV_FILE
  ? path.resolve(process.env.K0LMENA_ENV_FILE)
  : path.resolve(__dirname, '../../.env');

// BASEURL defined in the terminal (e.g. BASEURL=https://other npm test) overrides APP_URL for that run.
const baseurlFromTerminal = process.env.BASEURL;

require('dotenv').config({ path: envFile, quiet: true });

// The app URL lives in a single place: APP_URL. BASEURL (the name used by the k0lmena steps and
// tools) is built from it, so both always have the same value. An old BASEURL
// in the .env is only used if APP_URL is empty.

const url = baseurlFromTerminal || process.env.APP_URL || process.env.BASEURL || '';
if (url) {
  process.env.APP_URL = url;
  process.env.BASEURL = url;
}

module.exports = { envFile };
