// Helpers for the API steps (api/steps/common.steps.ts), in plain JS so they can be tested without
// installing k0lmena (tests/node/api-http.test.js).
//
//   joinUrl(base, path)              → base + path with a single slash in between (the base includes the
//                                       spec's server or basePath: https://petstore.swagger.io/v2).
//   variablesWithoutValue(text)      → the {variables} that were left unreplaced (to stop with a clear
//                                       message instead of sending a literal "/pet/{petId}" and getting a 404).
//   parseJson(text, what)            → JSON.parse with an error that says which JSON was wrong and where.
//   parseResponse(text)              → the response body: JSON (with big integers as text, so int64 ids
//                                       don't lose precision) or the text as is.
//   hideHeaders(headers)             → the headers with the credentials masked (for the report).
//   typeOf(value, expected)          → { ok, actual }: accepts the JSON Schema / OpenAPI types (integer,
//                                       number, string, boolean, array, object, null) and their common aliases.

/** base + path without extra or missing slashes. A path that is already a full URL stays as is. */
function joinUrl(base, route) {
  const r = String(route ?? '');
  if (/^https?:\/\//i.test(r)) return r;
  const b = String(base ?? '').trim();
  if (!b) throw new Error(`There is no base URL for "${r}": set API_BASEURL in the root .env (with the spec's server or basePath, e.g. https://petstore.swagger.io/v2).`);
  if (!r) return b;
  if (/^[?#]/.test(r)) return b.replace(/\/+$/, '') + r;
  return `${b.replace(/\/+$/, '')}/${r.replace(/^\/+/, '')}`;
}

/** The {variables} left without a value in an already interpolated text. */
function variablesWithoutValue(text) {
  return [...new Set((String(text).match(/\{([A-Za-z_][\w.]*)\}/g) || []).map((m) => m.slice(1, -1)))];
}

/** JSON.parse with a message that says what was being read. */
function parseJson(text, what = 'The JSON') {
  try {
    return JSON.parse(text);
  } catch (e) {
    throw new Error(`${what} is not valid JSON (${e.message}). Check quotes, commas and braces:\n${String(text).slice(0, 500)}`);
  }
}

// Integers that don't fit in a JavaScript number without losing precision (the int64 ids of many APIs,
// e.g. 9223372036854775807 in petstore): they are kept as text. Walks the JSON respecting strings.
function protectBigIntegers(text) {
  let output = '';
  let inString = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (inString) {
      output += ch;
      if (ch === '\\') { output += text[++i] ?? ''; continue; }
      if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') { inString = true; output += ch; continue; }
    if (ch === '-' || (ch >= '0' && ch <= '9')) {
      const m = /^-?\d+(\.\d+)?([eE][+-]?\d+)?/.exec(text.slice(i));
      if (m) {
        const num = m[0];
        const integer = !m[1] && !m[2];
        output += integer && !Number.isSafeInteger(Number(num)) ? `"${num}"` : num;
        i += num.length - 1;
        continue;
      }
    }
    output += ch;
  }
  return output;
}

/** Response body: JSON if it is JSON (with big integers as text); otherwise, the text. */
function parseResponse(text) {
  if (text == null || typeof text !== 'string') return text;
  const t = text.trim();
  if (!t) return '';
  if (!/^[[{"]|^-?\d|^(true|false|null)$/.test(t)) return text;
  try {
    return JSON.parse(protectBigIntegers(t));
  } catch {
    return text;
  }
}

const SENSITIVE = /authorization|token|api[-_]?key|secret|password|passwd|cookie|session|credential/i;

/** Copy of the headers with the credentials masked (the scheme is shown: "Bearer ***", "Basic ***"). */
function hideHeaders(headers) {
  const output = {};
  for (const [k, v] of Object.entries(headers || {})) {
    if (!SENSITIVE.test(k)) { output[k] = v; continue; }
    const scheme = /^(Bearer|Basic|Token|ApiKey)\s/i.exec(String(v));
    output[k] = scheme ? `${scheme[1]} ***` : '***';
  }
  return output;
}

/** Copy of the query parameters with the credentials masked. */
function hideParameters(params) {
  const output = {};
  for (const [k, v] of Object.entries(params || {})) output[k] = SENSITIVE.test(k) ? '***' : v;
  return output;
}

const SYNONYMS = {
  integer: 'integer', int: 'integer', int32: 'integer', int64: 'integer', long: 'integer',
  number: 'number', float: 'number', double: 'number', decimal: 'number',
  string: 'string', text: 'string', str: 'string',
  boolean: 'boolean', bool: 'boolean',
  array: 'array', list: 'array',
  object: 'object', obj: 'object',
  null: 'null',
};

/** Is the value of the expected type? Big integers (which arrive as text) count as integer. */
function typeOf(value, expected) {
  const type = SYNONYMS[String(expected).trim().toLowerCase()];
  if (!type) throw new Error(`Unknown type: "${expected}". Use integer, number, string, boolean, array, object or null.`);
  const actual = Array.isArray(value) ? 'array' : value === null ? 'null' : typeof value;
  const bigInteger = typeof value === 'string' && /^-?\d{16,}$/.test(value);
  let ok;
  if (type === 'integer') ok = (actual === 'number' && Number.isInteger(value)) || bigInteger;
  else if (type === 'number') ok = actual === 'number' || bigInteger;
  else ok = actual === type;
  return { ok, actual: actual === 'number' && Number.isInteger(value) ? 'integer' : actual };
}

module.exports = { joinUrl, variablesWithoutValue, parseJson, parseResponse, protectBigIntegers, hideHeaders, hideParameters, typeOf };
