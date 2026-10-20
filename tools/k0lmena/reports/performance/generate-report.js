// reports/performance/generate-report.js
//
// k0lmenIA performance report (k6, Artillery and JMeter with the same format).
// run-perf.js calls it at the end of each run:
//   - normalizes the tool's raw result into a common "summary" (small JSON; it is what
//     the agent reads: there is no need to open the raw result or the log),
//   - builds the HTML dashboard (dark mode, self-contained, no CDN).
const fs = require('fs');
const path = require('path');

// ---------------------------------------------------------------- utilities
const num = (x) => (typeof x === 'number' && isFinite(x) ? x : null);
const r2 = (x) => (x == null ? null : Math.round(x * 100) / 100);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const stripAnsi = (s) => s.replace(/\x1b\[[0-9;]*m/g, '');

function ms(x) {
  if (x == null) return '—';
  return x >= 1000 ? `${(x / 1000).toFixed(2)} s` : `${x.toFixed(0)} ms`;
}
function duration(sec) {
  if (sec == null) return '—';
  const total = Math.round(sec); // round before splitting: 239.6 s is "4m 0s", not "3m 60s"
  const m = Math.floor(total / 60), s = total % 60;
  return m ? `${m}m ${s}s` : `${s}s`;
}
function formatDate(iso) {
  const d = new Date(iso), p = (n) => String(n).padStart(2, '0');
  return `${p(d.getMonth() + 1)}/${p(d.getDate())}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
const integer = (x) => (x == null ? '—' : Math.round(x).toLocaleString('en-US'));

// ---------------------------------------------------------------- k6
function parseSubmetric(key) {
  const i = key.indexOf('{');
  if (i === -1) return null;
  const tags = {};
  for (const pair of key.slice(i + 1, key.lastIndexOf('}')).split(',')) {
    const j = pair.indexOf(':');
    if (j > 0) tags[pair.slice(0, j).trim()] = pair.slice(j + 1).trim();
  }
  return { metric: key.slice(0, i), tags };
}

function checksK6(group, output = []) {
  if (!group) return output;
  const checks = Array.isArray(group.checks) ? group.checks : Object.values(group.checks || {});
  for (const c of checks) output.push({ name: c.name, passes: c.passes || 0, fails: c.fails || 0 });
  const groups = Array.isArray(group.groups) ? group.groups : Object.values(group.groups || {});
  for (const g of groups) checksK6(g, output);
  return output;
}

function fromK6(data) {
  const m = data.metrics || {};
  const v = (name) => (m[name] && m[name].values) || {};
  const dur = v('http_req_duration');
  const sec = num(data.state && data.state.testRunDurationMs) != null ? data.state.testRunDurationMs / 1000 : null;
  const requests = num(v('http_reqs').count) || 0;

  const thresholds = [];
  const endpoints = [];
  const codes = {};
  for (const [key, metric] of Object.entries(m)) {
    for (const [cond, res] of Object.entries(metric.thresholds || {})) {
      const mm = cond.match(/^\s*([a-z]+(?:\(\d+(?:\.\d+)?\))?)\s*(<=|>=|<|>|===|==|!=)\s*([\d.]+)\s*$/i);
      let value = mm ? num(metric.values[mm[1] === 'p(50)' ? 'med' : mm[1]]) : null;
      if (value != null && /rate/.test(mm[1])) value = value * 100;
      thresholds.push({
        metric: key, condition: cond,
        value: value == null ? '—' : /rate/.test(mm && mm[1]) ? `${value.toFixed(2)} %` : /duration|waiting|time/.test(key) ? ms(value) : String(r2(value)),
        ok: !!res.ok,
      });
    }
    const sub = parseSubmetric(key);
    if (!sub) continue;
    if (sub.metric === 'http_req_duration' && sub.tags.name) {
      const x = metric.values;
      endpoints.push({ name: sub.tags.name, requests: num(x.count), avg: num(x.avg), p95: num(x['p(95)']), p99: num(x['p(99)']), max: num(x.max) });
    }
    if (sub.metric === 'http_reqs' && sub.tags.status != null && num(metric.values.count)) {
      codes[sub.tags.status === '0' ? 'no response' : sub.tags.status] = metric.values.count;
    }
  }

  const checks = checksK6(data.root_group);
  const errors = {};
  for (const c of checks) if (c.fails) errors[`check: ${c.name}`] = c.fails;
  for (const [code, n] of Object.entries(codes)) if (code === 'no response' || Number(code) >= 400) errors[`HTTP ${code}`] = n;

  return {
    duration_s: sec,
    kpis: {
      requests,
      rps: sec ? requests / sec : num(v('http_reqs').rate),
      error_pct: num(v('http_req_failed').rate) != null ? v('http_req_failed').rate * 100 : null,
      max_users: num(v('vus_max').max) ?? num(v('vus_max').value),
      iterations: num(v('iterations').count),
    },
    latency: {
      source: 'http_req_duration (each request)',
      p50: num(dur.med), p90: num(dur['p(90)']), p95: num(dur['p(95)']), p99: num(dur['p(99)']),
      avg: num(dur.avg), max: num(dur.max),
    },
    thresholds,
    detail: { title: 'By endpoint', rows: endpoints.sort((a, b) => (b.requests || 0) - (a.requests || 0)) },
    codes,
    checks,
    errors,
    timeline: [],
  };
}

// ---------------------------------------------------------------- Artillery
function fromArtillery(data, log) {
  const a = data.aggregate || {};
  const c = a.counters || {}, s = a.summaries || {};
  const sec = num(a.lastMetricAt) && num(a.firstMetricAt) ? (a.lastMetricAt - a.firstMetricAt) / 1000 : null;
  const requests = c['http.requests'] ?? c['browser.http_requests'] ?? null;
  const created = c['vusers.created'] || 0, completed = c['vusers.completed'] || 0;
  const source = s['http.response_time'] ? 'http.response_time' : s['vusers.session_length'] ? 'vusers.session_length' : null;
  const lat = source ? s[source] : {};

  // Measured value of an Artillery metric ("http.response_time.p95", "vusers.failed", ...)
  const valueFor = (name) => {
    if (c[name] != null) return c[name];
    const i = name.lastIndexOf('.');
    return i > 0 && s[name.slice(0, i)] ? num(s[name.slice(0, i)][name.slice(i + 1)]) : null;
  };
  const thresholds = [];
  for (const line of stripAnsi(log || '').split(/\r?\n/)) {
    const mm = line.match(/^\s*(ok|fail):\s*(.+?)\s*$/);
    if (!mm) continue;
    const cond = mm[2];
    const ok = mm[1] === 'ok';
    const errorPct = created ? `${(((created - completed) / created) * 100).toFixed(2)} %` : '—';
    const t = cond.match(/^(.+?)\s*(<=|<)\s*([\d.]+)$/);
    if (/^maxErrorRate|vusers\.created - vusers\.completed/.test(cond)) {
      thresholds.push({ metric: 'users who did not complete the flow', condition: `<= ${t ? t[3] : '?'} %`, value: errorPct, ok });
    } else if (t) {
      const name = t[1].trim(), v = valueFor(name);
      const value = v == null ? '—' : /time|length|step|FCP|LCP|TTFB|FID|INP|CLS/.test(name) ? ms(v) : String(r2(v));
      thresholds.push({ metric: name, condition: `${t[2]} ${t[3]}`, value, ok });
    } else {
      thresholds.push({ metric: 'condition', condition: cond, value: '—', ok }); // config.ensure.conditions expressions
    }
  }

  const rows = Object.entries(s)
    .filter(([n]) => n !== source)
    .map(([n, x]) => ({ name: n, requests: num(x.count), avg: num(x.mean), p95: num(x.p95), p99: num(x.p99), max: num(x.max) }))
    .sort((x, y) => x.name.localeCompare(y.name));

  const codes = {};
  for (const [n, v] of Object.entries(c)) {
    const mm = n.match(/\.codes\.(\d+)$/);
    if (mm) codes[mm[1]] = (codes[mm[1]] || 0) + v;
  }
  const errors = {};
  for (const [n, v] of Object.entries(c)) if (n.startsWith('errors.')) errors[n.slice(7)] = v;
  for (const [code, n] of Object.entries(codes)) if (Number(code) >= 400) errors[`HTTP ${code}`] = n;

  const periods = (data.intermediate || []).filter((p) => p.counters);
  const timeline = periods.map((p, i) => {
    const next = periods[i + 1];
    const length = next ? (Number(next.period) - Number(p.period)) / 1000 : 10;
    const req = p.counters['http.requests'] ?? p.counters['browser.http_requests'] ?? p.counters['vusers.created'] ?? 0;
    return {
      t: Number(p.period),
      rps: length > 0 ? req / length : null,
      p95: source && p.summaries && p.summaries[source] ? num(p.summaries[source].p95) : null,
      errors: p.counters['vusers.failed'] || 0,
    };
  });

  return {
    duration_s: sec,
    kpis: {
      requests,
      rps: sec && requests != null ? requests / sec : null,
      error_pct: created ? ((created - completed) / created) * 100 : null,
      max_users: created,
      iterations: completed,
    },
    latency: {
      source: source === 'http.response_time' ? 'http.response_time (each request)' : source ? 'vusers.session_length (full flow of each user)' : '—',
      p50: num(lat.median ?? lat.p50), p90: num(lat.p90), p95: num(lat.p95), p99: num(lat.p99), avg: num(lat.mean), max: num(lat.max),
    },
    thresholds,
    detail: { title: 'By step / metric', rows },
    codes,
    checks: [],
    errors,
    timeline,
  };
}

// ---------------------------------------------------------------- JMeter
// CSV with double quotes ("" escapes a quote), as JMeter writes it in the .jtl.
function csvRows(text) {
  const rows = [];
  let row = [], field = '', quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (ch === '"') quoted = false;
      else field += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ',') { row.push(field); field = ''; }
    else if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && text[i + 1] === '\n') i++;
      row.push(field); field = '';
      if (row.length > 1 || row[0]) rows.push(row);
      row = [];
    } else field += ch;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  return rows;
}

function percentile(sorted, p) {
  if (!sorted.length) return null;
  return sorted[Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1)];
}

function statistics(times) {
  const o = [...times].sort((a, b) => a - b);
  const sum = o.reduce((s, x) => s + x, 0);
  return { n: o.length, p50: percentile(o, 50), p90: percentile(o, 90), p95: percentile(o, 95), p99: percentile(o, 99), avg: o.length ? sum / o.length : null, max: o.length ? o[o.length - 1] : null };
}

// Thresholds from the <script>.json file: { error_pct, p50, p90, p95, p99, avg, max, by_sample: { "<label>": {...} } }
const JM_METRICS = { error_pct: '% errors', p50: 'p50', p90: 'p90', p95: 'p95', p99: 'p99', avg: 'average', max: 'max' };
function jmeterThresholds(def, global, byLabel) {
  const output = [];
  const evaluate = (limits, st, prefix) => {
    for (const [key, limit] of Object.entries(limits || {})) {
      if (!(key in JM_METRICS) || typeof limit !== 'number') continue;
      const v = st[key];
      output.push({
        metric: `${prefix}${JM_METRICS[key]}`,
        condition: key === 'error_pct' ? `<= ${limit} %` : `<= ${limit} ms`,
        value: v == null ? '—' : key === 'error_pct' ? `${v.toFixed(2)} %` : ms(v),
        ok: v != null && v <= limit,
      });
    }
  };
  evaluate(def, global, '');
  for (const [label, limits] of Object.entries((def && def.by_sample) || {})) {
    const st = byLabel[label];
    if (st) evaluate(limits, st, `${label} · `);
    else output.push({ metric: `${label} · (no samples)`, condition: 'the sample exists', value: '—', ok: false });
  }
  return output;
}

function fromJMeter(text, defThresholds) {
  const [head, ...rows] = csvRows(text);
  const col = (n) => head.indexOf(n);
  const [cTs, cEl, cLb, cCode, cOk, cMsg, cThreads] = ['timeStamp', 'elapsed', 'label', 'responseCode', 'success', 'failureMessage', 'allThreads'].map(col);
  if (cTs < 0 || cEl < 0 || cLb < 0) throw new Error('The .jtl does not have the timeStamp, elapsed and label columns (was it saved as CSV?).');

  const times = [], byLabel = {}, codes = {}, errors = {}, buckets = {};
  let start = Infinity, end = 0, failed = 0, maxThreads = 0;
  for (const f of rows) {
    const ts = Number(f[cTs]), el = Number(f[cEl]), label = f[cLb];
    if (!isFinite(ts) || !isFinite(el)) continue;
    const ok = cOk < 0 || f[cOk] === 'true';
    times.push(el);
    (byLabel[label] = byLabel[label] || { times: [], failures: 0 }).times.push(el);
    start = Math.min(start, ts);
    end = Math.max(end, ts + el);
    if (cThreads >= 0) maxThreads = Math.max(maxThreads, Number(f[cThreads]) || 0);
    const cod = cCode >= 0 ? f[cCode] : '';
    const code = /^\d{3}$/.test(cod) ? cod : 'no response';
    codes[code] = (codes[code] || 0) + 1;
    if (!ok) {
      failed++;
      byLabel[label].failures++;
      // JMeter assertion messages span several lines: they are joined into one.
      const reason = ((cMsg >= 0 && f[cMsg]) || (code === 'no response' ? `no response: ${cod}` : `HTTP ${code}`))
        .replace(/\s+/g, ' ').trim().slice(0, 160);
      errors[reason] = (errors[reason] || 0) + 1;
    }
    const b = Math.floor(ts / 10000) * 10000;
    (buckets[b] = buckets[b] || { times: [], failures: 0 }).times.push(el);
    if (!ok) buckets[b].failures++;
  }

  const sec = times.length ? (end - start) / 1000 : null;
  const global = { ...statistics(times), error_pct: times.length ? (failed / times.length) * 100 : null };
  const statsByLabel = {};
  for (const [label, x] of Object.entries(byLabel)) statsByLabel[label] = { ...statistics(x.times), error_pct: (x.failures / x.times.length) * 100 };

  return {
    duration_s: sec,
    kpis: {
      requests: times.length,
      rps: sec ? times.length / sec : null,
      error_pct: global.error_pct,
      max_users: maxThreads || null,
      iterations: failed,
    },
    latency: { source: 'elapsed (each sample)', p50: global.p50, p90: global.p90, p95: global.p95, p99: global.p99, avg: global.avg, max: global.max },
    thresholds: jmeterThresholds(defThresholds, global, statsByLabel),
    detail: {
      title: 'By sample (label)',
      rows: Object.entries(statsByLabel).map(([name, e]) => ({ name, requests: e.n, avg: e.avg, p95: e.p95, p99: e.p99, max: e.max })).sort((a, b) => b.requests - a.requests),
    },
    codes,
    checks: [],
    errors,
    timeline: Object.keys(buckets).map(Number).sort((a, b) => a - b).map((ts) => {
      const x = buckets[ts];
      return { t: ts, rps: x.times.length / 10, p95: statistics(x.times).p95, errors: x.failures };
    }),
  };
}

// ---------------------------------------------------------------- HTML
// Same design system as the k0lmenIA reports (scripts/_report_styles.py): k0lmena.com style,
// dark mode, validated categorical and status palettes (CVD and contrast), a single axis per chart,
// tooltips on hover and the status always with icon + text, never color alone.
const SERIES = ['#C98500', '#14A895', '#4C8DEB', '#E0702E'];
const STATUS = { ok: '#5CBF4A', warn: '#FFD60A', serious: '#FF8A00', err: '#FF5A4E', neutral: '#8A8172' };
const SURFACE = '#1E1A14';

// Line icons for the indicators (24x24, 1.8 stroke).
const ICONS = {
  load: '<path d="M4 18l5-6 4 3 7-9"/><path d="M15 6h5v5"/>',
  bolt: '<path d="M13 3L5 14h6l-1 7 8-11h-6z"/>',
  warn: '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17.2v.1"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  person: '<circle cx="12" cy="6" r="2.2"/><path d="M5 9.5l7 1.5 7-1.5M12 11v4l-3 5M12 15l3 5"/>',
  list: '<path d="M9 6h11M9 12h11M9 18h11M4.5 6h.1M4.5 12h.1M4.5 18h.1"/>',
};
const icon = (n) => `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[n] || ICONS.list}</svg>`;

// k0lmena.com typography (Saira, Inter and JetBrains Mono) embedded (scripts/fonts, OFL license): works offline.
const FONTS = (() => {
  const dir = path.resolve(__dirname, '..', '..', '..', '..', 'scripts', 'fonts');
  return [['Saira', 'saira.woff2', '500 700'], ['Inter', 'inter.woff2', '400 600'], ['JetBrains Mono', 'jetbrains-mono.woff2', '400 700']].map(([family, file, weights]) => {
    try {
      const b64 = fs.readFileSync(path.join(dir, file)).toString('base64');
      return `@font-face{font-family:'${family}';font-weight:${weights};font-display:swap;src:url(data:font/woff2;base64,${b64}) format('woff2')}`;
    } catch {
      return '';
    }
  }).join('');
})();

const CSS = `*{box-sizing:border-box;margin:0;padding:0}
:root{color-scheme:dark;--bg:#0E0C09;--surface:#1A1712;--surface-2:#1E1A14;--tile:#221E17;--line:rgba(244,239,230,.09);--line-2:rgba(244,239,230,.15);
  --ink:#F4EFE6;--body:#CFC7B8;--muted:#8A8172;--accent:#F9B006;--accent-soft:rgba(249,176,6,.12);--ok:#5CBF4A;--warn:#FFD60A;--err:#FF5A4E;--neutral:#8A8172;
  --neon:linear-gradient(135deg,#FFD60A,#FF8A00);--glow-k0:0 0 0 1px rgba(249,176,6,.35),0 0 32px -6px rgba(249,176,6,.40);
  --display:"Saira","Inter",ui-sans-serif,system-ui,sans-serif;
  --sans:"Inter",ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;--mono:"JetBrains Mono",ui-monospace,Menlo,Consolas,monospace}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--ink);font:14px/1.55 var(--sans);-webkit-font-smoothing:antialiased}
body::before{content:"";position:fixed;inset:0;pointer-events:none;background:radial-gradient(760px 420px at 100% -8%,rgba(249,176,6,.12),transparent 62%),
  url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='56' height='100'%3E%3Cpath d='M28 66L0 50L0 16L28 0L56 16L56 50L28 66L28 100' fill='none' stroke='%23F9B006' stroke-opacity='.10' stroke-width='1.2'/%3E%3Cpath d='M28 0L28 34L0 50L0 84L28 100L56 84L56 50L28 34' fill='none' stroke='%23F9B006' stroke-opacity='.07' stroke-width='1.2'/%3E%3C/svg%3E\") 0 0/56px 100px;-webkit-mask-image:linear-gradient(180deg,#000 0,rgba(0,0,0,.55) 420px,rgba(0,0,0,.18) 900px);
  mask-image:linear-gradient(180deg,#000 0,rgba(0,0,0,.55) 420px,rgba(0,0,0,.18) 900px)}
.app{position:relative;display:grid;grid-template-columns:248px minmax(0,1fr);min-height:100vh}
.side{position:sticky;top:0;height:100vh;display:flex;flex-direction:column;gap:18px;padding:22px 16px;border-right:1px solid var(--line);
  background:linear-gradient(180deg,rgba(26,23,18,.94),rgba(14,12,9,.94))}
.logo{display:flex;align-items:center;gap:11px;padding:4px 8px 14px;border-bottom:1px solid var(--line)}
.logo i{width:36px;height:34px;clip-path:polygon(25% 3%,75% 3%,100% 50%,75% 97%,25% 97%,0 50%);background:var(--neon);filter:drop-shadow(0 0 10px rgba(249,176,6,.45))}
.logo b{display:block;font-family:var(--display);font-size:16px;font-weight:700;letter-spacing:.02em}.logo span{display:block;font-family:var(--mono);font-size:10.5px;color:var(--accent);text-transform:lowercase;letter-spacing:.04em;font-weight:500}
.nav{flex:1;overflow:auto;display:flex;flex-direction:column;gap:2px}
.nav .t{font-family:var(--mono);font-size:11px;text-transform:lowercase;letter-spacing:.02em;color:var(--accent);font-weight:500;padding:4px 10px 8px}.nav .t::before{content:"// "}
.nav a{display:flex;align-items:center;gap:10px;padding:7px 10px;border-radius:9px;color:var(--body);text-decoration:none;font-size:13px}
.nav a i{width:8px;height:8px;clip-path:polygon(25% 3%,75% 3%,100% 50%,75% 97%,25% 97%,0 50%);background:#2E281F}
.nav a:hover{background:rgba(244,239,230,.04);color:var(--ink)}
.nav a.on{background:var(--accent-soft);color:var(--ink);box-shadow:inset 2px 0 0 var(--accent)}.nav a.on i{background:var(--accent)}
.main{min-width:0;padding:26px 34px 56px}.wrap{max-width:1520px;margin:0 auto}
.eyebrow{display:inline-flex;align-items:center;font-family:var(--mono);font-size:13px;text-transform:lowercase;letter-spacing:.01em;font-weight:500;color:var(--accent)}
.eyebrow::before{content:"// "}
h1{font-family:var(--display);font-size:44px;font-weight:700;letter-spacing:-.012em;line-height:1.05;margin:12px 0 16px}
h2{font-family:var(--display);font-size:18px;font-weight:700;letter-spacing:-.005em}
h2::before{content:"";display:inline-block;width:11px;height:10px;clip-path:polygon(25% 3%,75% 3%,100% 50%,75% 97%,25% 97%,0 50%);margin:0 10px 2px 0;background:var(--neon);vertical-align:middle}
.sub{font-size:12px;color:var(--muted);margin:3px 0 14px}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{background:rgba(26,23,18,.8);border:1px solid var(--line);border-radius:8px;padding:5px 11px;color:var(--muted);font-family:var(--mono);font-size:11px;text-transform:lowercase;letter-spacing:.02em;font-weight:500}
.chip b{color:var(--ink);font-family:var(--sans);font-weight:600;font-size:12.5px;text-transform:none;letter-spacing:0;margin-left:6px}
main.grid{display:grid;gap:18px;grid-template-columns:repeat(12,minmax(0,1fr));margin-top:22px}
.card{position:relative;border-radius:20px;padding:20px 22px 22px;grid-column:span 12;min-width:0;overflow:hidden;scroll-margin-top:20px;border:1px solid transparent;
  background:linear-gradient(180deg,var(--surface-2),var(--surface)) padding-box,linear-gradient(180deg,rgba(244,239,230,.11),rgba(244,239,230,.03) 45%,rgba(244,239,230,.05)) border-box;
  box-shadow:0 24px 48px -32px rgba(0,0,0,.9)}
.c6{grid-column:span 6}
@media(max-width:1100px){.app{grid-template-columns:minmax(0,1fr)}.side{position:sticky;top:0;z-index:5;height:auto;flex-direction:row;align-items:center;padding:10px 14px;border:0;border-bottom:1px solid var(--line)}
  .logo{border:0;padding:0}.logo span{display:none}.nav{flex-direction:row;overflow-x:auto;min-width:0;flex:1 1 0}.nav .t{display:none}.nav a{white-space:nowrap}.c6{grid-column:span 12}.main{padding:20px 16px}}
@media(max-width:760px){h1{font-size:26px}.kpis{grid-template-columns:repeat(2,minmax(0,1fr))!important}}
.banner{position:relative;display:flex;align-items:center;gap:16px;padding:18px 22px;border-radius:16px;font-weight:600;font-size:16px;border:1px solid transparent;
  background:linear-gradient(100deg,var(--tint),transparent 55%) padding-box,linear-gradient(180deg,#1E1A14,#1A1712) padding-box,linear-gradient(90deg,var(--edge),rgba(244,239,230,.05) 60%) border-box}
.banner .bic{width:40px;height:40px;border-radius:12px;display:grid;place-items:center;font-weight:800;font-size:18px;flex:none}
.banner.ok{--tint:rgba(92,191,74,.16);--edge:rgba(92,191,74,.55)}.banner.ok .bic{background:rgba(92,191,74,.18);color:#7BD36A}
.banner.err{--tint:rgba(255,90,78,.18);--edge:rgba(255,90,78,.6)}.banner.err .bic{background:rgba(255,90,78,.2);color:#FF7B70}
.banner.warn{--tint:rgba(255,214,10,.13);--edge:rgba(255,214,10,.5)}.banner.warn .bic{background:rgba(255,214,10,.16);color:#FFD60A}
.note{color:var(--muted);margin-top:12px}.note.err{color:#FF8F85}
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin-top:18px}
.kpi{position:relative;border-radius:16px;padding:16px 18px;display:flex;flex-direction:column;min-height:132px;overflow:hidden;border:1px solid transparent;
  background:linear-gradient(180deg,#221E17,#1E1A14) padding-box,linear-gradient(180deg,rgba(244,239,230,.1),rgba(244,239,230,.03)) border-box}
.kpi::after{content:"";position:absolute;width:160px;height:160px;right:-60px;top:-80px;border-radius:50%;background:radial-gradient(circle,var(--glow,rgba(249,176,6,.15)),transparent 70%)}
.kpi.ok{--glow:rgba(92,191,74,.16)}.kpi.err{--glow:rgba(255,90,78,.2)}
.kpi .ic{width:38px;height:38px;border-radius:11px;display:grid;place-items:center;color:var(--accent);background:var(--accent-soft);box-shadow:inset 0 0 0 1px rgba(249,176,6,.18)}
.kpi.ok .ic{color:#7BD36A;background:rgba(92,191,74,.13)}.kpi.err .ic{color:#FF7B70;background:rgba(255,90,78,.15)}
.kpi .st{position:absolute;top:16px;right:16px;font-size:10.5px;font-weight:650;text-transform:uppercase;letter-spacing:.08em;padding:3px 8px;border-radius:999px}
.kpi.ok .st{color:#7BD36A;background:rgba(92,191,74,.12)}.kpi.err .st{color:#FF7B70;background:rgba(255,90,78,.14)}
.kpi .et{color:var(--muted);font-size:11.5px;font-weight:550;margin-top:auto;padding-top:14px}
.kpi .v{font-size:30px;font-weight:650;letter-spacing:-.035em;line-height:1.1;margin-top:4px}
.bars{display:flex;flex-direction:column;gap:6px;margin-top:4px}
.bar{display:grid;grid-template-columns:110px 1fr 80px;gap:14px;align-items:center;padding:6px 8px;margin:0 -8px;border-radius:10px}
.bar:hover{background:rgba(244,239,230,.03)}
.bar .et{color:var(--body);font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.track{height:12px;background:rgba(244,239,230,.045);border-radius:999px;overflow:hidden}
.fill{display:block;height:100%;border-radius:999px}
.bar .val{text-align:right;font-weight:620;font-variant-numeric:tabular-nums}
svg{width:100%;height:auto;display:block;overflow:visible}
.axis{font-size:11px;fill:var(--muted);font-variant-numeric:tabular-nums;font-family:var(--sans)}.grid-l{stroke:rgba(244,239,230,.05)}.base{stroke:rgba(244,239,230,.12)}
.value{font-size:12px;fill:var(--ink);font-weight:620;font-family:var(--sans)}
.hit rect{fill:transparent}.hit .cross{stroke:rgba(244,239,230,.25);opacity:0}.hit:hover .cross{opacity:1}
.hit circle{opacity:0}.hit:hover circle{opacity:1}
.table{overflow-x:auto;margin:0 -22px -22px}
table{width:100%;border-collapse:collapse;font-size:13.5px;font-variant-numeric:tabular-nums}
th{color:var(--muted);font-size:10.5px;text-transform:uppercase;letter-spacing:.12em;font-weight:650;text-align:left;padding:11px 22px;white-space:nowrap;
  background:rgba(244,239,230,.025);border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
td{padding:13px 22px;border-bottom:1px solid var(--line);color:var(--body);white-space:nowrap}
tbody tr:last-child td{border-bottom:0}
td:first-child{white-space:normal;word-break:break-word}
tbody tr:hover td{background:rgba(244,239,230,.025)}
code{font-family:var(--mono);font-size:12.5px;color:var(--ink)}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;padding:3px 10px;border-radius:999px;color:var(--ink)}
.pill.ok{background:rgba(92,191,74,.13);box-shadow:inset 0 0 0 1px rgba(92,191,74,.34)}.pill.ok b{color:var(--ok)}
.pill.err{background:rgba(255,90,78,.13);box-shadow:inset 0 0 0 1px rgba(255,90,78,.38)}.pill.err b{color:var(--err)}
.muted{color:var(--muted)}.empty{color:#7BD36A}
#tip{position:fixed;z-index:10;pointer-events:none;opacity:0;transition:opacity .12s;background:rgba(26,23,18,.97);border:1px solid var(--line-2);border-radius:12px;padding:9px 12px;
  font-size:12.5px;color:var(--ink);box-shadow:0 18px 40px rgba(0,0,0,.65);white-space:pre-line}#tip.on{opacity:1}
footer{margin:32px auto 0;color:var(--muted);font-size:12px;text-align:center}
@media print{.side{display:none}.app{display:block}}`;

const JS = `(function(){var t=document.createElement('div');t.id='tip';document.body.appendChild(t);
document.addEventListener('mousemove',function(e){var el=e.target.closest('[data-tip]');if(!el){t.className='';return;}
t.textContent=el.getAttribute('data-tip');t.className='on';var w=t.offsetWidth,h=t.offsetHeight;
t.style.left=Math.max(8,Math.min(e.clientX+14,innerWidth-w-8))+'px';t.style.top=(e.clientY-h-12<4?e.clientY+16:e.clientY-h-12)+'px';});
var nav=document.getElementById('nav'),cs=[].slice.call(document.querySelectorAll('main.grid > .card'));
var tt=document.createElement('div');tt.className='t';tt.textContent='In this report';nav.appendChild(tt);
cs.forEach(function(c,i){var h=c.querySelector('h2');var txt=h?h.textContent:(i===0?'Summary':'Section');c.id='s'+i;
var a=document.createElement('a');a.href='#s'+i;a.innerHTML='<i></i>';a.appendChild(document.createTextNode(txt));nav.appendChild(a);c._a=a;});
if('IntersectionObserver' in window){var vis={};var io=new IntersectionObserver(function(es){es.forEach(function(en){vis[en.target.id]=en.isIntersecting;});
for(var i=0;i<cs.length;i++){if(vis[cs[i].id]){cs.forEach(function(x){x._a.classList.remove('on');});cs[i]._a.classList.add('on');break;}}},{rootMargin:'-10% 0px -60% 0px'});
cs.forEach(function(c){io.observe(c);});}})();`;

function bars(items, fmt) {
  if (!items.length) return '<p class="muted">No data.</p>';
  const max = Math.max(1, ...items.map((i) => i.value || 0));
  return `<div class="bars">${items.map((i) => `
    <div class="bar" data-tip="${esc(i.label)}: ${esc(fmt(i.value))}"><span class="et">${esc(i.label)}</span>
      <span class="track"><span class="fill" style="width:${Math.max(0.8, ((i.value || 0) / max) * 100).toFixed(1)}%;background:${i.color || SERIES[0]}"></span></span>
      <span class="val">${esc(fmt(i.value))}</span></div>`).join('')}</div>`;
}

// "Round" maximum for 4 grid lines.
function scale(max) {
  if (!(max > 0)) return [1, 0.25];
  const exp = 10 ** Math.floor(Math.log10(max));
  for (const m of [1, 2, 2.5, 5, 10]) if ((m * exp) >= max) return [m * exp, (m * exp) / 4];
  return [max, max / 4];
}

// Smooth monotone curve (Fritsch–Carlson): goes through the points without inventing peaks.
function curve(p) {
  const n = p.length;
  if (n < 3) return p.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const m = [];
  for (let i = 0; i < n - 1; i++) m.push((p[i + 1][1] - p[i][1]) / ((p[i + 1][0] - p[i][0]) || 1));
  const t = [m[0]];
  for (let i = 1; i < n - 1; i++) t.push(m[i - 1] * m[i] <= 0 ? 0 : (m[i - 1] + m[i]) / 2);
  t.push(m[n - 2]);
  for (let i = 0; i < n - 1; i++) {
    if (m[i] === 0) { t[i] = 0; t[i + 1] = 0; continue; }
    const a = t[i] / m[i], b = t[i + 1] / m[i], s = a * a + b * b;
    if (s > 9) { const k = 3 / Math.sqrt(s); t[i] = k * a * m[i]; t[i + 1] = k * b * m[i]; }
  }
  let d = `M${p[0][0].toFixed(1)},${p[0][1].toFixed(1)}`;
  for (let i = 0; i < n - 1; i++) {
    const h = (p[i + 1][0] - p[i][0]) / 3;
    d += ` C${(p[i][0] + h).toFixed(1)},${(p[i][1] + t[i] * h).toFixed(1)} ${(p[i + 1][0] - h).toFixed(1)},${(p[i + 1][1] - t[i + 1] * h).toFixed(1)} ${p[i + 1][0].toFixed(1)},${p[i + 1][1].toFixed(1)}`;
  }
  return d;
}

let gradients = 0;
// Single-series line on one axis (smooth curve with a gradient area), label at the maximum
// and the last value, crosshair and tooltip per interval.
function lineGraph(points, key, color, fmt, name, W = 700) {
  const pts = points.filter((p) => p[key] != null);
  if (pts.length < 2) return '<p class="muted">Run too short: fewer than two 10 s intervals.</p>';
  const H = 260, left = 58, right = 14, top = 22, bottom = 28;
  const [max, step] = scale(Math.max(...pts.map((p) => p[key])));
  const t0 = pts[0].t, range = (pts[pts.length - 1].t - t0) || 1;
  const px = (t) => left + ((t - t0) / range) * (W - left - right);
  const py = (v) => top + (H - top - bottom) * (1 - v / max);
  let svg = '';
  for (let v = 0; v <= max + 1e-9; v += step) {
    svg += `<line class="${v === 0 ? 'base' : 'grid-l'}" x1="${left}" x2="${W - right}" y1="${py(v).toFixed(1)}" y2="${py(v).toFixed(1)}"/>`
      + `<text class="axis" x="${left - 10}" y="${(py(v) + 4).toFixed(1)}" text-anchor="end">${esc(fmt(v))}</text>`;
  }
  const d = curve(pts.map((p) => [px(p.t), py(p[key])]));
  const gid = `g${++gradients}`;
  svg += `<defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${color}" stop-opacity=".32"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></linearGradient></defs>`
    + `<path d="${d} L${px(pts[pts.length - 1].t).toFixed(1)},${py(0).toFixed(1)} L${px(t0).toFixed(1)},${py(0).toFixed(1)} Z" fill="url(#${gid})"/>`
    + `<path d="${d}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
  if (pts.length <= 40) svg += pts.map((p) => `<circle cx="${px(p.t).toFixed(1)}" cy="${py(p[key]).toFixed(1)}" r="3.5" fill="${color}" stroke="${SURFACE}" stroke-width="2"/>`).join('');
  const iMax = pts.reduce((m, p, i) => (p[key] > pts[m][key] ? i : m), 0);
  for (const i of new Set([iMax, pts.length - 1])) {
    svg += `<text class="value" x="${px(pts[i].t).toFixed(1)}" y="${(py(pts[i][key]) - 10).toFixed(1)}" text-anchor="middle">${esc(fmt(pts[i][key]))}</text>`;
  }
  pts.forEach((p, i) => {
    const a = i ? (px(pts[i - 1].t) + px(p.t)) / 2 : px(p.t);
    const b = i < pts.length - 1 ? (px(p.t) + px(pts[i + 1].t)) / 2 : px(p.t);
    svg += `<g class="hit" data-tip="${esc(duration((p.t - t0) / 1000))}\n${esc(name)}: ${esc(fmt(p[key]))}${p.errors ? `\nerrors: ${p.errors}` : ''}">`
      + `<rect x="${a.toFixed(1)}" y="${top}" width="${Math.max(b - a, 1).toFixed(1)}" height="${H - top - bottom}"/>`
      + `<line class="cross" x1="${px(p.t).toFixed(1)}" x2="${px(p.t).toFixed(1)}" y1="${top}" y2="${H - bottom}"/>`
      + `<circle cx="${px(p.t).toFixed(1)}" cy="${py(p[key]).toFixed(1)}" r="5.5" fill="${color}" stroke="${SURFACE}" stroke-width="2"/></g>`;
  });
  svg += `<text class="axis" x="${left}" y="${H - 6}">0 s</text><text class="axis" x="${W - right}" y="${H - 6}" text-anchor="end">${esc(duration(range / 1000))}</text>`;
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(name)} over time">${svg}</svg>`;
}

function table(headers, rows) {
  if (!rows.length) return '<p class="muted">No data.</p>';
  return `<div class="table"><table><thead><tr>${headers.map((e) => `<th>${esc(e)}</th>`).join('')}</tr></thead>
    <tbody>${rows.map((f) => `<tr>${f.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}

function html(r) {
  const k = r.kpis, l = r.latency;
  const ver = { pass: ['ok', '✓', 'Meets the thresholds'], fail: ['err', '✕', 'Does not meet the thresholds'],
    'no thresholds': ['warn', '!', 'No thresholds defined'], error: ['err', '✕', 'The run ended with an error'] }[r.verdict];
  const kpi = (et, val, cls = '', ic = 'list') => `<div class="kpi ${cls}"><div class="ic">${icon(ic)}</div>`
    + `${cls ? `<span class="st">${cls === 'ok' ? '✓ OK' : '✕ Critical'}</span>` : ''}<div class="et">${et}</div><div class="v">${val}</div></div>`;
  const codeColor = (c) => (c === 'no response' || Number(c) >= 500 ? STATUS.err : Number(c) >= 400 ? STATUS.serious : Number(c) >= 300 ? STATUS.warn : STATUS.ok);
  const codes = Object.entries(r.codes).map(([c, n]) => ({ label: c, value: n, color: codeColor(c) }));
  const pill = (ok) => (ok ? '<span class="pill ok"><b>✓</b>Pass</span>' : '<span class="pill err"><b>✕</b>Fail</span>');
  const evolution = r.tool === 'k6'
    ? '<section class="card"><h2>Evolution over time</h2><p class="muted">k6 only provides the final summary; the evolution is available in Artillery and JMeter runs.</p></section>'
    : `<section class="card c6"><h2>Throughput</h2><p class="sub">req/s per 10 s interval</p>${lineGraph(r.timeline, 'rps', SERIES[0], (v) => (v >= 10 ? v.toFixed(0) : v >= 1 ? v.toFixed(1) : v.toFixed(2)), 'req/s')}</section>
  <section class="card c6"><h2>p95 latency</h2><p class="sub">p95 per 10 s interval</p>${lineGraph(r.timeline, 'p95', SERIES[1], ms, 'p95')}</section>`;

  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="dark">
<title>Performance · ${esc(r.script)} · ${esc(r.profile)}</title><style>${FONTS}${CSS}</style></head><body>
<div class="app"><aside class="side"><div class="logo"><i></i><div><b>k0lmena</b><span>Performance</span></div></div><nav class="nav" id="nav"></nav></aside>
<div class="main"><div class="wrap">
<header>
  <span class="eyebrow">Performance · ${esc(r.profile)}</span>
  <h1>${esc(r.script)}</h1>
  <div class="chips">
    <span class="chip">Tool <b>${esc(r.tool)}</b></span><span class="chip">Profile <b>${esc(r.profile)}</b></span>
    <span class="chip">Target <b>${esc(r.target || '—')}</b></span><span class="chip">Date <b>${esc(formatDate(r.date))}</b></span>
    <span class="chip">Duration <b>${duration(r.duration_s)}</b></span>
  </div>
</header>
<main class="grid">
  <section class="card"><div class="banner ${ver[0]}"><span class="bic">${ver[1]}</span>${ver[2]}</div>
    ${r.profile === 'smoke' ? '<p class="note">Smoke profile: minimal load to validate that the script works; it does not represent the target load.</p>' : ''}
    ${r.error ? `<p class="note err">${esc(r.error)}</p>` : ''}
    <div class="kpis">
      ${kpi('Requests', integer(k.requests), '', 'load')}${kpi('Average req/s', k.rps == null ? '—' : k.rps.toFixed(2), '', 'bolt')}
      ${kpi('Errors', k.error_pct == null ? '—' : `${k.error_pct.toFixed(2)} %`, k.error_pct > 0 ? 'err' : 'ok', 'warn')}
      ${kpi('p50', ms(l.p50), '', 'clock')}${kpi('p95', ms(l.p95), '', 'clock')}${kpi('p99', ms(l.p99), '', 'clock')}
      ${kpi(r.tool === 'artillery' ? 'Users created' : 'Max users', integer(k.max_users), '', 'person')}
      ${kpi({ k6: 'Iterations', artillery: 'Completed flows', jmeter: 'Samples with errors' }[r.tool], integer(k.iterations), '', 'list')}
    </div>
  </section>
  <section class="card"><h2>Thresholds</h2><p class="sub">acceptance criteria of the run</p>
    ${r.thresholds.length ? table(['Metric', 'Condition', 'Measured value', 'Result'], r.thresholds.map((u) => [`<code>${esc(u.metric)}</code>`, esc(u.condition), esc(u.value), pill(u.ok)])) : '<p class="muted">The script does not define thresholds: the run has no acceptance criteria.</p>'}
  </section>
  ${evolution}
  <section class="card c6"><h2>Latency</h2><p class="sub">${esc(l.source)}</p>
    ${bars([{ label: 'p50', value: l.p50 }, { label: 'p90', value: l.p90 }, { label: 'p95', value: l.p95 }, { label: 'p99', value: l.p99 }, { label: 'average', value: l.avg }, { label: 'max', value: l.max }].filter((b) => b.value != null), ms)}
  </section>
  <section class="card c6"><h2>Response codes</h2><p class="sub">number of responses per HTTP code</p>${codes.length ? bars(codes, integer) : '<p class="muted">No response code data.</p>'}</section>
  <section class="card"><h2>${esc(r.detail.title)}</h2><p class="sub">sorted by count</p>
    ${table(['Name', 'Count', 'Average', 'p95', 'p99', 'Max'], r.detail.rows.map((f) => [`<code>${esc(f.name)}</code>`, integer(f.requests), ms(f.avg), ms(f.p95), ms(f.p99), ms(f.max)]))}
  </section>
  ${r.checks.length ? `<section class="card c6"><h2>Checks</h2>${table(['Check', 'Passed', 'Failed'], r.checks.map((c) => [esc(c.name), integer(c.passes), c.fails ? `<span class="pill err"><b>✕</b>${integer(c.fails)}</span>` : '0']))}</section>` : ''}
  <section class="card ${r.checks.length ? 'c6' : ''}"><h2>Errors</h2>
    ${Object.keys(r.errors).length ? table(['Error', 'Count'], Object.entries(r.errors).sort((a, b) => b[1] - a[1]).map(([e, n]) => [esc(e), `<span class="pill err"><b>✕</b>${integer(n)}</span>`])) : '<p class="empty">✓ No errors.</p>'}
  </section>
</main>
<footer>k0lmenIA · In this folder: raw result <code>${esc(path.basename(r.files.raw))}</code> · log <code>${esc(path.basename(r.files.log))}</code></footer>
</div></div></div><script>${JS}</script>
</body></html>`;
}

// ---------------------------------------------------------------- API
/**
 * @param {object} o { tool: 'k6'|'artillery'|'jmeter', script, profile, target, raw, log, output, exitCode,
 *                     thresholds (JMeter only: the ones from <script>.json) }
 * @returns {object} summary (also written to <output>.json, and the HTML to <output>.html)
 */
function generateReport(o) {
  const text = fs.existsSync(o.raw) ? fs.readFileSync(o.raw, 'utf8') : '';
  let raw = null;
  if (text.trim()) {
    try {
      raw = o.tool === 'jmeter' ? text : JSON.parse(text);
    } catch {
      raw = null; // truncated result (the run was cut short): reported as an error, the report does not crash
    }
  }
  const log = fs.existsSync(o.log) ? fs.readFileSync(o.log, 'utf8') : '';
  const base = { tool: o.tool, script: o.script, profile: o.profile, target: o.target, date: new Date().toISOString() };
  let r;
  if (!raw) {
    r = { ...base, duration_s: null, kpis: {}, latency: { source: '—' }, thresholds: [], detail: { title: 'Detail', rows: [] }, codes: {}, checks: [], errors: {}, timeline: [],
      error: `The tool did not produce results (exit code ${o.exitCode}). Check the log.` };
  } else {
    const from = { k6: () => fromK6(raw), artillery: () => fromArtillery(raw, log), jmeter: () => fromJMeter(raw, o.thresholds) };
    r = { ...base, ...from[o.tool]() };
  }
  // k6 exits with 99 and Artillery with 1 when a threshold fails; any other code is a run error.
  // JMeter exits with 0 even if samples fail: the thresholds are evaluated by this report.
  const thresholdFails = r.thresholds.some((u) => !u.ok);
  if (!raw || (o.exitCode && !thresholdFails && ![0, 99].includes(o.exitCode))) {
    r.verdict = 'error';
    r.error = r.error || `The tool exited with code ${o.exitCode}. Check the log.`;
  } else {
    r.verdict = !r.thresholds.length ? 'no thresholds' : thresholdFails ? 'fail' : 'pass';
  }
  r.files = { html: `${o.output}.html`, summary: `${o.output}.json`, raw: o.raw, log: o.log };

  fs.mkdirSync(path.dirname(o.output), { recursive: true });
  fs.writeFileSync(`${o.output}.json`, JSON.stringify(r, null, 2));
  fs.writeFileSync(`${o.output}.html`, html(r));
  return r;
}

module.exports = { generateReport };
