// k0lmena runner: runs the suites unattended (and without agents).
//
//   npm test                 -> web + api
//   npm test -- web          -> web only        (also: npm run test:web)
//   npm test -- api          -> api only
//   npm test -- mobile       -> mobile only (Appium / emulator / BrowserStack, see .env)
//   npm test -- all          -> web + api + mobile
//
// Filter by tag: TAGS=@US-001 npm test   (PowerShell: $env:TAGS="@US-001"; npm test)
// Exits with code != 0 if any suite fails, but always runs every requested suite.
const { spawnSync } = require('child_process');
// Loads the .env at the k0lmenIA root; the suites (child processes) inherit the variables.
require('./env');

const SUITES = {
  web: 'npx cucumber-js --profile web',
  api: 'npx cucumber-js --profile api',
  mobile: 'npx wdio run mobile/support/wdio.conf.ts',
};

const arg = (process.argv[2] || 'default').toLowerCase();
const plan = {
  default: ['web', 'api'],
  all: ['web', 'api', 'mobile'],
}[arg] || [arg];

const unknown = plan.filter((s) => !SUITES[s]);
if (unknown.length) {
  console.error(`Unknown suite: ${unknown.join(', ')}. Options: web | api | mobile | all`);
  process.exit(2);
}

// Evidence from the previous run: the report only describes the latest one, so it is cleaned up.
const path = require('path');
const fs = require('fs');
const CLEAN = {
  web: ['screenshots', 'traces', 'videos', 'evidence', 'dom'].map((d) =>
    path.resolve(__dirname, process.env.REPORT_DIR || 'reports/web', d)
  ),
  mobile: ['html/videos', 'html/evidence', 'evidence', 'screenshots'].map((d) => path.join(__dirname, 'reports/mobile', d)),
};

const { archive } = require('./tools/history/history.js');
const dirWeb = path.resolve(__dirname, process.env.REPORT_DIR || 'reports/web');
const HISTORY = {
  web: { dir: dirWeb, names: ['cucumber-report.json', 'front-report.html', 'index.html', 'features', 'screenshots', 'traces', 'videos', 'evidence', 'dom'] },
  api: { dir: path.join(__dirname, 'reports/api'), names: ['cucumber-report.json', 'api-report.html', 'index.html', 'features'] },
  mobile: { dir: path.join(__dirname, 'reports/mobile'), names: ['cucumber-report.json', 'html', 'evidence', 'screenshots'] },
};

// Evidence for passing tests: if EVIDENCE is not in the .env, you are asked (only in an
// interactive terminal; in CI or without a terminal it defaults to "screenshot").
function askForEvidence() {
  if ((process.env.EVIDENCE ?? '').trim()) return Promise.resolve();
  if (!process.stdin.isTTY || process.env.CI || !plan.some((s) => s === 'web' || s === 'mobile')) {
    process.env.EVIDENCE = 'screenshot';
    return Promise.resolve();
  }
  const rl = require('readline').createInterface({ input: process.stdin, output: process.stdout });
  const text =
    '\nWhat evidence should be saved for passing tests?\n' +
    '  1) Screenshot only\n' +
    '  2) Screenshot + GIF of the walkthrough (adds ~0.5 s per scenario)\n' +
    'Option [1]: ';
  return new Promise((resolve) =>
    rl.question(text, (r) => {
      rl.close();
      process.env.EVIDENCE = r.trim() === '2' ? 'both' : 'screenshot';
      console.log(`Evidence: ${process.env.EVIDENCE === 'both' ? 'screenshot + GIF' : 'screenshot only'}` +
        ' (to skip this question, set EVIDENCE in the root .env)');
      resolve();
    })
  );
}

// Full report (multiple-cucumber-html-reporter with the k0lmenIA theme, the one from `npm run report:<suite>`):
// it is built automatically when each suite finishes, so the reports portal links to it and not to Cucumber's basic HTML.
const REPORTS = {
  web: { json: path.join(dirWeb, 'cucumber-report.json'), cmd: 'node reports/web/report-generator.js' },
  api: { json: path.join(__dirname, 'reports/api/cucumber-report.json'), cmd: 'node reports/api/report-generator.js' },
};

function generateReport(suite) {
  const r = REPORTS[suite];
  if (!r || !fs.existsSync(r.json) || fs.statSync(r.json).size <= 4) return; // no scenarios, no report
  const { status } = spawnSync(r.cmd, { stdio: 'inherit', shell: true, cwd: __dirname });
  if (status !== 0) console.error(`[k0lmena] Could not generate the ${suite} report; Cucumber's basic one remains.`);
}

function run() {
  const results = plan.map((suite) => {
    console.log(`\n=== k0lmena: suite ${suite} ===`);
    // The previous run (report + evidence) moves to history/ (last 5) instead of being deleted.
    const h = HISTORY[suite];
    if (h) archive(h.dir, h.names, 'cucumber-report.json');
    for (const dir of CLEAN[suite] || []) fs.rmSync(dir, { recursive: true, force: true });
    const { status } = spawnSync(SUITES[suite], { stdio: 'inherit', shell: true });
    generateReport(suite);
    return { suite, ok: status === 0 };
  });

  console.log('\n=== Summary ===');
  for (const r of results) console.log(`${r.suite.padEnd(7)} ${r.ok ? 'OK' : 'FAILED'}`);
  process.exit(results.every((r) => r.ok) ? 0 : 1);
}

askForEvidence().then(run);
