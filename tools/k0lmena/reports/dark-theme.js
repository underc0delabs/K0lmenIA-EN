// reports/dark-theme.js — k0lmenIA theme for the multiple-cucumber-html-reporter reports
// (web, api and mobile). It locks the reports in dark mode, with the k0lmena.com style and the same
// palette as the rest of the reports (scripts/_report_styles.py): background, cards, borders and the status
// colors their charts use (ApexCharts reads them from the --status-* variables).
//
//   const { reportOptions, applyTheme } = require('../dark-theme');
//   await reporter.generate({ ...reportOptions('Web'), jsonDir, reportPath });
//   applyTheme(reportPath);
const fs = require('fs');
const path = require('path');
// The root .env (base URL, browser, device…) for the report header data.
try {
  require('../env');
} catch {
  // without dotenv installed (for example, in the repo tests): the header data shows "—"
}

// k0lmena.com palette (night, charcoal, wax and amber) with the data colors validated for the
// dark surface (CVD and contrast, dataviz skill): the same as scripts/_report_styles.py.
const TOKENS = {
  '--background': '#0E0C09',
  '--foreground': '#F4EFE6',
  '--card': '#1A1712',
  '--card-foreground': '#F4EFE6',
  '--popover': '#221E17',
  '--popover-foreground': '#F4EFE6',
  '--primary': '#F9B006',
  '--primary-foreground': '#0E0C09',
  '--secondary': '#221E17',
  '--secondary-foreground': '#F4EFE6',
  '--muted': '#221E17',
  '--muted-foreground': '#8A8172',
  '--accent': '#2E2412',
  '--accent-foreground': '#FFE58A',
  '--destructive': '#FF5A4E',
  '--border': '#2E281F',
  '--input': '#2E281F',
  '--ring': '#F9B006',
  '--chart-1': '#C98500',
  '--chart-2': '#14A895',
  '--chart-3': '#4C8DEB',
  '--chart-4': '#E0702E',
  '--chart-5': '#9085E9',
  // Cucumber statuses (always accompanied by the status name in the report)
  '--status-passed': '#5CBF4A',
  '--status-failed': '#FF5A4E',
  '--status-ambiguous': '#FF8A00',
  '--status-undefined': '#FFD60A',
  '--status-pending': '#9085E9',
  '--status-skipped': '#8A8172',
  '--font-sans': '"Inter",ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif',
  '--radius': '0.875rem',
};

// Embedded k0lmena.com typography (scripts/fonts, OFL license): works offline.
const FONTS = (() => {
  const dir = path.resolve(__dirname, '..', '..', '..', 'scripts', 'fonts');
  return [['Saira', 'saira.woff2', '500 700'], ['Inter', 'inter.woff2', '400 600'], ['JetBrains Mono', 'jetbrains-mono.woff2', '400 700']]
    .map(([family, file, weights]) => {
      try {
        return `@font-face{font-family:'${family}';font-weight:${weights};font-display:swap;src:url(data:font/woff2;base64,${fs.readFileSync(path.join(dir, file)).toString('base64')}) format('woff2')}`;
      } catch {
        return '';
      }
    }).join('');
})();

// k0lmena.com honeycomb pattern (header background).
const HONEYCOMB = "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='56' height='100'%3E%3Cpath d='M28 66L0 50L0 16L28 0L56 16L56 50L28 66L28 100' fill='none' stroke='%23F9B006' stroke-opacity='.10' stroke-width='1.2'/%3E%3Cpath d='M28 0L28 34L0 50L0 84L28 100L56 84L56 50L28 34' fill='none' stroke='%23F9B006' stroke-opacity='.07' stroke-width='1.2'/%3E%3C/svg%3E\")";

const STYLE = `
<style id="k0lmena-theme">
${FONTS}
html.dark,:root.dark{${Object.entries(TOKENS).map(([k, v]) => `${k}:${v}`).join(';')}}
html.dark{color-scheme:dark}
html.dark body{
  background:radial-gradient(760px 420px at 100% -8%,rgba(249,176,6,.12),transparent 62%),
             ${HONEYCOMB} 0 0/56px 100px,var(--background) !important;
  background-attachment:fixed !important;font-family:var(--font-sans) !important;-webkit-font-smoothing:antialiased;
}
html.dark main,html.dark .container,html.dark .max-w-7xl,html.dark .max-w-6xl,html.dark .max-w-screen-xl{max-width:1480px !important;margin-left:auto !important;margin-right:auto !important}
html.dark .bg-card{border:1px solid transparent !important;border-radius:14px !important;
  background:linear-gradient(180deg,#1E1A14,#1A1712) padding-box,linear-gradient(180deg,rgba(244,239,230,.12),rgba(244,239,230,.04) 45%,rgba(244,239,230,.06)) border-box !important;
  box-shadow:0 24px 48px -32px rgba(0,0,0,.9) !important}
html.dark h1,html.dark h2,html.dark h3{font-family:"Saira","Inter",ui-sans-serif,system-ui,sans-serif !important;font-weight:700 !important;letter-spacing:-.012em}
html.dark header,html.dark nav{background:rgba(14,12,9,.85) !important;backdrop-filter:blur(10px);border-color:var(--border) !important}
html.dark table{font-variant-numeric:tabular-nums}
html.dark thead th{font-family:"JetBrains Mono",ui-monospace,Consolas,monospace !important;font-size:11px !important;text-transform:lowercase;letter-spacing:.02em;color:var(--muted-foreground) !important;background:rgba(244,239,230,.025)}
html.dark table tbody tr:hover td{background:rgba(249,176,6,.035)}
html.dark code,html.dark pre,html.dark .font-mono{font-family:"JetBrains Mono",ui-monospace,Consolas,monospace !important}
html.dark a{color:#F9B006}
html.dark .apexcharts-tooltip{background:#1A1712 !important;border:1px solid rgba(249,176,6,.38) !important;color:var(--foreground) !important;
  box-shadow:0 14px 34px rgba(0,0,0,.6) !important;border-radius:12px !important}
html.dark .apexcharts-legend-text{color:#CFC7B8 !important}
#theme-toggle{display:none !important}
</style>
<script id="k0lmena-dark">document.documentElement.classList.add('dark');try{localStorage.setItem('theme','dark')}catch(e){}</script>`;

/** URL to show in the report, without user or password (https://user:pass@host → https://host). */
function safeUrl(url) {
  if (!url) return '—';
  try {
    const u = new URL(url);
    u.username = '';
    u.password = '';
    return u.toString().replace(/\/$/, '');
  } catch {
    return '(invalid URL)';
  }
}

/** Common options for reporter.generate(): English title and percentages on the donuts. */
function reportOptions(type) {
  return {
    pageTitle: `k0lmena · ${type} Report`,
    reportName: `k0lmena · ${type} Run Report`,
    displayDuration: true,
    displayChartPercentages: true,
  };
}

function htmls(dir) {
  const output = [];
  if (!fs.existsSync(dir)) return output;
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) output.push(...htmls(p));
    else if (e.name.toLowerCase().endsWith('.html')) output.push(p);
  }
  return output;
}

/** Injects the theme into an HTML (before </head>, after the reporter's styles). */
function themeInHtml(html) {
  if (html.includes('id="k0lmena-theme"') || !/<\/head>/i.test(html)) return html;
  // The theme stays locked in dark: the reporter's script that adds the light/dark button is removed.
  html = html.replace(/<script[^>]+src=["'][^"']*darkmode\.js[^"']*["'][^>]*>\s*<\/script>\s*/gi, '');
  html = html.replace(/<html([^>]*)>/i, (m, attrs) => (/class=/i.test(attrs)
    ? `<html${attrs.replace(/class=(["'])([^"']*)\1/i, (x, q, c) => `class=${q}${c} dark${q}`)}>`
    : `<html${attrs} class="dark">`));
  return html.replace(/<\/head>/i, `${STYLE}\n</head>`);
}

/** Applies the theme to every .html in the report folder (and subfolders). */
function applyTheme(dir) {
  let n = 0;
  for (const file of htmls(dir)) {
    const before = fs.readFileSync(file, 'utf8');
    const after = themeInHtml(before);
    if (after !== before) {
      fs.writeFileSync(file, after, 'utf8');
      n++;
    }
  }
  return n;
}

/** Waits for the reporter to finish writing the HTML files (it writes in the background). */
async function waitForHtml(dir, timeoutMs = 15000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {

    if (fs.existsSync(path.join(dir, 'index.html'))) return true;
    await new Promise((r) => setTimeout(r, 200));
  }
  return false;
}

module.exports = { reportOptions, applyTheme, themeInHtml, waitForHtml, safeUrl, TOKENS };
