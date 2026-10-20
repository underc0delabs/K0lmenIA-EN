#!/usr/bin/env node
// tools/db/cli.js — database queries for the data-verifier agent.
//
// From tools/k0lmena:   npm run db -- <command> [options]
//
//   connections                                lists the .env connections and tests them
//   schema     [--db X] [--table T]            tables (or collections) and the columns of a table
//   query      [--db X] --sql "SELECT ..." [--param V]...          read-only SQL
//   query      [--db X] --collection C [--operation find] [--filter JSON] [--projection JSON]
//              [--order JSON] [--pipeline JSON] [--field C]         MongoDB (read)
//   exists     [--db X] --table T --where field=value [--where ...] are there records? (value "(null)" = NULL)
//   write      [--db X] --sql "UPDATE ..." --confirm              write (requires DB_X_WRITE=yes)
//   write      [--db X] --collection C --operation updateMany --filter JSON --changes JSON --confirm
//
//   --max N           rows to show (default DB_MAX_ROWS or 50)
//   --format table|json|md   (default table)
//   Any value starting with @ is read from a file: --sql @query.sql --filter @filter.json
//
// Sensitive columns (password, token, hash, card, …) are shown as ****.
'use strict';
const fs = require('fs');
const db = require('./index');

function readArgs(argv) {
  const pos = [], o = { param: [], where: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) { pos.push(a); continue; }
    const k = a.slice(2);
    if (k === 'confirm') { o.confirm = true; continue; }
    let v = argv[++i];
    if (v === undefined) throw new db.DbError(`The value of --${k} is missing.`);
    if (v.startsWith('@') && fs.existsSync(v.slice(1))) v = fs.readFileSync(v.slice(1), 'utf8');
    if (k === 'param' || k === 'where') o[k].push(v); else o[k] = v;
  }
  return { command: pos[0], o };
}

const json = (text, name) => {
  if (text === undefined) return undefined;
  try { return JSON.parse(text); } catch (e) { throw new db.DbError(`--${name} is not valid JSON: ${e.message}`); }
};

function cell(v) {
  if (v === null || v === undefined) return 'NULL';
  const s = typeof v === 'object' ? JSON.stringify(v) : String(v);
  return s.length > 60 ? s.slice(0, 57) + '...' : s;
}

function print(title, columns, rows, format, max, extra = '') {
  const total = rows.length;
  const visible = db.mask(rows.slice(0, max));
  if (format === 'json') {
    console.log(JSON.stringify({ title, columns, rows: visible, total, truncated: total > max, ...(extra ? { note: extra } : {}) }, null, 2));
    return;
  }
  const cols = columns.length ? columns : [...new Set(visible.flatMap((f) => Object.keys(f)))];
  console.log(title);
  if (!cols.length || !visible.length) { console.log('(no rows)'); if (extra) console.log(extra); return; }
  const data = visible.map((f) => cols.map((c) => cell(f[c])));
  if (format === 'md') {
    console.log(`| ${cols.join(' | ')} |\n| ${cols.map(() => '---').join(' | ')} |`);
    data.forEach((d) => console.log(`| ${d.map((x) => x.replace(/\|/g, '\\|')).join(' | ')} |`));
  } else {
    const widths = cols.map((c, i) => Math.max(c.length, ...data.map((d) => d[i].length)));
    const line = (vals) => vals.map((v, i) => v.padEnd(widths[i])).join('  ');
    console.log(line(cols)); console.log(widths.map((a) => '-'.repeat(a)).join('  '));
    data.forEach((d) => console.log(line(d)));
  }
  console.log(`${total > max ? `Showing ${max} of ${total} rows` : `${total} row${total === 1 ? '' : 's'}`}${extra ? ` · ${extra}` : ''}`);
}

async function main() {
  const { command, o } = readArgs(process.argv.slice(2));
  const format = o.format || 'table';
  const max = Number(o.max) || db.MAX_ROWS();

  switch (command) {
    case 'connections': {
      const rows = [];
      for (const n of db.connectionNames()) {
        try { const r = await db.testConnection(n); rows.push({ ...r, status: `OK (${r.ms} ms)` }); } catch (e) {
          let d = {}; try { d = db.describe(db.config(n)); } catch { d = { name: n }; }
          rows.push({ ...d, status: `ERROR: ${e.message}` });
        }
      }
      if (!rows.length) throw new db.DbError('There are no connections: set DB_CONNECTIONS and DB_<NAME>_* in the root .env.');
      print('Connections', ['name', 'engine', 'target', 'write', 'production', 'status'], rows.map((f) => ({ ...f, write: f.write ? 'yes' : 'no', production: f.production ? 'yes' : 'no' })), format, 100);
      break;
    }
    case 'schema': {
      const r = await db.schema(o.db, o.table);
      print(`Schema · ${r.type}`, [], r.rows, format, 500);
      break;
    }
    case 'query':
    case 'write': {
      const write = command === 'write';
      const options = { write, confirmed: !!o.confirm };
      let r;
      if (o.collection) {
        r = await db.mongo(o.db, {
          collection: o.collection, operation: o.operation || 'find', filter: json(o.filter, 'filter'),
          projection: json(o.projection, 'projection'), order: json(o.order, 'order'), pipeline: json(o.pipeline, 'pipeline'),
          field: o.field, document: json(o.document, 'document'), changes: json(o.changes, 'changes'), limit: max + 1,
        }, options);
      } else if (o.sql) {
        r = await db.sql(o.db, o.sql, o.param, options);
      } else {
        throw new db.DbError('Specify --sql "..." or --collection C.');
      }
      if (r.write) console.log(`Write confirmed · affected rows: ${r.affected ?? 0} · ${r.ms} ms`);
      else print(`Result (${db.describe(db.config(o.db)).name})`, r.columns, r.rows, format, max, `${r.ms} ms`);
      break;
    }
    case 'exists': {
      if (!o.table || !o.where.length) throw new db.DbError('Usage: exists --table T --where field=value [--where field2=value2].');
      const conditions = o.where.map((d) => {
        const i = d.indexOf('=');
        if (i < 1) throw new db.DbError(`--where "${d}" must be field=value.`);
        return { field: d.slice(0, i).trim(), value: d.slice(i + 1) };
      });
      const r = await db.find(o.db, o.table, conditions, Math.min(max, 5));
      console.log(`${r.total > 0 ? 'EXISTS' : 'DOES NOT EXIST'} · ${r.total} record${r.total === 1 ? '' : 's'} in ${o.table} where ${conditions.map((c) => `${c.field} = ${c.value}`).join(' and ')}`);
      if (r.rows.length) print('First records', [], r.rows, format, 5);
      break;
    }
    default:
      console.log('Usage: npm run db -- <connections | schema | query | exists | write> [options]  (see tools/db/cli.js)');
      process.exitCode = command ? 2 : 0;
  }
}

main()
  .catch((e) => {
    console.error(e instanceof db.DbError ? `Error: ${e.message}` : `Database error: ${e.message}`);
    process.exitCode = 1;
  })
  .finally(() => db.closeAll());
