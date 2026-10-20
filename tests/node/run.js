// Runs all the repo's Node tests (tests/node/*.test.js) with the native runner.
// It looks for the files here instead of using a glob pattern, which `node --test` only accepts since Node 21.
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const files = fs.readdirSync(__dirname).filter((f) => f.endsWith('.test.js')).map((f) => path.join(__dirname, f));
// The reports the tests build do not touch the output/index.html portal.
const r = spawnSync(process.execPath, ['--test', ...files], { stdio: 'inherit', env: { ...process.env, K0LMENIA_PORTAL: '0' } });
process.exit(r.status === null ? 1 : r.status);
