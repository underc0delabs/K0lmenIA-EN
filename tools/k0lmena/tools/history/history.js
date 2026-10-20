// Run history: before a new run, the previous one is MOVED to <folder>/history/<date-time>/
// with its JSON, its analysis, its report and its evidence (screenshots, videos, traces…), so its report still
// opens the same way and can be compared. The last 5 are kept (4 previous + the current one).
//
// Same logic as scripts/_history.py (which also builds the "Run evolution" section of the reports).
const fs = require('fs');
const path = require('path');

const MAX_RUNS = Number(process.env.RUN_HISTORY) > 0 ? Number(process.env.RUN_HISTORY) : 5;
const FOLDER = 'history';

function stamp(dataFile) {
  let f = null;
  try {
    const d = JSON.parse(fs.readFileSync(dataFile, 'utf8'));
    f = (!Array.isArray(d) && (d.stamp || d.date)) || null;
  } catch { /* unreadable JSON: the file date is used */ }
  if (!f) {
    const m = fs.statSync(dataFile).mtime;
    f = new Date(m.getTime() - m.getTimezoneOffset() * 60000).toISOString().slice(0, 19);
  }
  return String(f).replace(/[^0-9A-Za-z-]+/g, '-').slice(0, 19).replace(/^-+|-+$/g, '');
}

function move(source, target) {
  try {
    fs.renameSync(source, target);
  } catch (e) {
    if (e.code !== 'EXDEV' && e.code !== 'EPERM' && e.code !== 'EBUSY') throw e;
    fs.cpSync(source, target, { recursive: true });
    fs.rmSync(source, { recursive: true, force: true });
  }
}

// Moves the previous run (the `names` that exist) to history/<stamp>/ and keeps only the latest ones.
// dataFile: the run's JSON (the date comes from it); if it does not exist, there is no run to save.
function archive(folder, names, dataFile, maxRuns = MAX_RUNS) {
  const data = path.join(folder, dataFile);
  if (!fs.existsSync(data) || fs.statSync(data).size <= 4) return null; // there was no run ("[]" or empty)
  const base = path.join(folder, FOLDER, stamp(data));
  let target = base;
  for (let n = 2; fs.existsSync(target); n++) target = `${base}-${n}`;
  fs.mkdirSync(target, { recursive: true });
  for (const name of names) {
    const src = path.join(folder, name);
    if (fs.existsSync(src)) move(src, path.join(target, name));
  }
  prune(folder, maxRuns - 1);
  return target;
}

function prune(folder, keep) {
  const dir = path.join(folder, FOLDER);
  if (!fs.existsSync(dir)) return;
  const runs = fs.readdirSync(dir, { withFileTypes: true }).filter((d) => d.isDirectory()).map((d) => d.name).sort();
  for (const old of runs.slice(0, Math.max(0, runs.length - keep))) {
    fs.rmSync(path.join(dir, old), { recursive: true, force: true });
  }
}

module.exports = { archive, prune, stamp, MAX_RUNS, FOLDER };
