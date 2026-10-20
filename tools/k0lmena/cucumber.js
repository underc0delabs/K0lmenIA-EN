// Cucumber configuration (dynamic).
//
// Migrated from cucumber.json to JavaScript so the parallelism can be toggled
// from the environment (.env). The profile shape is otherwise identical.
//
// PARALLEL env var:
//   (empty) | 0 | 1 | false | off | no  -> sequential (single process)
//   on | true | yes                     -> auto (one worker per CPU core)
//   N (>1)                              -> N parallel workers
require('./env'); // single .env at the k0lmenIA root

const resolveParallel = () => {
  const raw = (process.env.PARALLEL ?? '').trim().toLowerCase();
  if (!raw || ['0', '1', 'false', 'off', 'no'].includes(raw)) return 0;
  if (['on', 'true', 'yes', 'auto'].includes(raw)) {
    // "auto": use the number of logical CPUs (min 2).
    const cpus = require('os').cpus()?.length || 2;
    return Math.max(2, cpus);
  }
  const n = Number(raw);
  return Number.isFinite(n) && n > 1 ? Math.floor(n) : 0;
};

const parallel = resolveParallel();

// REPORT_DIR: folder for the web suite's reports and evidence (reports/web by default). It is used,
// for example, by cross-browser to run one browser per folder without overwriting the last npm test.
const dirWeb = (process.env.REPORT_DIR ?? '').trim() || 'reports/web';

// TAGS env var: filters scenarios by tag (e.g. TAGS=@US-001). Empty = all.
// Scenarios tagged @blocked (steps that could not be mapped) never run.
const rawTags = (process.env.TAGS ?? '').trim();
const tags = rawTags ? `(${rawTags}) and not @blocked` : 'not @blocked';

// Steps shared by all suites: scenario variables, database checks and email checks.
const commonSteps = ['tools/variables.ts', 'tools/db/db.steps.ts', 'tools/emails/emails.steps.ts'];

const common = {
  requireModule: ['ts-node/register'],
  timeout: 60000,
  tags,
  formatOptions: {
    snippetInterface: 'async-await',
  },
};

module.exports = {
  web: {
    ...common,
    retry: 1,
    paths: ['web/features/*.feature'],
    require: ['web/steps/*.ts', ...commonSteps],
    parallel,
    format: [
      ['html', `${dirWeb}/front-report.html`],
      'summary',
      'progress-bar',
      ['json', `${dirWeb}/cucumber-report.json`],
    ],
  },

  api: {
    ...common,
    paths: ['api/features/*.feature'],
    require: ['api/steps/*.ts', ...commonSteps],
    parallel,
    format: [
      ['html', 'reports/api/api-report.html'],
      'summary',
      'progress-bar',
      'json:reports/api/cucumber-report.json',
    ],
  },

  // Debug always runs sequentially so breakpoints / logs are readable.
  // Its reports go to reports/debug: the web report reads every .json in reports/web and would mix them.

  debug: {
    ...common,
    paths: ['web/features/*.feature'],
    require: ['tools/debug/debugHook.ts', 'web/steps/*.ts', ...commonSteps],
    parallel: 0,
    format: [
      ['html', 'reports/debug/front-report-debug.html'],
      'summary',
      'progress-bar',
      'json:reports/debug/cucumber-report-debug.json',
    ],
  },
};
