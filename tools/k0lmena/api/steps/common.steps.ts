// api/steps/common.steps.ts
//
// Generic API steps in English. The api-mapper agent builds the .feature files
// using ONLY these steps, so there is no need to write code for each endpoint.
//
// URL: API_BASEURL in the .env is the spec's server WITH its basePath (e.g. https://petstore.swagger.io/v2)
// and the .feature endpoints are the spec's paths as they are ("/pet/{petId}"). They are joined with a
// single slash; a full URL in the endpoint is used as is.
//
// Variables in endpoints, parameters, headers and bodies: {name}
//   - replaced by a value saved with "I save the response field ... as ..."
//   - or by data generated for the scenario: {uuid}, {random}, {timestamp}, {now}
//   - or, if it does not exist, by the environment variable with the same name (.env)
//   A variable left without a value in the endpoint or the body stops the scenario with a clear
//   message (previously a literal "{petId}" was sent and the API answered 404).
//
// Authentication, according to the spec's securityScheme:
//   Bearer (http bearer / JWT)      → the request uses the authentication token          (API_TOKEN)
//   apiKey in a header              → the request uses the API key in the header "api_key" (API_KEY or API_TOKEN)
//   apiKey in the query             → the request uses the API key in the parameter "key"  (API_KEY or API_TOKEN)
//   http basic                      → the request uses basic authentication               (API_USER / API_PASSWORD)
//
// Responses: the JSON is read with big integers (int64 ids) as text, so no precision
// is lost; a response that is not JSON stays as text.
//
// GraphQL: "I send the GraphQL query:" sends {query, variables} by POST to the GraphQL endpoint
// (the one from "the GraphQL endpoint is ...", or GRAPHQL_URL in the .env, or API_BASEURL + /graphql). The query
// goes as is (its braces are not interpolated): dynamic values go in the GraphQL variables,
// which do accept {name}.
import '../../env'; // single .env at the k0lmenIA root
import { Given, When, Then, Before, After, DataTable } from '@cucumber/cucumber';
import { expect } from '@playwright/test';
import axios, { AxiosResponse, Method } from 'axios';
import { variables, interpolate } from '../../tools/variables';
const http = require('../../tools/api/http');

type Body = { type: 'json'; data: unknown } | { type: 'form'; data: Record<string, string> };
type State = {
  headers: Record<string, string>;
  params: Record<string, string>;
  graphql: { endpoint?: string; variables?: Record<string, unknown> };
  request?: { method: string; url: string; params?: Record<string, string>; body?: unknown };
  response?: AxiosResponse;
  ms?: number;
};

let state: State;

Before(() => {
  state = { headers: {}, params: {}, graphql: {} };
});

const TIMEOUT_MS = Number(process.env.API_TIMEOUT_MS) || 30000;

// Reads a field with dot notation: "data.items.0.id"
const readField = (obj: unknown, path: string): unknown =>
  path.split('.').reduce<any>((acc, k) => (acc == null ? undefined : acc[k]), obj);

const response = (): AxiosResponse => {
  if (!state.response) throw new Error('No request has been sent yet in this scenario.');
  return state.response;
};

const textOf = (data: unknown): string => (typeof data === 'string' ? data : JSON.stringify(data) ?? '');

const hasHeader = (headers: Record<string, string>, name: string) =>
  Object.keys(headers).some((k) => k.toLowerCase() === name.toLowerCase());

const noPendingVariables = (text: string, where: string) => {
  const missing: string[] = http.variablesWithoutValue(text);
  if (missing.length) {
    throw new Error(`${where} has variables without a value: ${missing.map((v) => `{${v}}`).join(', ')}. ` +
      'Save them first with "I save the response field ... as ..." (in this same scenario) or define them in the .env.');
  }
};

// Rows of a name | value table (with or without the "name | value" header row).
const rows = (table: DataTable): Record<string, string> => {
  const raw = table.raw();
  const noHeader = raw.length && /^(name|field|parameter|key)$/i.test(raw[0][0]?.trim() ?? '') ? raw.slice(1) : raw;
  const output: Record<string, string> = {};
  for (const [k, v] of noHeader) output[k.trim()] = interpolate(v ?? '');
  return output;
};

const send = async (method: string, endpoint: string, body?: Body) => {
  const path = interpolate(endpoint);
  noPendingVariables(path, `The endpoint "${path}"`);
  const url: string = http.joinUrl(process.env.API_BASEURL, path);
  const headers = { ...state.headers };
  let data: unknown;
  if (body?.type === 'json') {
    data = body.data;
    if (!hasHeader(headers, 'Content-Type')) headers['Content-Type'] = 'application/json';
  } else if (body?.type === 'form') {
    data = new URLSearchParams(body.data).toString();
    headers['Content-Type'] = 'application/x-www-form-urlencoded';
  }
  const params = { ...state.params };
  const start = Date.now();
  state.request = { method: method.toUpperCase(), url, params, body: body?.data };
  state.response = await axios.request({
    method: method.toUpperCase() as Method,
    url,
    headers,
    params,
    data,
    timeout: TIMEOUT_MS,
    responseType: 'text',
    transformResponse: [(d: string) => http.parseResponse(d)],
    validateStatus: () => true, // 4xx/5xx are validated in the Then steps, they do not throw
  });
  state.ms = Date.now() - start;
};

const bodyJson = (text: string) => {
  const t = interpolate(text);
  noPendingVariables(t, 'The body');
  return http.parseJson(t, 'The body');
};

// GraphQL: POST with {query, variables, operationName} to the GraphQL endpoint.
const urlGraphQL = (): string =>
  http.joinUrl(process.env.API_BASEURL, interpolate(state.graphql.endpoint ?? process.env.GRAPHQL_URL ?? '/graphql'));

const sendGraphQL = async (query: string) => {
  const url = urlGraphQL();
  const operation = /^\s*(?:query|mutation|subscription)\s+([A-Za-z_]\w*)/.exec(query)?.[1];
  const body = { query, variables: state.graphql.variables ?? {}, ...(operation ? { operationName: operation } : {}) };
  const start = Date.now();
  state.request = { method: 'POST', url, body };
  state.response = await axios.request({
    method: 'POST', url, headers: { 'Content-Type': 'application/json', ...state.headers }, params: { ...state.params }, data: body,
    timeout: TIMEOUT_MS,
    responseType: 'text',
    transformResponse: [(d: string) => http.parseResponse(d)],
    validateStatus: () => true,
  });
  state.ms = Date.now() - start;
};

const graphQLErrors = (): Array<{ message?: string; extensions?: Record<string, unknown> }> => {
  const errors = response().data?.errors;
  return Array.isArray(errors) ? errors : [];
};

// Evidence of each scenario (pass or fail): the last request and its response.
// Credentials (Authorization, API keys, cookies) are masked so they do not leak into the report.
After(function () {
  if (!state?.request) return;
  const res = state.response;
  const body = typeof res?.data === 'string' ? res.data : JSON.stringify(res?.data, null, 2) ?? '';
  const params = state.request.params && Object.keys(state.request.params).length
    ? `Parameters: ${JSON.stringify(http.hideParameters(state.request.params))}` : '';
  this.attach(
    [
      `REQUEST\n${state.request.method} ${state.request.url}`,
      params,
      `Headers: ${JSON.stringify(http.hideHeaders(state.headers))}`,
      state.request.body !== undefined ? `Body:\n${JSON.stringify(state.request.body, null, 2)}` : '',
      `\nRESPONSE (${state.ms} ms)\nStatus: ${res?.status} ${res?.statusText ?? ''}`,
      `Headers: ${JSON.stringify(http.hideHeaders(res?.headers ?? {}))}`,
      `Body:\n${body.length > 20000 ? body.slice(0, 20000) + '\n... (truncated)' : body}`,
    ].filter(Boolean).join('\n'),
    'text/plain'
  );
});

/* ---------- Given ---------- */

Given('the request uses the header {string} with value {string}', (name: string, value: string) => {
  state.headers[name] = interpolate(value);
});

Given('the request uses the authentication token', () => {
  const token = process.env.API_TOKEN;
  if (!token) throw new Error('API_TOKEN is missing in the k0lmenIA root .env.');
  state.headers.Authorization = `Bearer ${token}`;
});

const apiKey = (): string => {
  const key = process.env.API_KEY || process.env.API_TOKEN;
  if (!key) throw new Error('API_KEY (or API_TOKEN) is missing in the k0lmenIA root .env.');
  return key;
};

Given('the request uses the API key in the header {string}', (name: string) => {
  state.headers[name] = apiKey();
});

Given('the request uses the API key in the parameter {string}', (name: string) => {
  state.params[name] = apiKey();
});

Given('the request uses basic authentication', () => {
  const user = process.env.API_USER;
  const password = process.env.API_PASSWORD;
  if (!user || password === undefined) throw new Error('API_USER and API_PASSWORD are missing in the k0lmenIA root .env.');
  state.headers.Authorization = `Basic ${Buffer.from(`${user}:${password}`).toString('base64')}`;
});

Given('the request sends no authentication token', () => {
  // No credentials at all: no Authorization and no API keys in headers or parameters.
  for (const k of Object.keys(state.headers)) if (/^authorization$|api[-_]?key|token/i.test(k)) delete state.headers[k];
  for (const k of Object.keys(state.params)) if (/api[-_]?key|token/i.test(k)) delete state.params[k];
});

Given('the request has the parameters:', (table: DataTable) => {
  // Query parameters (name | value); they are encoded automatically (spaces, accents, &).
  Object.assign(state.params, rows(table));
});

Given('the GraphQL endpoint is {string}', (endpoint: string) => {
  state.graphql.endpoint = endpoint;
});

Given('the GraphQL variables are:', (json: string) => {
  state.graphql.variables = http.parseJson(interpolate(json), 'The GraphQL variables');
});

/* ---------- When ---------- */

When('I send a {word} to {string}', async (method: string, endpoint: string) => {
  await send(method, endpoint);
});

When('I send a {word} to {string} with the body:', async (method: string, endpoint: string, body: string) => {
  await send(method, endpoint, { type: 'json', data: bodyJson(body) });
});

When('I send a {word} to {string} with the form:', async (method: string, endpoint: string, table: DataTable) => {
  // application/x-www-form-urlencoded (name | value), for the endpoints that consume formData in the spec.
  await send(method, endpoint, { type: 'form', data: rows(table) });
});

When('I send the GraphQL query:', async (query: string) => {
  await sendGraphQL(query);
});

When('I save the response field {string} as {string}', (field: string, name: string) => {
  const value = readField(response().data, field);
  if (value === undefined) {
    throw new Error(`The response does not have the field "${field}" to save it as "${name}". Response: ${textOf(response().data).slice(0, 500)}`);
  }
  variables[name] = value;
});

/* ---------- Then ---------- */

Then('the response status is {int}', (status: number) => {
  expect(response().status, textOf(response().data).slice(0, 500)).toBe(status);
});

Then('the response contains the field {string}', (field: string) => {
  expect(readField(response().data, field), `Missing the field "${field}"`).not.toBeUndefined();
});

Then('the response does not contain the field {string}', (field: string) => {
  expect(readField(response().data, field)).toBeUndefined();
});

Then('the response field {string} is {string}', (field: string, value: string) => {
  expect(String(readField(response().data, field))).toBe(interpolate(value));
});

Then('the response field {string} is the number {float}', (field: string, value: number) => {
  expect(Number(readField(response().data, field))).toBe(value);
});

Then('the response field {string} is of type {string}', (field: string, type: string) => {
  // Accepts the spec's types: integer, number, string, boolean, array, object, null (or their common aliases).
  const v = readField(response().data, field);
  const { ok, actual } = http.typeOf(v, type);
  expect(ok, `The field "${field}" is ${actual}, not ${type}`).toBe(true);
});

Then('the response is a list', () => {
  expect(Array.isArray(response().data)).toBe(true);
});

Then('the response is a list with at least {int} element(s)', (min: number) => {
  expect(Array.isArray(response().data)).toBe(true);
  expect(response().data.length).toBeGreaterThanOrEqual(min);
});

const hasElement = (list: unknown, field: string, value: string, where: string) => {
  expect(Array.isArray(list), `${where} is not a list`).toBe(true);
  const wanted = interpolate(value);
  const found = (list as unknown[]).some((x) => String(readField(x, field)) === wanted);
  expect(found, `${where} has no element with "${field}" = "${wanted}"`).toBe(true);
};

Then('the response has an element with {string} equal to {string}', (field: string, value: string) => {
  hasElement(response().data, field, value, 'The response');
});

Then('the response list {string} has an element with {string} equal to {string}', (list: string, field: string, value: string) => {
  hasElement(readField(response().data, list), field, value, `"${list}"`);
});

Then('the response has the fields:', (table: DataTable) => {
  // One-column table with the paths of the required fields.
  for (const [field] of table.raw()) {
    expect(readField(response().data, field), `Missing the field "${field}"`).not.toBeUndefined();
  }
});

Then('the response contains the text {string}', (text: string) => {
  expect(textOf(response().data)).toContain(interpolate(text));
});

Then('the response header {string} contains {string}', (name: string, value: string) => {
  expect(String(response().headers[name.toLowerCase()] ?? '')).toContain(value);
});

Then('the response arrives in less than {int} ms', (max: number) => {
  expect(state.ms ?? Infinity).toBeLessThan(max);
});

/* ---------- GraphQL Then steps (the fields are read inside "data") ---------- */

Then('the GraphQL response has no errors', () => {
  expect(graphQLErrors().map((e) => e.message), 'The GraphQL response has errors').toEqual([]);
});

Then('the GraphQL response has an error with the message {string}', (message: string) => {
  const messages = graphQLErrors().map((e) => String(e.message ?? ''));
  expect(messages.some((m) => m.includes(interpolate(message))), `Errors: ${JSON.stringify(messages)}`).toBe(true);
});

Then('the GraphQL response has an error with the code {string}', (code: string) => {
  const codes = graphQLErrors().map((e) => String(e.extensions?.code ?? ''));
  expect(codes, `Errors: ${JSON.stringify(graphQLErrors())}`).toContain(code);
});

Then('the GraphQL response contains the field {string}', (field: string) => {
  expect(readField(response().data?.data, field), `Missing data.${field}`).not.toBeUndefined();
});

Then('the GraphQL field {string} is {string}', (field: string, value: string) => {
  expect(String(readField(response().data?.data, field))).toBe(interpolate(value));
});

Then('the GraphQL field {string} is the number {float}', (field: string, value: number) => {
  expect(Number(readField(response().data?.data, field))).toBe(value);
});

Then('the GraphQL field {string} is null', (field: string) => {
  expect(readField(response().data?.data, field)).toBeNull();
});

Then('the GraphQL field {string} is a list with at least {int} element(s)', (field: string, min: number) => {
  const v = readField(response().data?.data, field);
  expect(Array.isArray(v), `data.${field} is not a list`).toBe(true);
  expect((v as unknown[]).length).toBeGreaterThanOrEqual(min);
});

When('I save the GraphQL field {string} as {string}', (field: string, name: string) => {
  variables[name] = readField(response().data?.data, field);
});
