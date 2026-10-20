// performance/k6/lib/k0lmena.ts
//
// Base for the k0lmenIA k6 scripts. A script defines the FLOW (export default) and the target
// LOAD; the PROFILE is chosen when running (npm run perf -- <script> <profile>):
//
//   smoke  -> 1 user, 30 s: validates that the script works (measures nothing)
//   load   -> ramps up to `vus`, holds them for `duration` and ramps down
//   stress -> `vus`, then 2x and 3x `vus` (looks for the breaking point)
//   soak   -> `vus` held for `soakDuration` (memory leaks, degradation)
//   spike  -> sudden jump up to `peak` users and back (traffic spikes)
//
// The numbers (users, durations, thresholds) are defined by the person: the agent asks for them.
// PERF_VUS and PERF_DURATION in the environment override `vus` and `duration` for a one-off run.

import http from 'k6/http';

export type Profile = 'smoke' | 'load' | 'stress' | 'soak' | 'spike';

export interface Load {
  /** Target concurrent virtual users. */
  vus: number;
  /** Time held at `vus` (load and each stress step), e.g. '5m'. */
  duration: string;
  /** Ramp-up and ramp-down time. Default '30s'. */
  ramp?: string;
  /** Soak duration. Default '30m'. */
  soakDuration?: string;
  /** Users at the spike peak. Default 3x `vus`. */
  peak?: number;
  /** k6 thresholds (https://grafana.com/docs/k6/latest/using-k6/thresholds/). */
  thresholds?: Record<string, string[]>;
  /** Request names (tag `name`) to get per-endpoint metrics in the report. */
  endpoints?: string[];
}

export const env = {
  BASEURL: __ENV.BASEURL || '',
  API_BASEURL: __ENV.API_BASEURL || '',
  // Same token as the API suite (API_TOKEN); AUTH_TOKEN is kept for compatibility.
  TOKEN: __ENV.API_TOKEN || __ENV.AUTH_TOKEN || '',
};

export const profile = ((__ENV.PROFILE || 'smoke').toLowerCase()) as Profile;

// Codes broken down in the report (k6 only exports submetrics declared in advance).
const CODES = [0, 200, 201, 202, 204, 301, 302, 304, 400, 401, 403, 404, 405, 409, 422, 429, 500, 502, 503, 504];

function stages(c: Load) {
  const vus = Number(__ENV.PERF_VUS || c.vus);
  const dur = __ENV.PERF_DURATION || c.duration;
  const ramp = c.ramp || '30s';
  switch (profile) {
    case 'smoke':
      return { executor: 'constant-vus', vus: 1, duration: __ENV.PERF_DURATION || '30s' };
    case 'load':
      return { executor: 'ramping-vus', startVUs: 0, stages: [
        { duration: ramp, target: vus }, { duration: dur, target: vus }, { duration: ramp, target: 0 },
      ] };
    case 'stress':
      return { executor: 'ramping-vus', startVUs: 0, stages: [
        { duration: ramp, target: vus }, { duration: dur, target: vus },
        { duration: ramp, target: vus * 2 }, { duration: dur, target: vus * 2 },
        { duration: ramp, target: vus * 3 }, { duration: dur, target: vus * 3 },
        { duration: ramp, target: 0 },
      ] };
    case 'soak':
      return { executor: 'ramping-vus', startVUs: 0, stages: [
        { duration: ramp, target: vus }, { duration: c.soakDuration || '30m', target: vus }, { duration: ramp, target: 0 },
      ] };
    case 'spike': {
      const peak = c.peak || vus * 3;
      return { executor: 'ramping-vus', startVUs: 0, stages: [
        { duration: ramp, target: vus }, { duration: '1m', target: vus },
        { duration: '10s', target: peak }, { duration: '1m', target: peak },
        { duration: '10s', target: vus }, { duration: '1m', target: vus },
        { duration: ramp, target: 0 },
      ] };
    }
    default:
      throw new Error(`Unknown PROFILE: ${profile} (smoke | load | stress | soak | spike)`);
  }
}

/** `export const options = loadOptions({...})` in each script. */
export function loadOptions(c: Load) {
  const thresholds: Record<string, string[]> = { ...(c.thresholds || {}) };
  // An empty threshold evaluates nothing: it only makes k6 export that submetric to the summary.
  for (const name of c.endpoints || []) {
    const key = `http_req_duration{name:${name}}`;
    if (!thresholds[key]) thresholds[key] = [];
  }
  for (const code of CODES) thresholds[`http_reqs{status:${code}}`] = [];
  return {
    scenarios: { [profile]: stages(c) },
    thresholds,
    summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max', 'count'],
    tags: { profile },
  };
}

/** JSON headers + Authorization (if there is a token). */
export function headers(extra: Record<string, string> = {}) {
  const h: Record<string, string> = Object.assign({ 'Content-Type': 'application/json' }, extra);
  if (env.TOKEN) h['Authorization'] = `Bearer ${env.TOKEN}`;
  return h;
}

/**
 * Named request (the name groups the metrics per endpoint: use the path with
 * parameters, e.g. 'GET /pet/{id}', not the URL with the real ID).
 */
export function request(method: string, name: string, url: string, body?: unknown, extraHeaders: Record<string, string> = {}) {
  const payload = body === undefined ? null : typeof body === 'string' ? body : JSON.stringify(body);
  return http.request(method, url, payload, { headers: headers(extraHeaders), tags: { name } });
}

/** Saves the raw summary for the k0lmenIA report (processed by run-perf.js). */
export function handleSummary(data: unknown) {
  const output = __ENV.K0LMENA_PERF_OUTPUT || 'reports/performance/k6/latest.json';
  return { [output]: JSON.stringify(data) };
}
