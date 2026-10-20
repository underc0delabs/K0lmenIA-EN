// tools/db/index.js
//
// Database access for k0lmenIA: used by the CLI (tools/db/cli.js, data-verifier
// agent) and the Cucumber steps (tools/db/db.steps.ts).
//
// Engines: PostgreSQL, MySQL / MariaDB, SQL Server and MongoDB.
// Named connections, from the root .env:
//
//   DB_CONNECTIONS=main,payments          (the first one is the default connection)
//   DB_MAIN_ENGINE=postgres            postgres | mysql | mariadb | sqlserver | mongodb
//   DB_MAIN_URL=                      optional: full URL (replaces host/port/database/user/password)
//   DB_MAIN_HOST=  _PORT=  _DATABASE=  _USER=  _PASSWORD=
//   DB_MAIN_SSL=no                    no | yes (encrypts and verifies the certificate) | no-verify (encrypts and accepts
//                                          self-signed certificates: test environments only)
//   DB_MAIN_SSL_CA=                   optional: .pem file of your own CA (verifies without using no-verify)
//   DB_MAIN_WRITE=no              yes = allows writing (always with explicit confirmation)
//   DB_MAIN_PRODUCTION=no             yes = never writes, even if WRITE=yes
//
// Safety:
//   - Reads run inside a transaction that is always discarded (ROLLBACK)
//     and in READ ONLY mode where the engine allows it: even if a "read" query
//     had side effects, they don't stick.
//   - A statement is considered a write if it has INSERT, UPDATE, DELETE, DDL, etc.
//     Writing requires WRITE=yes, a non-production connection and confirmation.
//   - One statement per call. Parameters with "?" (never concatenate values).
'use strict';

class DbError extends Error {}

const ENGINES = {
  postgres: 'postgres', postgresql: 'postgres', pg: 'postgres',
  mysql: 'mysql', mariadb: 'mysql',
  sqlserver: 'sqlserver', mssql: 'sqlserver',
  mongodb: 'mongodb', mongo: 'mongodb',
};
const PORTS = { postgres: 5432, mysql: 3306, sqlserver: 1433, mongodb: 27017 };
const YES = (v) => ['yes', 'y', 'true', '1', 'on'].includes(String(v ?? '').trim().toLowerCase());

const number = (v, def) => (Number.isFinite(Number(v)) && String(v).trim() !== '' ? Number(v) : def);
const TIMEOUT_MS = () => number(process.env.DB_TIMEOUT_MS, 30000);
const MAX_ROWS = () => number(process.env.DB_MAX_ROWS, 50);

// ------------------------------------------------------------------ configuration
/** Connection SSL: null (unencrypted) | 'verify' | 'no-verify'. */
function sslMode(value, prefix) {
  const s = (value || '').trim().toLowerCase();
  if (!s || ['no', 'false', '0'].includes(s)) return null;
  if (['no-verify', 'unverified', 'insecure'].includes(s)) return 'no-verify';
  if (YES(s)) return 'verify';
  throw new DbError(`${prefix}SSL must be no, yes or no-verify.`);
}

/** Common TLS options: verifies the certificate unless SSL=no-verify; SSL_CA adds your own CA. */
function tlsOptions(c) {
  if (!c.ssl) return undefined;
  if (c.ssl === 'no-verify') {
    console.error(`[db] Warning: the "${c.name}" connection uses SSL without verifying the server certificate (test environments only).`);
  }
  const tls = { rejectUnauthorized: c.ssl === 'verify' };
  if (c.sslCa) tls.ca = require('fs').readFileSync(c.sslCa, 'utf8');
  return tls;
}
function connectionNames() {
  return (process.env.DB_CONNECTIONS || '').split(',').map((s) => s.trim().toLowerCase()).filter(Boolean);
}

function config(name) {
  const names = connectionNames();
  if (!names.length) throw new DbError('No connections configured: set DB_CONNECTIONS and the DB_<NAME>_* variables in the root .env.');
  const n = (name || names[0]).trim().toLowerCase();
  if (!names.includes(n)) throw new DbError(`The "${n}" connection is not in DB_CONNECTIONS (${names.join(', ')}).`);
  const p = `DB_${n.toUpperCase().replace(/[^A-Z0-9]/g, '_')}_`;
  const v = (k) => (process.env[p + k] ?? '').trim();
  const engine = ENGINES[v('ENGINE').toLowerCase()];
  if (!engine) throw new DbError(`${p}ENGINE must be postgres, mysql, mariadb, sqlserver or mongodb.`);
  const c = {
    name: n, engine, url: v('URL'),
    host: v('HOST') || 'localhost', port: number(v('PORT'), PORTS[engine]),
    database: v('DATABASE'), user: v('USER'), password: v('PASSWORD'),
    ssl: sslMode(v('SSL'), p), sslCa: v('SSL_CA'), write: YES(v('WRITE')), production: YES(v('PRODUCTION')),
  };
  if (!c.url && !c.database) throw new DbError(`${p}DATABASE (or ${p}URL) is missing in the .env.`);
  return c;
}

/** Description of a connection without secrets (for listing). */
function describe(c) {
  let target = `${c.host}:${c.port}/${c.database}`;
  if (c.url) {
    try { const u = new URL(c.url); target = `${u.hostname}${u.port ? ':' + u.port : ''}${u.pathname}`; } catch { target = '(URL)'; }
  }
  return { name: c.name, engine: c.engine, target, write: c.write && !c.production, production: c.production };
}

// ------------------------------------------------------------------ drivers
function driver(module) {
  try { return require(module); } catch {
    throw new DbError(`The "${module}" driver is missing: run "npm install" in tools/k0lmena.`);
  }
}

const clients = new Map();

async function client(c) {
  if (clients.has(c.name)) return clients.get(c.name);
  let cli;
  if (c.engine === 'postgres') {
    const { Pool, types } = driver('pg');
    // Dates exactly as stored (without converting them to the local time zone): date, timestamp, timestamptz.
    for (const oid of [1082, 1114, 1184]) types.setTypeParser(oid, (v) => v);
    cli = new Pool(c.url ? { connectionString: c.url, max: 2 } : {
      host: c.host, port: c.port, database: c.database, user: c.user, password: c.password, max: 2,
      ssl: tlsOptions(c), connectionTimeoutMillis: TIMEOUT_MS(),
    });
  } else if (c.engine === 'mysql') {
    const mysql = driver('mysql2/promise');
    cli = mysql.createPool(c.url ? { uri: c.url, connectionLimit: 2 } : {
      host: c.host, port: c.port, database: c.database, user: c.user, password: c.password, connectionLimit: 2,
      ssl: tlsOptions(c), connectTimeout: TIMEOUT_MS(), dateStrings: true,
    });
  } else if (c.engine === 'sqlserver') {
    const sql = driver('mssql');
    cli = await new sql.ConnectionPool(c.url || {
      server: c.host, port: c.port, database: c.database, user: c.user, password: c.password,
      options: { encrypt: Boolean(c.ssl), trustServerCertificate: c.ssl === 'no-verify' },
      connectionTimeout: TIMEOUT_MS(), requestTimeout: TIMEOUT_MS(), pool: { max: 2 },
    }).connect();
  } else {
    const { MongoClient } = driver('mongodb');
    const url = c.url || `mongodb://${c.user ? `${encodeURIComponent(c.user)}:${encodeURIComponent(c.password)}@` : ''}${c.host}:${c.port}/${c.database}${c.user ? '?authSource=admin' : ''}`;
    const tls = c.ssl ? { tls: true, tlsAllowInvalidCertificates: c.ssl === 'no-verify', ...(c.sslCa ? { tlsCAFile: c.sslCa } : {}) } : {};
    cli = await new MongoClient(url, { serverSelectionTimeoutMS: TIMEOUT_MS(), ...tls }).connect();
  }
  clients.set(c.name, cli);
  return cli;
}

async function closeAll() {
  for (const [n, cli] of clients) {
    try { await (cli.end ? cli.end() : cli.close()); } catch { /* already closed */ }
    clients.delete(n);
  }
}

// ------------------------------------------------------------------ SQL analysis
const WRITE = new Set(['insert', 'update', 'delete', 'merge', 'upsert', 'replace', 'truncate', 'drop', 'alter', 'create',
  'grant', 'revoke', 'rename', 'call', 'exec', 'execute', 'copy', 'lock', 'vacuum', 'reindex', 'cluster', 'set', 'into',
  'load', 'handler', 'do', 'comment', 'refresh', 'backup', 'restore', 'kill', 'shutdown', 'dbcc', 'bulk', 'openrowset']);
const READ_START = new Set(['select', 'with', 'show', 'describe', 'desc', 'explain', 'values', 'table']);

/** SQL without comments, literals or quoted identifiers (to classify it). */
function cleanSQL(sql) {
  return sql
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/--[^\n]*/g, ' ')
    .replace(/'(?:[^']|'')*'/g, "''")
    .replace(/"(?:[^"]|"")*"/g, '""')
    .replace(/`[^`]*`/g, '``')
    .replace(/\[[^\]]*\]/g, '[]');
}

function analyzeSQL(sql) {
  const clean = cleanSQL(sql).trim().replace(/;\s*$/, '');
  if (!clean) throw new DbError('The query is empty.');
  if (clean.includes(';')) throw new DbError('One statement per query (no ";" in between).');
  const lower = clean.toLowerCase();
  const tokens = [...lower.matchAll(/[a-z_][a-z0-9_$]*/g)].map((m) => ({
    word: m[0],
    // A word followed by "(" is a function (REPLACE(...), MySQL's INSERT(...)), not a statement.
    func: /^\s*\(/.test(lower.slice(m.index + m[0].length)),
  }));
  const words = tokens.map((t) => t.word);
  const write = !READ_START.has(words[0]) || tokens.some((t) => !t.func && WRITE.has(t.word));
  return { write, first: words[0] };
}

/** Replaces the "?" (outside literals) with the engine's placeholder. */
function placeholders(sql, engine) {
  if (engine === 'mysql') return sql;
  let i = 0, output = '', quote = null;
  for (const ch of sql) {
    if (quote) { if (ch === quote) quote = null; output += ch; continue; }
    if (ch === "'" || ch === '"') { quote = ch; output += ch; continue; }
    if (ch === '?') { i += 1; output += engine === 'postgres' ? `$${i}` : `@p${i}`; continue; }
    output += ch;
  }
  return output;
}

// ------------------------------------------------------------------ values and masking
// Also matches common Spanish column names (clave, contraseña, tarjeta, cbu): masking errs on the safe side.
const SENSITIVE = /pass|clave|contrase|secret|token|hash|salt|api_?key|tarjeta|card|cvv|cbu|iban|ssn|pin$/i;
function isSensitive(field) {
  const extra = (process.env.DB_SENSITIVE_COLUMNS || '').split(',').map((s) => s.trim().toLowerCase()).filter(Boolean);
  return SENSITIVE.test(field) || extra.includes(String(field).toLowerCase());
}

function normalize(v) {
  if (v === null || v === undefined) return null;
  if (typeof v === 'bigint') return v.toString();
  if (v instanceof Date) return v.toISOString();
  if (Buffer.isBuffer(v)) return `<binary ${v.length} bytes>`;
  if (v && v._bsontype === 'ObjectId') return v.toString();
  if (v && v._bsontype === 'Decimal128') return v.toString();
  if (Array.isArray(v)) return v.map(normalize);
  if (typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, normalize(x)]));
  return v;
}

function mask(row) {
  if (Array.isArray(row)) return row.map(mask);
  if (!row || typeof row !== 'object') return row;
  return Object.fromEntries(Object.entries(row).map(([k, v]) => [k, isSensitive(k) && v !== null ? '****' : mask(v)]));
}

// ------------------------------------------------------------------ write permissions
function verifyWrite(c, confirmed) {
  if (c.production) throw new DbError(`The "${c.name}" connection is marked as production: writing is not allowed.`);
  if (!c.write) throw new DbError(`The "${c.name}" connection is read-only. To write, set DB_${c.name.toUpperCase()}_WRITE=yes in the .env.`);
  if (!confirmed) throw new DbError('Writing to the database requires explicit confirmation (--confirm).');
}

// ------------------------------------------------------------------ SQL
/**
 * Runs a SQL statement.
 * @returns {{columns: string[], rows: object[], affected: number|null, ms: number, write: boolean}}
 */
async function sql(name, text, params = [], options = {}) {
  const c = config(name);
  if (c.engine === 'mongodb') throw new DbError(`"${c.name}" is MongoDB: use a collection query (filter), not SQL.`);
  const { write } = analyzeSQL(text);
  if (write && !options.write) {
    throw new DbError('The query modifies data (or doesn\'t start with SELECT/WITH/SHOW). To write, use write mode, with confirmation.');
  }
  if (write) verifyWrite(c, options.confirmed);
  const cli = await client(c);
  const q = placeholders(text, c.engine);
  const start = Date.now();
  let rows = [], columns = [], affected = null;

  if (c.engine === 'postgres') {
    const con = await cli.connect();
    try {
      await con.query(write ? 'BEGIN' : 'BEGIN TRANSACTION READ ONLY');
      await con.query(`SET LOCAL statement_timeout = ${Math.floor(TIMEOUT_MS())}`);
      const r = await con.query(q, params);
      rows = r.rows || []; columns = (r.fields || []).map((f) => f.name);
      affected = write ? r.rowCount : null;
      await con.query(write ? 'COMMIT' : 'ROLLBACK');
    } catch (e) { await con.query('ROLLBACK').catch(() => {}); throw e; } finally { con.release(); }
  } else if (c.engine === 'mysql') {
    const con = await cli.getConnection();
    try {
      await con.query(write ? 'START TRANSACTION' : 'START TRANSACTION READ ONLY');
      const [r, fields] = await con.query({ sql: q, timeout: TIMEOUT_MS() }, params);
      if (Array.isArray(r)) { rows = r; columns = (fields || []).map((f) => f.name); } else { affected = r.affectedRows; }
      await con.query(write ? 'COMMIT' : 'ROLLBACK');
    } catch (e) { await con.query('ROLLBACK').catch(() => {}); throw e; } finally { con.release(); }
  } else {
    const mssql = driver('mssql');
    const tx = new mssql.Transaction(cli);
    await tx.begin();
    try {
      const req = new mssql.Request(tx);
      params.forEach((p, i) => req.input(`p${i + 1}`, p));
      const r = await req.query(q);
      rows = r.recordset || [];
      columns = rows.length ? Object.keys(rows[0]) : Object.keys((r.recordset && r.recordset.columns) || {});
      affected = write ? (r.rowsAffected || []).reduce((a, b) => a + b, 0) : null;
      await (write ? tx.commit() : tx.rollback());
    } catch (e) { await tx.rollback().catch(() => {}); throw e; }
  }
  if (!columns.length && rows.length) columns = Object.keys(rows[0]);
  return { columns, rows: rows.map(normalize), affected, ms: Date.now() - start, write };
}

// ------------------------------------------------------------------ MongoDB
const MONGO_READ = ['find', 'findOne', 'countDocuments', 'count', 'aggregate', 'distinct'];
const MONGO_WRITE = ['insertOne', 'insertMany', 'updateOne', 'updateMany', 'replaceOne', 'deleteOne', 'deleteMany'];

/**
 * Operation on a MongoDB collection.
 * o: { collection, operation, filter, projection, order, limit, pipeline, field, document, changes }
 */
async function mongo(name, o, options = {}) {
  const c = config(name);
  if (c.engine !== 'mongodb') throw new DbError(`"${c.name}" is ${c.engine}: use SQL.`);
  const op = o.operation || 'find';
  if (!MONGO_READ.includes(op) && !MONGO_WRITE.includes(op)) {
    throw new DbError(`Unsupported MongoDB operation: ${op}. Read: ${MONGO_READ.join(', ')}. Write: ${MONGO_WRITE.join(', ')}.`);
  }
  const write = MONGO_WRITE.includes(op) || (op === 'aggregate' && JSON.stringify(o.pipeline || []).match(/"\$(out|merge)"/));
  if (write) {
    if (!options.write) throw new DbError(`"${op}" modifies data: use write mode, with confirmation.`);
    verifyWrite(c, options.confirmed);
  }
  if (!o.collection) throw new DbError('The collection is missing.');
  const cli = await client(c);
  const col = cli.db(c.database || undefined).collection(o.collection);
  const filter = o.filter || {};
  const maxTimeMS = TIMEOUT_MS();
  const start = Date.now();
  let rows = [], affected = null;
  switch (op) {
    case 'find': {
      let cur = col.find(filter, { projection: o.projection, maxTimeMS });
      if (o.order) cur = cur.sort(o.order);
      rows = await cur.limit(o.limit || MAX_ROWS() + 1).toArray();
      break;
    }
    case 'findOne': { const d = await col.findOne(filter, { projection: o.projection, maxTimeMS }); rows = d ? [d] : []; break; }
    case 'count': case 'countDocuments': rows = [{ total: await col.countDocuments(filter, { maxTimeMS }) }]; break;
    case 'distinct': rows = (await col.distinct(o.field, filter, { maxTimeMS })).map((v) => ({ [o.field]: v })); break;
    case 'aggregate': rows = await col.aggregate(o.pipeline || [], { maxTimeMS }).toArray(); break;
    case 'insertOne': affected = (await col.insertOne(o.document)).acknowledged ? 1 : 0; break;
    case 'insertMany': affected = (await col.insertMany(o.document)).insertedCount; break;
    case 'updateOne': affected = (await col.updateOne(filter, o.changes)).modifiedCount; break;
    case 'updateMany': affected = (await col.updateMany(filter, o.changes)).modifiedCount; break;
    case 'replaceOne': affected = (await col.replaceOne(filter, o.document)).modifiedCount; break;
    case 'deleteOne': affected = (await col.deleteOne(filter)).deletedCount; break;
    case 'deleteMany': affected = (await col.deleteMany(filter)).deletedCount; break;
  }
  rows = rows.map(normalize);
  const columns = [...new Set(rows.flatMap((f) => Object.keys(f)))];
  return { columns, rows, affected, ms: Date.now() - start, write: !!write };
}

// ------------------------------------------------------------------ checks (used by the steps)
const IDENT = /^[A-Za-z_][\w$]*(\.[A-Za-z_][\w$]*)*$/;
function quoteIdent(ident, engine) {
  if (!IDENT.test(ident)) throw new DbError(`Invalid table or field name: "${ident}".`);
  const [a, b] = engine === 'postgres' ? ['"', '"'] : engine === 'mysql' ? ['`', '`'] : ['[', ']'];
  return ident.split('.').map((p) => a + p + b).join('.');
}

const NULL_VALUE = /^\(?null\)?$/i;

/** Type-tolerant MongoDB filter: "5" matches 5 or "5"; "true" matches true or "true"; 24 hex matches ObjectId. */
function mongoValue(v) {
  if (v === null || NULL_VALUE.test(String(v))) return null;
  const s = String(v);
  const options = [s];
  if (/^-?\d+(\.\d+)?$/.test(s)) options.push(Number(s));
  if (/^(true|false)$/i.test(s)) options.push(s.toLowerCase() === 'true');
  if (/^[a-f0-9]{24}$/i.test(s)) { try { const { ObjectId } = driver('mongodb'); options.push(new ObjectId(s)); } catch { /* no driver */ } }
  return options.length > 1 ? { $in: options } : s;
}

/**
 * Finds records by field equality.
 * conditions: [{ field, value }] (value "(null)" = IS NULL)
 * @returns {{ total: number, rows: object[], query: string }}
 */
async function find(name, table, conditions, limit = 5) {
  const c = config(name);
  if (c.engine === 'mongodb') {
    const filter = Object.fromEntries(conditions.map(({ field, value }) => [field, mongoValue(value)]));
    const cli = await client(c);
    const col = cli.db(c.database || undefined).collection(table);
    const total = await col.countDocuments(filter, { maxTimeMS: TIMEOUT_MS() });
    const rows = (await col.find(filter, { maxTimeMS: TIMEOUT_MS() }).limit(limit).toArray()).map(normalize);
    return { total, rows, query: `db.${table}.find(${JSON.stringify(filter)})` };
  }
  const params = [];
  const clauses = conditions.map(({ field, value }) => {
    if (value === null || NULL_VALUE.test(String(value))) return `${quoteIdent(field, c.engine)} IS NULL`;
    params.push(value);
    return `${quoteIdent(field, c.engine)} = ?`;
  });
  const where = clauses.length ? ` WHERE ${clauses.join(' AND ')}` : '';
  const t = quoteIdent(table, c.engine);
  const count = await sql(name, `SELECT COUNT(*) AS total FROM ${t}${where}`, params);
  const total = Number(Object.values(count.rows[0] || { total: 0 })[0]);
  const queryRows = c.engine === 'sqlserver' ? `SELECT TOP ${limit} * FROM ${t}${where}` : `SELECT * FROM ${t}${where} LIMIT ${limit}`;
  const { rows } = await sql(name, queryRows, params);
  return { total, rows, query: `${queryRows.replace(/ LIMIT \d+$/, '').replace(/TOP \d+ /, '')}  [${params.map(String).join(', ')}]` };
}

/** Lists tables (or collections) and, with a table, its columns. */
async function schema(name, table) {
  const c = config(name);
  if (c.engine === 'mongodb') {
    const db = (await client(c)).db(c.database || undefined);
    if (!table) return { type: 'collections', rows: (await db.listCollections().toArray()).map((x) => ({ collection: x.name })).sort((a, b) => a.collection.localeCompare(b.collection)) };
    const sample = await db.collection(table).find({}).limit(20).toArray();
    const fields = new Map();
    for (const d of sample) for (const [k, v] of Object.entries(d)) {
      const type = v === null ? 'null' : Array.isArray(v) ? 'array' : v && v._bsontype ? v._bsontype : v instanceof Date ? 'date' : typeof v;
      fields.set(k, new Set([...(fields.get(k) || []), type]));
    }
    return { type: `fields of ${table} (sample of ${sample.length} documents)`, rows: [...fields].map(([field, types]) => ({ field, types: [...types].join(' | ') })) };
  }
  let q, params = [];
  if (!table) {
    q = {
      postgres: "SELECT table_schema AS schema_name, table_name AS table_name FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema') ORDER BY 1, 2",
      mysql: 'SELECT table_name AS table_name FROM information_schema.tables WHERE table_schema = DATABASE() ORDER BY 1',
      sqlserver: 'SELECT TABLE_SCHEMA AS schema_name, TABLE_NAME AS table_name FROM INFORMATION_SCHEMA.TABLES ORDER BY 1, 2',
    }[c.engine];
  } else {
    const parts = table.split('.');
    const tableName = parts.pop();
    params = [tableName];
    const schemaFilter = parts.length ? (params.push(parts[0]), ' AND table_schema = ?') : '';
    q = {
      postgres: `SELECT column_name AS column_name, data_type AS data_type, is_nullable AS nullable FROM information_schema.columns WHERE table_name = ?${schemaFilter} ORDER BY ordinal_position`,
      mysql: `SELECT column_name AS column_name, column_type AS data_type, is_nullable AS nullable FROM information_schema.columns WHERE table_name = ? AND table_schema = DATABASE() ORDER BY ordinal_position`,
      sqlserver: `SELECT COLUMN_NAME AS column_name, DATA_TYPE AS data_type, IS_NULLABLE AS nullable FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ?${schemaFilter.replace('table_schema', 'TABLE_SCHEMA')} ORDER BY ORDINAL_POSITION`,
    }[c.engine];
    if (c.engine === 'mysql') params = [tableName];
  }
  const r = await sql(name, q, params);
  return { type: table ? `columns of ${table}` : 'tables', rows: r.rows };
}

/** Tests the connection with a trivial query. */
async function testConnection(name) {
  const c = config(name);
  const start = Date.now();
  if (c.engine === 'mongodb') await (await client(c)).db(c.database || undefined).command({ ping: 1 });
  else await sql(name, 'SELECT 1 AS ok');
  return { ...describe(c), ms: Date.now() - start };
}

module.exports = {
  DbError, connectionNames, config, describe, sql, mongo, find, schema, testConnection, closeAll,
  analyzeSQL, placeholders, mask, isSensitive, MAX_ROWS,
};
