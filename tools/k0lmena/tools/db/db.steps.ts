// tools/db/db.steps.ts
//
// Generic steps (in English) to verify data in the database from the
// web and API tests (they run with npm test, no tokens). Always read-only.
//
// Connection: the first one in DB_CONNECTIONS, or a named one ("in the database "payments"").
// Values: {variable} uses what was saved in the scenario (e.g. an id from the API response)
// or a .env variable. "(null)" checks for NULL.
// Wait: if the data is not there yet (asynchronous processes), it retries until DB_WAIT_MS (default 5000).
import '../../env';
import { Before, When, Then, AfterAll, DataTable } from '@cucumber/cucumber';
import { variables, interpolate } from '../variables';
// eslint-disable-next-line @typescript-eslint/no-var-requires
const db = require('./index');

type Condition = { field: string; value: string };
type Result = { columns: string[]; rows: Record<string, unknown>[] };

let lastQuery: Result | undefined;
const NULL_VALUE = /^\(?null\)?$/i;
const WAIT_MS = () => Number(process.env.DB_WAIT_MS ?? 5000) || 0;

Before(() => { lastQuery = undefined; });
AfterAll(async () => { await db.closeAll(); });

/** Compares a database value with the expected one (text from the .feature) without being strict about the type. */
function matches(actual: unknown, expected: string): boolean {
  if (NULL_VALUE.test(expected)) return actual === null || actual === undefined;
  if (actual === null || actual === undefined) return false;
  const s = typeof actual === 'object' ? JSON.stringify(actual) : String(actual);
  if (s === expected) return true;
  if (/^-?\d+(\.\d+)?$/.test(expected) && s.trim() !== '' && Number(s) === Number(expected)) return true;
  if (/^(true|false)$/i.test(expected)) return ['true', '1'].includes(s.toLowerCase()) === (expected.toLowerCase() === 'true');
  if (/^\d{4}-\d{2}-\d{2}/.test(expected) && s.startsWith(expected)) return true; // date (with or without time)
  return false;
}

const conditions = (field: string, value: string): Condition[] => [{ field, value: interpolate(value) }];

function fromTable(table: DataTable): Condition[] {
  const rows = table.raw().filter((f) => f.length >= 2);
  const noHeader = rows.length && rows[0][0].trim().toLowerCase() === 'field' ? rows.slice(1) : rows;
  return noHeader.map(([field, value]) => ({ field: field.trim(), value: interpolate(value.trim()) }));
}

/** Retries the search until the condition is met or DB_WAIT_MS runs out. */
async function waitForSearch(connection: string | undefined, table: string, cond: Condition[], ok: (r: any) => boolean) {
  const deadline = Date.now() + WAIT_MS();
  let r = await db.find(connection, table, cond);
  while (!ok(r) && Date.now() < deadline) {
    await new Promise((res) => setTimeout(res, 500));
    r = await db.find(connection, table, cond);
  }
  return r;
}

function evidence(world: any, title: string, query: string, rows: unknown[]) {
  const body = `${title}\n${query}\n\n${JSON.stringify(db.mask(rows.slice(0, 5)), null, 2)}`;
  return world.attach(body, 'text/plain');
}

const describeCond = (cond: Condition[]) => cond.map((c) => `${c.field} = ${c.value}`).join(' and ');

// ------------------------------------------------------------------ record count
async function verifyCount(world: any, connection: string | undefined, count: number, table: string, cond: Condition[]) {
  const r = await waitForSearch(connection, table, cond, (x) => x.total === count);
  await evidence(world, `Database: ${r.total} record(s) in ${table}`, r.query, r.rows);
  if (r.total !== count) {
    throw new Error(`Expected ${count} record(s) in "${table}" where ${describeCond(cond)} and there are ${r.total}.`);
  }
}

Then('the database has {int} record(s) in {string} where:', async function (count: number, table: string, t: DataTable) {
  await verifyCount(this, undefined, count, table, fromTable(t));
});
Then('the database {string} has {int} record(s) in {string} where:', async function (connection: string, count: number, table: string, t: DataTable) {
  await verifyCount(this, connection, count, table, fromTable(t));
});

// ------------------------------------------------------------------ exists / does not exist
async function verifyExists(world: any, connection: string | undefined, mustExist: boolean, table: string, cond: Condition[]) {
  const r = await waitForSearch(connection, table, cond, (x) => (x.total > 0) === mustExist);
  await evidence(world, `Database: ${r.total} record(s) in ${table}`, r.query, r.rows);
  if ((r.total > 0) !== mustExist) {
    throw new Error(mustExist
      ? `There is no record in "${table}" where ${describeCond(cond)}.`
      : `There are ${r.total} record(s) in "${table}" where ${describeCond(cond)} and there should be none.`);
  }
}

Then('the database has a record in {string} where {string} is {string}', async function (table: string, field: string, value: string) {
  await verifyExists(this, undefined, true, table, conditions(field, value));
});
Then('the database {string} has a record in {string} where {string} is {string}', async function (connection: string, table: string, field: string, value: string) {
  await verifyExists(this, connection, true, table, conditions(field, value));
});
Then('the database has no record in {string} where {string} is {string}', async function (table: string, field: string, value: string) {
  await verifyExists(this, undefined, false, table, conditions(field, value));
});
Then('the database {string} has no record in {string} where {string} is {string}', async function (connection: string, table: string, field: string, value: string) {
  await verifyExists(this, connection, false, table, conditions(field, value));
});

// ------------------------------------------------------------------ values of a record
async function verifyRecord(world: any, connection: string | undefined, table: string, field: string, value: string, t: DataTable) {
  const cond = conditions(field, value);
  const expected = fromTable(t);
  const fulfills = (r: any) => r.total === 1 && expected.every((e) => matches(r.rows[0]?.[e.field], e.value));
  const r = await waitForSearch(connection, table, cond, fulfills);
  await evidence(world, `Database: ${table} record`, r.query, r.rows);
  if (r.total === 0) throw new Error(`There is no record in "${table}" where ${describeCond(cond)}.`);
  if (r.total > 1) throw new Error(`There are ${r.total} records in "${table}" where ${describeCond(cond)}; the filter must identify exactly one.`);
  const row = r.rows[0];
  const errors = expected.filter((e) => !matches(row[e.field], e.value)).map((e) => {
    if (!(e.field in row)) return `the field "${e.field}" does not exist in "${table}"`;
    const actual = db.isSensitive(e.field) ? '****' : JSON.stringify(row[e.field]);
    return `"${e.field}" is ${actual} and "${e.value}" was expected`;
  });
  if (errors.length) throw new Error(`"${table}" record where ${describeCond(cond)}: ${errors.join('; ')}.`);
}

Then('the {string} record where {string} is {string} has:', async function (table: string, field: string, value: string, t: DataTable) {
  await verifyRecord(this, undefined, table, field, value, t);
});
Then('in the database {string} the {string} record where {string} is {string} has:', async function (connection: string, table: string, field: string, value: string, t: DataTable) {
  await verifyRecord(this, connection, table, field, value, t);
});

// ------------------------------------------------------------------ free query (read-only)
async function runQuery(world: any, connection: string | undefined, text: string) {
  const q = interpolate(text.trim());
  const c = db.config(connection);
  if (c.engine === 'mongodb') {
    let o: any;
    try { o = JSON.parse(q); } catch { throw new Error('In MongoDB the query is a JSON: {"collection": "...", "filter": {...}}'); }
    lastQuery = await db.mongo(connection, o);
  } else {
    lastQuery = await db.sql(connection, q, []);
  }
  await evidence(world, `Database: query (${lastQuery!.rows.length} rows)`, q, lastQuery!.rows);
}

const query = (): Result => {
  if (!lastQuery) throw new Error('No database query has been run in this scenario yet.');
  return lastQuery;
};

When('I query the database:', async function (text: string) { await runQuery(this, undefined, text); });
When('I query the database {string}:', async function (connection: string, text: string) { await runQuery(this, connection, text); });

Then('the query returns {int} row(s)', function (n: number) {
  const total = query().rows.length;
  if (total !== n) throw new Error(`The query returned ${total} row(s) and ${n} were expected.`);
});
Then('the query returns at least {int} row(s)', function (n: number) {
  const total = query().rows.length;
  if (total < n) throw new Error(`The query returned ${total} row(s) and at least ${n} were expected.`);
});
Then('the field {string} of the query is {string}', function (field: string, value: string) {
  const row = query().rows[0];
  if (!row) throw new Error('The query returned no rows.');
  const expected = interpolate(value);
  if (!matches(row[field], expected)) {
    throw new Error(`"${field}" is ${db.isSensitive(field) ? '****' : JSON.stringify(row[field])} and "${expected}" was expected.`);
  }
});
When('I save the field {string} of the query as {string}', function (field: string, name: string) {
  const row = query().rows[0];
  if (!row || !(field in row)) throw new Error(`The query does not have the field "${field}".`);
  variables[name] = row[field];
});
