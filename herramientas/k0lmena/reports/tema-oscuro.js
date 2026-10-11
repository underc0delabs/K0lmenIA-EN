// reports/tema-oscuro.js — tema de k0lmenIA para los reportes de multiple-cucumber-html-reporter
// (web, api y mobile). Deja los reportes en modo oscuro fijo y con la misma paleta que el resto
// de los informes (scripts/_estilos_reporte.py): fondo, tarjetas, bordes y los colores de estado
// que usan sus gráficos (ApexCharts los lee de las variables --status-*).
//
//   const { opcionesReporte, aplicarTema } = require('../tema-oscuro');
//   await reporter.generate({ ...opcionesReporte('Web'), jsonDir, reportPath });
//   aplicarTema(reportPath);
const fs = require('fs');
const path = require('path');
// El .env de la raíz (URL base, navegador, dispositivo…) para los datos del encabezado del reporte.
try {
  require('../env');
} catch {
  // sin dotenv instalado (por ejemplo, en los tests del repo): los datos del encabezado quedan con "—"
}

// Paleta validada para la superficie oscura (CVD y contraste, skill dataviz).
const TOKENS = {
  '--background': '#08090C',
  '--foreground': '#F3F5F8',
  '--card': '#111318',
  '--card-foreground': '#F3F5F8',
  '--popover': '#15181D',
  '--popover-foreground': '#F3F5F8',
  '--primary': '#14A895',
  '--primary-foreground': '#0B0D11',
  '--secondary': '#1A1E25',
  '--secondary-foreground': '#F3F5F8',
  '--muted': '#1A1E25',
  '--muted-foreground': '#7F8896',
  '--accent': '#16302D',
  '--accent-foreground': '#BFF1E9',
  '--destructive': '#D03B3B',
  '--border': '#242A33',
  '--input': '#242A33',
  '--ring': '#14A895',
  '--chart-1': '#14A895',
  '--chart-2': '#E0702E',
  '--chart-3': '#4C8DEB',
  '--chart-4': '#C98500',
  '--chart-5': '#9085E9',
  // Estados de Cucumber (siempre acompañados del nombre del estado en el reporte)
  '--status-passed': '#0CA30C',
  '--status-failed': '#D03B3B',
  '--status-ambiguous': '#EC835A',
  '--status-undefined': '#FAB219',
  '--status-pending': '#9085E9',
  '--status-skipped': '#8B949E',
  '--font-sans': '"Geist","Inter","Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,Roboto,sans-serif',
  '--radius': '1rem',
};

// Tipografía Geist incrustada (scripts/fuentes, licencia OFL): igual sin internet.
const FUENTES = (() => {
  const dir = path.resolve(__dirname, '..', '..', '..', 'scripts', 'fuentes');
  return [['Geist', 'geist-latin-wght-normal.woff2'], ['Geist Mono', 'geist-mono-latin-wght-normal.woff2']].map(([familia, archivo]) => {
    try {
      return `@font-face{font-family:'${familia}';font-weight:100 900;font-display:swap;src:url(data:font/woff2;base64,${fs.readFileSync(path.join(dir, archivo)).toString('base64')}) format('woff2')}`;
    } catch {
      return '';
    }
  }).join('');
})();

const ESTILO = `
<style id="k0lmena-theme">
${FUENTES}
html.dark,:root.dark{${Object.entries(TOKENS).map(([k, v]) => `${k}:${v}`).join(';')}}
html.dark{color-scheme:dark}
html.dark body{
  background:radial-gradient(900px 480px at 18% -12%,rgba(20,168,149,.13),transparent 62%),
             radial-gradient(rgba(255,255,255,.035) 1px,transparent 1px) 0 0/22px 22px,var(--background) !important;
  background-attachment:fixed !important;font-family:var(--font-sans) !important;-webkit-font-smoothing:antialiased;
}
html.dark main,html.dark .container,html.dark .max-w-7xl,html.dark .max-w-6xl,html.dark .max-w-screen-xl{max-width:1480px !important;margin-left:auto !important;margin-right:auto !important}
html.dark .bg-card{border:1px solid transparent !important;border-radius:20px !important;
  background:linear-gradient(180deg,#14171D,#111318) padding-box,linear-gradient(180deg,rgba(255,255,255,.11),rgba(255,255,255,.03) 45%,rgba(255,255,255,.05)) border-box !important;
  box-shadow:0 24px 48px -32px rgba(0,0,0,.9) !important}
html.dark code,html.dark pre{font-family:"Geist Mono",ui-monospace,Consolas,monospace !important}
html.dark h1,html.dark h2,html.dark h3{letter-spacing:-.015em}
html.dark header,html.dark nav{background:rgba(11,13,17,.85) !important;backdrop-filter:blur(10px);border-color:var(--border) !important}
html.dark table{font-variant-numeric:tabular-nums}
html.dark thead th{font-size:10.5px !important;text-transform:uppercase;letter-spacing:.12em;color:var(--muted-foreground) !important;background:rgba(255,255,255,.02)}
html.dark table tbody tr:hover td{background:rgba(255,255,255,.025)}
html.dark code,html.dark pre,html.dark .font-mono{font-family:"JetBrains Mono","Cascadia Code",ui-monospace,Consolas,monospace !important}
html.dark .apexcharts-tooltip{background:#0E1116 !important;border:1px solid var(--border) !important;color:var(--foreground) !important;
  box-shadow:0 14px 34px rgba(0,0,0,.6) !important;border-radius:12px !important}
html.dark .apexcharts-legend-text{color:#B7BECA !important}
#theme-toggle{display:none !important}
</style>
<script id="k0lmena-dark">document.documentElement.classList.add('dark');try{localStorage.setItem('theme','dark')}catch(e){}</script>`;

/** URL para mostrar en el reporte, sin usuario ni contraseña (https://user:pass@host → https://host). */
function urlSegura(url) {
  if (!url) return '—';
  try {
    const u = new URL(url);
    u.username = '';
    u.password = '';
    return u.toString().replace(/\/$/, '');
  } catch {
    return '(URL inválida)';
  }
}

/** Opciones comunes para reporter.generate(): título en español y porcentajes en las donas. */
function opcionesReporte(tipo) {
  return {
    pageTitle: `k0lmena · Reporte ${tipo}`,
    reportName: `k0lmena · Reporte de ejecución ${tipo}`,
    displayDuration: true,
    displayChartPercentages: true,
  };
}

function htmls(dir) {
  const salida = [];
  if (!fs.existsSync(dir)) return salida;
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) salida.push(...htmls(p));
    else if (e.name.toLowerCase().endsWith('.html')) salida.push(p);
  }
  return salida;
}

/** Inyecta el tema en un HTML (antes de </head>, después de los estilos del reporter). */
function temaEnHtml(html) {
  if (html.includes('id="k0lmena-theme"') || !/<\/head>/i.test(html)) return html;
  // El tema queda fijo en oscuro: se quita el script del reporter que agrega el botón claro/oscuro.
  html = html.replace(/<script[^>]+src=["'][^"']*darkmode\.js[^"']*["'][^>]*>\s*<\/script>\s*/gi, '');
  html = html.replace(/<html([^>]*)>/i, (m, attrs) => (/class=/i.test(attrs)
    ? `<html${attrs.replace(/class=(["'])([^"']*)\1/i, (x, q, c) => `class=${q}${c} dark${q}`)}>`
    : `<html${attrs} class="dark">`));
  return html.replace(/<\/head>/i, `${ESTILO}\n</head>`);
}

/** Aplica el tema a todos los .html de la carpeta del reporte (y subcarpetas). */
function aplicarTema(dir) {
  let n = 0;
  for (const archivo of htmls(dir)) {
    const antes = fs.readFileSync(archivo, 'utf8');
    const despues = temaEnHtml(antes);
    if (despues !== antes) {
      fs.writeFileSync(archivo, despues, 'utf8');
      n++;
    }
  }
  return n;
}

/** Espera a que el reporter termine de escribir los HTML (escribe en segundo plano). */
async function esperarHtml(dir, timeoutMs = 15000) {
  const inicio = Date.now();
  while (Date.now() - inicio < timeoutMs) {
    if (fs.existsSync(path.join(dir, 'index.html'))) return true;
    await new Promise((r) => setTimeout(r, 200));
  }
  return false;
}

module.exports = { opcionesReporte, aplicarTema, temaEnHtml, esperarHtml, urlSegura, TOKENS };
