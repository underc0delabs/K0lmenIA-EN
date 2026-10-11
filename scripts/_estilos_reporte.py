#!/usr/bin/env python3
"""
Sistema de diseño de los reportes HTML de k0lmenIA (dashboard moderno, modo oscuro).

Lo usan todos los generadores de entregables HTML (plan de pruebas, reporte de ejecución,
informe de cierre, performance, seguridad, exploratorias y accesibilidad), así todos se ven
igual y el tema vive en un solo lugar.

Página y estructura
  page(titulo, eyebrow, meta_html, body)    documento completo (marca, tooltips, pie)
  meta(items)                               chips de contexto (Historia, Fecha, …)
  section(titulo, body_html, sub="")        tarjeta con su título adentro
  section_group(titulo, body_html, sub="")  título de un grupo de tarjetas (va afuera)
  banner(texto, tono)                       veredicto destacado (ok | warn | bad)
  kpi_tiles(items)                          indicadores (etiqueta, valor, tono[, detalle[, icono]])
  two_col(izq, der)                         grilla de dos columnas
  table(headers, rows)                      tabla (las celdas pueden traer HTML)
  doc_list(items)                           lista con viñetas
  nivel_badge(nivel) / estado_pill(estado)  pastillas con ícono + texto (nunca solo color)
  legend(items)                             leyenda (nombre, color[, valor])

Gráficos (SVG inline, con tooltip al pasar el mouse o con foco)
  donut(segments, pct, label)               dona: segments = [(valor, color[, nombre])]
  donut_panel(segments, pct, label)         dona + leyenda con valor y % (para dentro de section)
  bar_chart(rows)                           barras horizontales: [(etiqueta, valor, color)]
  column_chart(rows, fmt)                   columnas: [(etiqueta, valor[, color])], valor en la punta
  stacked_bars(filas, series)               barras apiladas: filas = [(etiqueta, [v1, v2…])]
  grouped_columns(grupos, series, fmt)      columnas agrupadas, un solo eje
  line_chart(x, series, fmt, area)          líneas suaves sobre un eje, con área y crosshair

Colores (skill dataviz, validados con su script contra la superficie oscura):
  categórica  #14A895 #E0702E #4C8DEB #C98500 #D55181 #9085E9 #E66767 #008300
              (orden fijo, nunca ciclado; las tres primeras pasan también todos los pares)
  estado      ok #0CA30C · aviso #FAB219 · serio #EC835A · crítico #D03B3B (siempre con ícono y texto)
Sin dependencias externas: CSS, SVG y JS van inline, no usa internet.
"""
import html
import math

# ------------------------------------------------------------------ tokens
FONDO = "#0B0D11"
SUPERFICIE = "#15181D"
# Categórica (orden fijo, nunca ciclado): verde azulado, naranja, azul, amarillo, magenta, violeta, rojo, verde
SERIES = ["#14A895", "#E0702E", "#4C8DEB", "#C98500", "#D55181", "#9085E9", "#E66767", "#008300"]
# Estado (reservados: nunca se usan como "serie 4")
OK, AVISO, SERIO, CRITICO, NEUTRO = "#0CA30C", "#FAB219", "#EC835A", "#D03B3B", "#8B949E"
ACENTO = SERIES[0]

PALETA = {"bg": FONDO, "surface": SUPERFICIE, "tile": "#1A1E25", "border": "#242A33",
          "ink": "#F3F5F8", "body": "#B7BECA", "muted": "#7F8896",
          "ok": OK, "bad": CRITICO, "blk": NEUTRO, "warn": AVISO, "accent": ACENTO}

# Niveles / severidades → escala de estado (con su ícono y texto, nunca solo color)
NIVEL_COLOR = {"Alto": CRITICO, "Crítica": CRITICO, "Alta": SERIO, "Medio": AVISO, "Media": AVISO,
               "Bajo": NEUTRO, "Baja": NEUTRO}
NIVEL_ICONO = {"Alto": "▲", "Crítica": "▲", "Alta": "▲", "Medio": "●", "Media": "●", "Bajo": "▼", "Baja": "▼"}
ESTADO_COLOR = {"Aprobado": OK, "Fallido": CRITICO, "Bloqueado": NEUTRO, "Pendiente": AVISO, "N/A": NEUTRO,
                "En ejecución": SERIES[2]}
ESTADO_ICONO = {"Aprobado": "✓", "Fallido": "✕", "Bloqueado": "⊘", "Pendiente": "◷", "N/A": "–", "En ejecución": "▶"}


def _soft(hexcolor, alfa=0.16):
    h = hexcolor.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alfa})"


# Íconos de línea (24x24, trazo 2) para los indicadores. Sin dependencias: SVG inline.
ICONOS = {
    "grid": '<rect x="4" y="4" width="6" height="6" rx="1.5"/><rect x="14" y="4" width="6" height="6" rx="1.5"/><rect x="4" y="14" width="6" height="6" rx="1.5"/><rect x="14" y="14" width="6" height="6" rx="1.5"/>',
    "ok": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.7 2.7L16 9.8"/>',
    "bad": '<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>',
    "warn": '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17.2v.1"/>',
    "blk": '<circle cx="12" cy="12" r="9"/><path d="M6 6l12 12"/>',
    "reloj": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "pagina": '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5M10 13h6M10 17h6"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "imagen": '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="M21 16l-5-5-8 8"/>',
    "codigo": '<path d="M9 8l-4 4 4 4M15 8l4 4-4 4"/>',
    "pantalla": '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M9 20h6M12 16v4"/>',
    "rayo": '<path d="M13 3L5 14h6l-1 7 8-11h-6z"/>',
    "escudo": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
    "teclado": '<rect x="3" y="7" width="18" height="10" rx="2"/><path d="M7 11h.1M11 11h.1M15 11h.1M8 14h8"/>',
    "persona": '<circle cx="12" cy="6" r="2.2"/><path d="M5 9.5l7 1.5 7-1.5M12 11v4l-3 5M12 15l3 5"/>',
    "lista": '<path d="M9 6h11M9 12h11M9 18h11M4.5 6h.1M4.5 12h.1M4.5 18h.1"/>',
    "bicho": '<rect x="8" y="7" width="8" height="12" rx="4"/><path d="M12 7V4M8 11H4M16 11h4M8 15H5M16 15h3M9 5l1.5 2M15 5l-1.5 2"/>',
    "carga": '<path d="M4 18l5-6 4 3 7-9"/><path d="M15 6h5v5"/>',
    "lupa": '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
    "objetivo": '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1"/>',
}


def icono(nombre, tam=20):
    return (f'<svg viewBox="0 0 24 24" width="{tam}" height="{tam}" fill="none" stroke="currentColor" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONOS.get(nombre, ICONOS["grid"])}</svg>')


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{
  color-scheme:dark;
  --bg:#0B0D11; --surface:#15181D; --tile:#1A1E25; --raised:#20252D; --border:#242A33; --border-soft:#1E232A;
  --ink:#F3F5F8; --body:#B7BECA; --muted:#7F8896; --accent:#14A895; --accent-soft:rgba(20,168,149,.14);
  --ok:#0CA30C; --warn:#FAB219; --serious:#EC835A; --bad:#D03B3B; --neutral:#8B949E;
  --radius:18px; --gap:20px;
}
html{-webkit-text-size-adjust:100%}
body{
  background:radial-gradient(1100px 420px at 8% -8%,rgba(20,168,149,.10),transparent 60%),var(--bg);
  background-attachment:fixed;color:var(--ink);font-size:14.5px;
  font-family:"Inter","Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,Roboto,Helvetica,Arial,sans-serif;
  line-height:1.55;padding:40px 36px 56px;-webkit-font-smoothing:antialiased;
}
.wrap{max-width:1480px;margin:0 auto}
.mono{font-family:"JetBrains Mono","Cascadia Code",ui-monospace,Consolas,monospace;font-size:.9em}
.muted{color:var(--muted)}
.eyebrow{font-size:11px;text-transform:uppercase;letter-spacing:.16em;font-weight:650;color:var(--muted)}
a{color:#4FD1BE;text-decoration-color:rgba(79,209,190,.35);text-underline-offset:3px}

/* encabezado */
header{margin-bottom:26px;display:flex;flex-direction:column;gap:14px}
.brand{display:inline-flex;align-self:flex-start;align-items:center;gap:9px;padding:6px 14px 6px 7px;
  border:1px solid var(--border);border-radius:999px;background:rgba(21,24,29,.8)}
.brand .dot{width:24px;height:24px;border-radius:8px;display:grid;place-items:center;font-size:13px;
  background:linear-gradient(135deg,#14A895,#4C8DEB)}
h1{font-size:34px;font-weight:760;letter-spacing:-.03em;line-height:1.1;color:var(--ink)}
.meta{display:flex;flex-wrap:wrap;gap:8px}
.chip{display:inline-flex;align-items:center;gap:7px;font-size:12.5px;color:var(--ink);
  background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:6px 12px}
.chip .k{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.1em;font-weight:650}
.chip a{color:var(--ink);text-decoration:none;border-bottom:1px dashed var(--border)}

/* tarjetas y secciones */
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);
  box-shadow:0 1px 0 rgba(255,255,255,.035) inset,0 18px 40px -28px rgba(0,0,0,.8)}
.section{margin-top:var(--gap)}
.section>.card{overflow:hidden}
.section-title{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;padding:20px 24px 4px}
.section-title h2{font-size:16px;font-weight:680;letter-spacing:-.01em;color:var(--ink)}
.section-title .sub{font-size:12.5px;color:var(--muted)}
.cardbody{padding:16px 24px 22px;color:var(--body)}
.cardbody p{color:var(--body)}
.cardbody p+p{margin-top:10px}
.lead{font-size:15.5px;color:var(--ink);line-height:1.65}
.subhead{font-size:11px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted);font-weight:650;margin-bottom:10px}
.subhead.ok{color:#5BD25B}.subhead.bad{color:#F07272}.subhead.warn{color:#F5C451}

/* hero: dona + indicadores */
.hero{display:grid;grid-template-columns:260px 1fr;gap:28px;align-items:center;padding:26px 28px}
.gauge{display:flex;flex-direction:column;align-items:center;gap:16px}
.donut-num{font-size:34px;font-weight:760;fill:var(--ink);letter-spacing:-.02em}
.donut-lbl{font-size:10px;letter-spacing:.16em;text-transform:uppercase;fill:var(--muted);font-weight:650}
.hero .kpi{background:var(--tile)}
.hero .legend{flex-direction:column;gap:8px;align-self:stretch}

/* dona con leyenda de valores */
.panorama{display:grid;grid-template-columns:200px 1fr;gap:28px;align-items:center;padding:12px 28px 24px}
.dleg{display:flex;flex-direction:column;gap:4px}
.dleg .r{display:grid;grid-template-columns:12px 1fr auto 52px;gap:12px;align-items:center;padding:9px 0;
  border-bottom:1px solid var(--border-soft);font-size:13.5px;color:var(--body)}
.dleg .r:last-child{border-bottom:0}
.dleg i{width:10px;height:10px;border-radius:3px}
.dleg b{color:var(--ink);font-weight:650;font-variant-numeric:tabular-nums}
.dleg em{font-style:normal;color:var(--muted);text-align:right;font-variant-numeric:tabular-nums}
.grupo-titulo{display:flex;align-items:baseline;gap:12px;margin:0 4px 12px}
.grupo-titulo h2{font-size:16px;font-weight:680;letter-spacing:-.01em;color:var(--ink)}
.grupo-titulo .sub{font-size:12.5px;color:var(--muted)}

/* leyenda */
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12.5px;color:var(--body)}
.legend span{display:inline-flex;align-items:center;gap:8px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;flex:none}
.legend b{color:var(--ink);font-weight:650;font-variant-numeric:tabular-nums;margin-left:auto;padding-left:10px}
.legend em{font-style:normal;color:var(--muted);font-variant-numeric:tabular-nums}

/* indicadores */
.kpis{display:grid;grid-template-columns:repeat(var(--cols,4),minmax(0,1fr));gap:16px}
.kpi{position:relative;padding:20px 22px 18px;border:1px solid var(--border);border-radius:16px;background:var(--surface);
  display:flex;flex-direction:column;min-height:138px;box-shadow:0 1px 0 rgba(255,255,255,.03) inset}
.kpi .ic{width:42px;height:42px;border-radius:12px;display:grid;place-items:center;color:var(--accent);background:var(--accent-soft)}
.kpi.ok .ic{color:#3FCB3F;background:rgba(12,163,12,.14)} .kpi.bad .ic{color:#EE6A6A;background:rgba(208,59,59,.16)}
.kpi.warn .ic{color:#FAB219;background:rgba(250,178,25,.13)} .kpi.blk .ic{color:#A9B1BC;background:rgba(139,148,158,.14)}
.kpi .st{position:absolute;top:18px;right:18px;width:22px;height:22px;border-radius:50%;display:grid;place-items:center;
  font-size:12px;font-weight:800;color:#0B0D11}
.kpi.ok .st{background:var(--ok)} .kpi.bad .st{background:var(--bad)} .kpi.warn .st{background:var(--warn)} .kpi.blk .st{background:var(--neutral)}
.kpi .l{font-size:11px;text-transform:uppercase;letter-spacing:.14em;font-weight:650;color:var(--muted);margin-top:auto;padding-top:18px}
.kpi .n{font-size:30px;font-weight:760;letter-spacing:-.025em;line-height:1.1;color:var(--ink);margin-top:6px}
.kpi .d{font-size:12.5px;color:var(--body);margin-top:4px}

/* gráficos */
.chart{padding:10px 24px 20px}
.chart svg{width:100%;height:auto;display:block;overflow:visible}
.chart .legend{margin-top:14px}
.axis{font-size:11px;fill:var(--muted);font-variant-numeric:tabular-nums}
.lbl{font-size:12px;fill:var(--body)}
.val{font-size:12px;fill:var(--ink);font-weight:650;font-variant-numeric:tabular-nums}
.grid{stroke:var(--border-soft);stroke-width:1}
.base{stroke:var(--border);stroke-width:1}
.mark{transition:opacity .15s}
svg:hover .mark{opacity:.5} svg .mark:hover,svg .mark:focus{opacity:1;outline:none}
.hit rect{fill:transparent}
.hit .cross{stroke:var(--muted);stroke-width:1;opacity:0}
.hit:hover .cross{opacity:.6}
.hit circle{opacity:0}.hit:hover circle{opacity:1}

/* barras horizontales */
.bars{padding:14px 24px 22px;display:flex;flex-direction:column;gap:14px}
.bar-row{display:grid;grid-template-columns:var(--lw,120px) 1fr 56px;align-items:center;gap:14px}
.bar-label{font-size:13px;color:var(--body);display:flex;align-items:center;gap:8px;min-width:0}
.bar-label span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bar-wrap{background:rgba(255,255,255,.035);border-radius:0 6px 6px 0;height:12px}
.bar-track{height:12px;border-radius:0 6px 6px 0;display:flex;gap:2px;overflow:hidden}
.bar-track .seg{height:100%;display:block}
.bar-track .seg:last-child{border-radius:0 6px 6px 0}
.bar-count{font-size:13px;color:var(--ink);text-align:right;font-weight:650;font-variant-numeric:tabular-nums}

/* tablas */
.tablecard{overflow-x:auto;padding:6px 0 4px}
table{width:100%;border-collapse:collapse;font-size:13.5px;font-variant-numeric:tabular-nums}
thead th{text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted);
  font-weight:650;padding:12px 18px;white-space:nowrap;background:rgba(255,255,255,.02);
  border-top:1px solid var(--border-soft);border-bottom:1px solid var(--border-soft)}
tbody td{padding:14px 18px;border-bottom:1px solid var(--border-soft);color:var(--body);vertical-align:top}
tbody tr:last-child td{border-bottom:0}
tbody tr{transition:background .12s}
tbody tr:hover td{background:rgba(255,255,255,.025)}
td .id{font-weight:650;color:var(--ink);white-space:nowrap}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:650;padding:4px 11px;border-radius:999px;white-space:nowrap}

/* banner de veredicto */
.banner{position:relative;display:flex;align-items:center;gap:14px;padding:18px 22px 18px 24px;border-radius:16px;
  border:1px solid var(--border);background:var(--surface);font-weight:650;font-size:15.5px;color:var(--ink);overflow:hidden}
.banner::before{content:"";position:absolute;inset:0 auto 0 0;width:4px}
.banner .bic{width:34px;height:34px;border-radius:10px;display:grid;place-items:center;font-size:16px;font-weight:800;flex:none}
.banner.ok{background:linear-gradient(90deg,rgba(12,163,12,.12),transparent 60%),var(--surface)}
.banner.ok::before{background:var(--ok)} .banner.ok .bic{background:rgba(12,163,12,.18);color:#3FCB3F}
.banner.bad{background:linear-gradient(90deg,rgba(208,59,59,.14),transparent 60%),var(--surface)}
.banner.bad::before{background:var(--bad)} .banner.bad .bic{background:rgba(208,59,59,.2);color:#EE6A6A}
.banner.warn{background:linear-gradient(90deg,rgba(250,178,25,.11),transparent 60%),var(--surface)}
.banner.warn::before{background:var(--warn)} .banner.warn .bic{background:rgba(250,178,25,.16);color:#FAB219}

.doclist{list-style:none;display:flex;flex-direction:column;gap:10px}
.doclist li{position:relative;padding-left:22px;color:var(--body)}
.doclist li::before{content:"";position:absolute;left:4px;top:8px;width:8px;height:8px;border-radius:3px;background:var(--accent)}
.twocol{display:grid;grid-template-columns:1fr 1fr;gap:var(--gap);margin-top:var(--gap)}
.section .twocol{margin-top:0}
.twocol>.section{margin-top:0}
.twocol>.section>.card{height:100%}

/* tooltip */
#tip{position:fixed;z-index:20;pointer-events:none;opacity:0;transform:translateY(4px);transition:opacity .12s,transform .12s;
  background:#0E1116;border:1px solid var(--border);border-radius:12px;padding:9px 12px;font-size:12.5px;color:var(--ink);
  box-shadow:0 14px 34px rgba(0,0,0,.6);max-width:320px;white-space:pre-line;font-variant-numeric:tabular-nums}
#tip.on{opacity:1;transform:none}

footer{margin-top:40px;display:flex;justify-content:center;gap:8px;font-size:12px;color:var(--muted)}

@media (max-width:900px){
  body{padding:24px 16px 40px}
  .hero,.panorama{grid-template-columns:1fr;justify-items:center}
  .dleg{width:100%}
  .twocol{grid-template-columns:1fr}
  .kpis{grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:12px}
  .kpi{min-height:128px;padding:16px}
  .kpi .n{font-size:24px}
  .bar-row{grid-template-columns:90px 1fr 44px}
  h1{font-size:26px}
}
@media print{body{background:var(--bg);padding:16px}.card,.kpi{box-shadow:none}#tip{display:none}}
"""

# Tooltip: cualquier elemento con data-tip lo muestra al pasar el mouse o con foco (teclado).
JS = """
(function(){var t=document.createElement('div');t.id='tip';document.body.appendChild(t);
function show(e){var el=e.target.closest('[data-tip]');if(!el){t.className='';return;}
t.textContent=el.getAttribute('data-tip');t.className='on';var r=el.getBoundingClientRect(),x=e.clientX||r.left+r.width/2,y=e.clientY||r.top;
var w=t.offsetWidth,h=t.offsetHeight;t.style.left=Math.max(8,Math.min(x+14,innerWidth-w-8))+'px';t.style.top=(y-h-12<4?y+16:y-h-12)+'px';}
document.addEventListener('mousemove',show);document.addEventListener('focusin',show);
document.addEventListener('mouseleave',function(){t.className='';});})();
"""


def e(s):
    return html.escape(str(s if s is not None else ""))


def page(titulo, eyebrow, meta_html, body):
    return (f'<!doctype html>\n<html lang="es"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="color-scheme" content="dark">'
            f'<title>{e(titulo)} — k0lmenIA</title><style>{CSS}</style></head>'
            f'<body><div class="wrap"><header>'
            f'<span class="brand"><span class="dot">🪖</span>'
            f'<span class="eyebrow">k0lmenIA · {e(eyebrow)}</span></span>'
            f'<h1>{e(titulo)}</h1>{meta_html}</header>{body}'
            f'<footer><span>Generado por k0lmenIA</span></footer></div>'
            f'<script>{JS}</script></body></html>\n')


def meta(items):
    """items: lista de (clave, valor); ignora valores vacíos."""
    parts = [f'<span class="chip"><span class="k">{e(k)}</span> {e(v)}</span>' for k, v in items if v]
    return f'<div class="meta">{"".join(parts)}</div>' if parts else ""


def section(titulo, body_html, sub=""):
    s = f'<span class="sub">{e(sub)}</span>' if sub else ""
    return (f'<div class="section"><div class="card"><div class="section-title"><h2>{e(titulo)}</h2>{s}</div>'
            f'{body_html}</div></div>')


def section_group(titulo, body_html, sub=""):
    s = f'<span class="sub">{e(sub)}</span>' if sub else ""
    return f'<div class="section"><div class="grupo-titulo"><h2>{e(titulo)}</h2>{s}</div>{body_html}</div>'


ICONO_TONO = {"ok": "✓", "bad": "✕", "warn": "!", "blk": "⊘"}

# Ícono de cada indicador según su etiqueta (la primera coincidencia gana).
ICONO_POR_ETIQUETA = [
    ("riesgo", "escudo"), ("informativ", "lupa"), ("aprobad", "ok"), ("fallid", "bad"), ("bloquead", "blk"),
    ("errores js", "codigo"), ("% de error", "warn"), ("error", "warn"), ("recurso", "codigo"), ("link", "link"),
    ("imagen", "imagen"), ("responsive", "pantalla"), ("teclado", "teclado"), ("página", "pagina"),
    ("cumplimiento", "objetivo"), ("umbral", "objetivo"), ("objetivo", "objetivo"), ("criterio", "lista"),
    ("p95", "reloj"), ("latencia", "reloj"), ("carga promedio", "reloj"), ("duración", "reloj"),
    ("req/s", "rayo"), ("request", "carga"), ("usuario", "persona"), ("manual", "persona"),
    ("revisar", "lupa"), ("hallazgo", "lupa"), ("supuesto", "lupa"), ("pregunta", "lupa"), ("bug", "bicho"),
    ("caso", "lista"), ("corrida", "lista"), ("total", "lista"), ("tipos", "grid"), ("elemento", "grid"),
]


def _icono_de(label, tono):
    low = (label or "").lower()
    for clave, nombre in ICONO_POR_ETIQUETA:
        if clave in low:
            return nombre
    return tono if tono in ICONO_TONO else "grid"


def kpi_tiles(items):
    """items: (etiqueta, valor, tono[, detalle[, icono]]). tono: '' | 'ok' | 'bad' | 'blk' | 'warn'.
    icono: un nombre de ICONOS; si falta, se elige por la etiqueta. El tono colorea el ícono y además
    se muestra como símbolo (✓ ✕ ! ⊘) en la esquina: el estado nunca depende solo del color."""
    out = ""
    for it in items:
        label, val, tono = it[0], it[1], it[2]
        detalle = it[3] if len(it) > 3 else ""
        ic = it[4] if len(it) > 4 and it[4] else _icono_de(label, tono)
        st = f'<span class="st" title="{e(tono)}">{ICONO_TONO[tono]}</span>' if tono in ICONO_TONO else ""
        d = f'<div class="d">{e(detalle)}</div>' if detalle else ""
        out += (f'<div class="kpi {tono}"><div class="ic">{icono(ic)}</div>{st}'
                f'<div class="l">{e(label)}</div><div class="n">{e(val)}</div>{d}</div>')
    n = len(items)
    cols = n if n <= 6 else math.ceil(n / 2)  # 7 u 8 en dos filas parejas, nunca 6 + 2
    return f'<div class="kpis" style="--cols:{cols}">{out}</div>'


def legend(items):
    """items: (nombre, color[, valor])."""
    parts = []
    for it in items:
        valor = f' <b>{e(it[2])}</b>' if len(it) > 2 else ""
        parts.append(f'<span><i style="background:{it[1]}"></i>{e(it[0])}{valor}</span>')
    return f'<div class="legend">{"".join(parts)}</div>'


def banner(texto, tono="ok"):
    return f'<div class="banner {tono}"><span class="bic">{ICONO_TONO.get(tono, "i")}</span>{e(texto)}</div>'


def doc_list(items):
    if not items:
        return '<div class="cardbody"><p class="muted">—</p></div>'
    lis = "".join(f'<li>{e(it)}</li>' for it in items)
    return f'<div class="cardbody"><ul class="doclist">{lis}</ul></div>'


def two_col(izq, der):
    return f'<div class="twocol">{izq}{der}</div>'


def table(headers, rows):
    """headers: lista de strings. rows: lista de listas; cada celda puede traer HTML."""
    th = "".join(f'<th>{e(h)}</th>' for h in headers)
    trs = "".join("<tr>" + "".join(f'<td>{c}</td>' for c in row) + "</tr>" for row in rows)
    return f'<div class="tablecard"><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'


def _pastilla(texto, color, icono_txt):
    return (f'<span class="pill" style="background:{_soft(color, .14)};color:var(--ink);box-shadow:inset 0 0 0 1px {_soft(color, .38)}">'
            f'<span style="color:{color}">{icono_txt}</span>{e(texto)}</span>')


def nivel_badge(nivel):
    n = (nivel or "").strip()
    return _pastilla(n or "—", NIVEL_COLOR.get(n, NEUTRO), NIVEL_ICONO.get(n, "●"))


def estado_pill(estado):
    s = (estado or "").strip()
    return _pastilla(s or "—", ESTADO_COLOR.get(s, NEUTRO), ESTADO_ICONO.get(s, "●"))


# ------------------------------------------------------------------ gráficos
def _num(v, fmt=None):
    if v is None:
        return "—"
    if fmt:
        return fmt(v)
    if float(v).is_integer():
        return f"{v:,.0f}".replace(",", ".")
    return f"{v:,.2f}".rstrip("0").replace(",", "X").replace(".", ",").replace("X", ".")


def _escala(maxv):
    """Máximo "redondo" y paso para 4-5 líneas de grilla."""
    if maxv <= 0:
        return 1, 0.25
    exp = 10 ** math.floor(math.log10(maxv))
    for m in (1, 2, 2.5, 5, 10):
        paso = m * exp / 4
        if paso * 4 >= maxv:
            return paso * 4, paso
    return maxv, maxv / 4


def _barra_vertical(x, y_base, ancho, alto, color, tip):
    """Columna con el extremo de datos redondeado (4px) y la base recta."""
    r = min(4, ancho / 2, alto)
    if alto <= 0:
        return ""
    y = y_base - alto
    d = (f"M{x:.1f},{y_base:.1f} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} "
         f"H{x + ancho - r:.1f} Q{x + ancho:.1f},{y:.1f} {x + ancho:.1f},{y + r:.1f} V{y_base:.1f} Z")
    return f'<path class="mark" d="{d}" fill="{color}" data-tip="{e(tip)}" tabindex="0"/>'


def _grilla_y(W, izq, der, y_de, maxv, paso, fmt):
    out, i = [], 0
    while i * paso <= maxv + 1e-9:
        y = y_de(i * paso)
        out.append(f'<line class="{"base" if i == 0 else "grid"}" x1="{izq}" x2="{W - der}" y1="{y:.1f}" y2="{y:.1f}"/>'
                   f'<text class="axis" x="{izq - 10}" y="{y + 4:.1f}" text-anchor="end">{e(_num(i * paso, fmt))}</text>')
        i += 1
    return out


def donut(segments, pct, label="aprobados"):
    """segments: [(valor, color[, nombre])]. El centro muestra pct + label."""
    r, cx, cy, w = 74, 100, 100, 20
    C = 2 * math.pi * r
    total = sum(s[0] for s in segments) or 1
    track = f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#20252D" stroke-width="{w}"/>'
    segs, acc = "", 0.0
    gap = 3 if sum(1 for s in segments if s[0]) > 1 else 0
    for s in segments:
        valor, color = s[0], s[1]
        if not valor:
            continue
        nombre = s[2] if len(s) > 2 else ""
        frac = valor / total
        dash = max(frac * C - gap, 0.1)
        tip = f"{nombre}: {valor} ({frac * 100:.0f} %)" if nombre else f"{valor} ({frac * 100:.0f} %)"
        segs += (f'<circle class="mark" cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="{w}" '
                 f'stroke-dasharray="{dash:.2f} {C - dash:.2f}" stroke-dashoffset="{-acc * C:.2f}" '
                 f'transform="rotate(-90 {cx} {cy})" data-tip="{e(tip)}" tabindex="0"/>')
        acc += frac
    return (f'<svg viewBox="0 0 200 200" width="200" height="200" role="img" '
            f'aria-label="{pct} por ciento {e(label)}">{track}{segs}'
            f'<text x="{cx}" y="{cy + 6}" text-anchor="middle" class="donut-num">{pct}%</text>'
            f'<text x="{cx}" y="{cy + 28}" text-anchor="middle" class="donut-lbl">{e(label)}</text></svg>')


def donut_panel(segments, pct, label):
    """Dona + leyenda en filas (nombre, valor y %), para usar como cuerpo de section()."""
    total = sum(s[0] for s in segments) or 1
    filas = "".join(f'<div class="r"><i style="background:{s[1]}"></i><span>{e(s[2] if len(s) > 2 else "")}</span>'
                    f'<b>{e(_num(s[0]))}</b><em>{s[0] / total * 100:.0f} %</em></div>' for s in segments)
    return f'<div class="panorama"><div class="gauge">{donut(segments, pct, label)}</div><div class="dleg">{filas}</div></div>'


def bar_chart(rows, ancho_etiqueta=120):
    """rows: [(etiqueta, valor, color)]. Barras horizontales normalizadas al máximo, sobre un riel
    tenue; valor al final. ancho_etiqueta: ancho de la columna de etiquetas en px."""
    rows = list(rows)
    maxv = max((c for _, c, _ in rows), default=0)
    if not rows or maxv == 0:
        return '<div class="cardbody"><p class="muted">Sin datos.</p></div>'
    out = ""
    for label, count, color in rows:
        ancho = count / maxv * 100
        seg = f'<span class="seg" style="width:100%;background:{color}"></span>' if count else ""
        out += (f'<div class="bar-row" data-tip="{e(label)}: {e(_num(count))}" tabindex="0"><div class="bar-label"><span>{e(label)}</span></div>'
                f'<div class="bar-wrap"><div class="bar-track" style="width:{max(ancho, 0.8 if count else 0):.1f}%">{seg}</div></div>'
                f'<div class="bar-count">{e(_num(count))}</div></div>')
    return f'<div class="bars" style="--lw:{ancho_etiqueta}px">{out}</div>'


def column_chart(rows, fmt=None, alto=280, ancho=1320):
    """rows: [(etiqueta, valor[, color])]. Columnas verticales de una serie (verde azulado por
    defecto), con el valor sobre la punta. Para pocas categorías (hasta ~12)."""
    rows = [r for r in rows if r[1] is not None]
    if not rows or max(r[1] for r in rows) <= 0:
        return '<div class="cardbody"><p class="muted">Sin datos.</p></div>'
    W, H, izq, der, arriba, abajo = ancho, alto, 52, 10, 26, 40
    maxv, paso = _escala(max(r[1] for r in rows))
    ph = H - arriba - abajo
    y0 = arriba + ph
    svg = _grilla_y(W, izq, der, lambda v: y0 - ph * v / maxv, maxv, paso, fmt)
    banda = (W - izq - der) / len(rows)
    col = min(24 if len(rows) > 6 else 40, banda * 0.6)
    for k, r in enumerate(rows):
        etiqueta, v = r[0], r[1]
        color = r[2] if len(r) > 2 and r[2] else SERIES[0]
        x = izq + k * banda + (banda - col) / 2
        h = ph * v / maxv
        svg.append(_barra_vertical(x, y0, col, h, color, f"{etiqueta}: {_num(v, fmt)}"))
        svg.append(f'<text class="val" x="{x + col / 2:.1f}" y="{y0 - h - 8:.1f}" text-anchor="middle">{e(_num(v, fmt))}</text>')
        corto = etiqueta if len(etiqueta) * 6.4 <= banda else etiqueta[:max(int(banda / 6.4) - 1, 3)] + "…"
        svg.append(f'<text class="lbl" x="{izq + k * banda + banda / 2:.1f}" y="{H - 14}" text-anchor="middle">{e(corto)}<title>{e(etiqueta)}</title></text>')
    return f'<div class="chart"><svg viewBox="0 0 {W} {H}" role="img">{"".join(svg)}</svg></div>'


def stacked_bars(filas, series):
    """filas: [(etiqueta, [valor por serie])]; series: [(nombre, color)]. Barras horizontales
    apiladas, con 2px de separación entre segmentos y largo proporcional al total."""
    filas = [f for f in filas if sum(f[1])]
    if not filas:
        return '<div class="cardbody"><p class="muted">Sin datos.</p></div>'
    maxt = max(sum(v) for _, v in filas)
    out = ""
    for etiqueta, valores in filas:
        tot = sum(valores)
        segs = "".join(f'<span class="seg" style="width:{v / tot * 100:.2f}%;background:{c}" '
                       f'data-tip="{e(etiqueta)} · {e(n)}: {v} ({v / tot * 100:.0f} %)"></span>'
                       for v, (n, c) in zip(valores, series) if v)
        out += (f'<div class="bar-row"><div class="bar-label"><span>{e(etiqueta)}</span></div>'
                f'<div class="bar-wrap"><div class="bar-track" style="width:{tot / maxt * 100:.1f}%">{segs}</div></div>'
                f'<div class="bar-count">{tot}</div></div>')
    return f'<div class="bars">{out}{legend(series) if len(series) > 1 else ""}</div>'


def grouped_columns(grupos, series, fmt=None, alto=300, ancho=1320):
    """grupos: etiquetas del eje X; series: [(nombre, color, [valor por grupo])]. Un solo eje Y.
    ancho: lienzo en px (1320 a todo el ancho; 660 en una grilla de dos columnas, así el texto no cambia de tamaño)."""
    valores = [v for _, _, vs in series for v in vs if v is not None]
    if not valores:
        return '<div class="cardbody"><p class="muted">Sin datos.</p></div>'
    W, H, izq, der, arriba, abajo = ancho, alto, 58, 8, 22, 40
    maxv, paso = _escala(max(valores))
    ph = H - arriba - abajo
    y0 = arriba + ph
    svg = _grilla_y(W, izq, der, lambda v: y0 - ph * v / maxv, maxv, paso, fmt)
    ancho_grupo = (W - izq - der) / len(grupos)
    col = min(24, (ancho_grupo * 0.7 - 2 * (len(series) - 1)) / len(series))
    for g, nombre in enumerate(grupos):
        x0 = izq + g * ancho_grupo + (ancho_grupo - (col * len(series) + 2 * (len(series) - 1))) / 2
        for s, (sn, color, vs) in enumerate(series):
            v = vs[g]
            if v is None:
                continue
            svg.append(_barra_vertical(x0 + s * (col + 2), y0, col, ph * v / maxv, color, f"{nombre} · {sn}: {_num(v, fmt)}"))
        corto = nombre if len(nombre) * 6.6 <= ancho_grupo else nombre[:max(int(ancho_grupo / 6.6) - 1, 3)] + "…"
        svg.append(f'<text class="lbl" x="{izq + g * ancho_grupo + ancho_grupo / 2:.1f}" y="{H - 14}" text-anchor="middle">'
                   f'{e(corto)}<title>{e(nombre)}</title></text>')
    if len(series) == 1:  # una sola serie: el valor sobre cada columna (son pocas)
        for g, v in enumerate(series[0][2]):
            if v is not None and len(grupos) <= 12:
                x = izq + g * ancho_grupo + ancho_grupo / 2
                svg.append(f'<text class="val" x="{x:.1f}" y="{y0 - ph * v / maxv - 8:.1f}" text-anchor="middle">{e(_num(v, fmt))}</text>')
    ley = legend([(n, c) for n, c, _ in series]) if len(series) > 1 else ""
    return f'<div class="chart"><svg viewBox="0 0 {W} {H}" role="img">{"".join(svg)}</svg>{ley}</div>'


def _curva(pts):
    """Curva suave monótona (Fritsch–Carlson) por los puntos: no se pasa de los valores reales."""
    n = len(pts)
    if n < 3:
        return " ".join(f'{"M" if k == 0 else "L"}{a:.1f},{b:.1f}' for k, (a, b) in enumerate(pts))
    dx = [pts[i + 1][0] - pts[i][0] for i in range(n - 1)]
    dy = [pts[i + 1][1] - pts[i][1] for i in range(n - 1)]
    m = [dy[i] / dx[i] if dx[i] else 0 for i in range(n - 1)]
    t = [m[0]] + [0 if m[i - 1] * m[i] <= 0 else (m[i - 1] + m[i]) / 2 for i in range(1, n - 1)] + [m[-1]]
    for i in range(n - 1):
        if m[i] == 0:
            t[i] = t[i + 1] = 0
        else:
            a, b = t[i] / m[i], t[i + 1] / m[i]
            s = a * a + b * b
            if s > 9:
                k = 3 / math.sqrt(s)
                t[i], t[i + 1] = k * a * m[i], k * b * m[i]
    d = [f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"]
    for i in range(n - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        h = (x1 - x0) / 3
        d.append(f"C{x0 + h:.1f},{y0 + t[i] * h:.1f} {x1 - h:.1f},{y1 - t[i + 1] * h:.1f} {x1:.1f},{y1:.1f}")
    return " ".join(d)


_GRAD = [0]


def line_chart(x, series, fmt=None, fmt_x=None, alto=300, area=None, ancho=1320):
    """x: valores del eje X (números); series: [(nombre, color, [valor por x])]. Un solo eje Y,
    curvas suaves de 2px, área con degradado (por defecto, si hay una sola serie), puntos y
    etiquetas en el máximo y el último valor, y crosshair con el valor de todas las series."""
    if len(x) < 2 or not any(v is not None for _, _, vs in series for v in vs):
        return '<p class="muted" style="padding:16px 24px">Sin datos suficientes para la evolución.</p>'
    if area is None:
        area = len(series) == 1
    W, H, izq, der, arriba, abajo = ancho, alto, 58, 18, 24, 30
    valores = [v for _, _, vs in series for v in vs if v is not None]
    maxv, paso = _escala(max(valores))
    ph, pw = H - arriba - abajo, W - izq - der
    x0, x1 = x[0], x[-1]
    rx = (x1 - x0) or 1
    px = lambda xv: izq + (xv - x0) / rx * pw
    py = lambda v: arriba + ph - ph * v / maxv
    svg = _grilla_y(W, izq, der, py, maxv, paso, fmt)
    for xv in (x0, x0 + rx / 4, x0 + rx / 2, x0 + 3 * rx / 4, x1):
        svg.append(f'<text class="axis" x="{px(xv):.1f}" y="{H - 8}" text-anchor="middle">{e(fmt_x(xv) if fmt_x else _num(xv))}</text>')
    defs = []
    for nombre, color, vs in series:
        pts = [(px(xv), py(v)) for xv, v in zip(x, vs) if v is not None]
        if not pts:
            continue
        d = _curva(pts)
        if area:
            _GRAD[0] += 1
            gid = f"g{_GRAD[0]}"
            defs.append(f'<linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
                        f'<stop offset="0" stop-color="{color}" stop-opacity=".32"/><stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient>')
            svg.append(f'<path d="{d} L{pts[-1][0]:.1f},{py(0):.1f} L{pts[0][0]:.1f},{py(0):.1f} Z" fill="url(#{gid})"/>')
        svg.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
        # puntos (si no son demasiados) y etiquetas solo en el máximo y el último valor
        if len(pts) <= 40:
            svg += [f'<circle cx="{a:.1f}" cy="{b:.1f}" r="3.5" fill="{color}" stroke="{SUPERFICIE}" stroke-width="2"/>' for a, b in pts]
        reales = [(xv, v) for xv, v in zip(x, vs) if v is not None]
        imax = max(range(len(reales)), key=lambda k: reales[k][1])
        for k in sorted({imax, len(reales) - 1} if len(series) == 1 else {len(reales) - 1}):
            xv, v = reales[k]
            svg.append(f'<text class="val" x="{px(xv):.1f}" y="{py(v) - 10:.1f}" text-anchor="middle">{e(_num(v, fmt))}</text>')
    # zonas de hover: una por punto del eje X, con crosshair y el valor de todas las series
    for k, xv in enumerate(x):
        izqz = px(x[k - 1]) if k else px(xv)
        derz = px(x[k + 1]) if k < len(x) - 1 else px(xv)
        a, b = (izqz + px(xv)) / 2, (px(xv) + derz) / 2
        tip = (fmt_x(xv) if fmt_x else _num(xv)) + "\n" + "\n".join(
            f"{n}: {_num(vs[k], fmt)}" for n, _, vs in series if vs[k] is not None)
        puntos = "".join(f'<circle cx="{px(xv):.1f}" cy="{py(vs[k]):.1f}" r="5.5" fill="{c}" stroke="{SUPERFICIE}" stroke-width="2"/>'
                         for _, c, vs in series if vs[k] is not None)
        svg.append(f'<g class="hit" data-tip="{e(tip)}"><rect x="{a:.1f}" y="{arriba}" width="{max(b - a, 1):.1f}" height="{ph}"/>'
                   f'<line class="cross" x1="{px(xv):.1f}" x2="{px(xv):.1f}" y1="{arriba}" y2="{arriba + ph}"/>{puntos}</g>')
    ley = legend([(n, c) for n, c, _ in series]) if len(series) > 1 else ""
    return f'<svg viewBox="0 0 {W} {H}" role="img"><defs>{"".join(defs)}</defs>{"".join(svg)}</svg>{ley}'
