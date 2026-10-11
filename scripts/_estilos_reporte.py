#!/usr/bin/env python3
"""
Sistema de diseño de los reportes HTML de k0lmenIA (dashboard bento, modo oscuro).

Lo usan todos los generadores de entregables HTML (plan de pruebas, reporte de ejecución, informe
de cierre, performance, seguridad, exploratorias, accesibilidad, rendimiento web, fallos y
cobertura), así todos se ven igual y el tema vive en un solo lugar.

Estructura de la página: barra lateral con la marca y el índice del reporte (se arma solo con las
secciones y marca la que se está leyendo), encabezado con buscador y una grilla bento de 12
columnas. Las tablas largas suman solas un buscador, filtros por la columna de estado o severidad
y orden al hacer clic en el encabezado.

Página y estructura
  page(titulo, eyebrow, meta_html, body)    documento completo (barra lateral, encabezado, pie)
  meta(items)                               chips de contexto (Historia, Fecha, …)
  section(titulo, body_html, sub="", ancho=12)   tarjeta de la grilla (12 = todo el ancho, 6 = mitad, 4 = tercio)
  section_group(titulo, body_html, sub="")  título de un grupo de tarjetas (va afuera)
  two_col(izq, der)                         dos secciones lado a lado (cada una ocupa la mitad)
  banner(texto, tono)                       veredicto destacado (ok | warn | bad)
  kpi_tiles(items)                          indicadores (etiqueta, valor, tono[, detalle[, icono[, extra]]])
                                            extra: {"pct": 0-100} barra de progreso · {"serie": [números]} sparkline
  table(headers, rows)                      tabla (las celdas pueden traer HTML)
  doc_list(items)                           lista con viñetas
  nivel_badge(nivel) / estado_pill(estado)  pastillas con ícono + texto (nunca solo color)
  legend(items)                             leyenda (nombre, color[, valor])

Gráficos (SVG inline, con tooltip al pasar el mouse o con foco)
  donut(segments, pct, label)               dona: segments = [(valor, color[, nombre])]
  donut_panel(segments, pct, label)         dona + leyenda con valor, % y barra de proporción
  gauge(pct, label, tono)                   medidor semicircular (puntajes 0-100)
  sparkline(valores, color)                 mini línea para un indicador
  bar_chart(rows)                           barras horizontales: [(etiqueta, valor, color)]
  column_chart(rows, fmt)                   columnas: [(etiqueta, valor[, color])], valor en la punta
  stacked_bars(filas, series)               barras apiladas: filas = [(etiqueta, [v1, v2…])]
  grouped_columns(grupos, series, fmt)      columnas agrupadas, un solo eje
  line_chart(x, series, fmt, area)          líneas suaves sobre un eje, con área y crosshair

Colores (skill dataviz, validados con su script contra la superficie oscura):
  categórica  #14A895 #E0702E #4C8DEB #C98500 #D55181 #9085E9 #E66767 #008300
              (orden fijo, nunca ciclado; las tres primeras pasan también todos los pares)
  estado      ok #0CA30C · aviso #FAB219 · serio #EC835A · crítico #D03B3B (siempre con ícono y texto)
Tipografía: Geist y Geist Mono (scripts/fuentes, licencia OFL), incrustadas en base64.
Sin dependencias externas: CSS, fuentes, SVG y JS van inline, no usa internet.
"""
import base64
import html
import math
import os
import re
from pathlib import Path

# ------------------------------------------------------------------ tokens
FONDO = "#08090C"
SUPERFICIE = "#111318"
# Categórica (orden fijo, nunca ciclado): verde azulado, naranja, azul, amarillo, magenta, violeta, rojo, verde
SERIES = ["#14A895", "#E0702E", "#4C8DEB", "#C98500", "#D55181", "#9085E9", "#E66767", "#008300"]
# Estado (reservados: nunca se usan como "serie 4")
OK, AVISO, SERIO, CRITICO, NEUTRO = "#0CA30C", "#FAB219", "#EC835A", "#D03B3B", "#8B949E"
ACENTO = SERIES[0]

PALETA = {"bg": FONDO, "surface": SUPERFICIE, "tile": "#181B22", "border": "#22262E",
          "ink": "#EDEFF3", "body": "#A9B0BC", "muted": "#6F7787",
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


def _aclarar(hexcolor, f=0.35):
    """El color mezclado con blanco (para el extremo claro de un degradado)."""
    h = hexcolor.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02X%02X%02X" % tuple(round(c + (255 - c) * f) for c in (r, g, b))


# Íconos de línea (24x24, trazo 1.8) para los indicadores y la navegación.
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


def _fuentes():
    """@font-face de Geist y Geist Mono incrustadas (si los archivos están)."""
    carpeta = Path(__file__).resolve().parent / "fuentes"
    css = ""
    for familia, archivo in (("Geist", "geist-latin-wght-normal.woff2"), ("Geist Mono", "geist-mono-latin-wght-normal.woff2")):
        f = carpeta / archivo
        if f.exists():
            datos = base64.b64encode(f.read_bytes()).decode()
            css += (f"@font-face{{font-family:'{familia}';font-style:normal;font-weight:100 900;font-display:swap;"
                    f"src:url(data:font/woff2;base64,{datos}) format('woff2')}}")
    return css


FUENTES = _fuentes()

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{
  color-scheme:dark;
  --bg:#08090C; --surface:#111318; --surface-2:#14171D; --tile:#181B22; --raised:#1E222A;
  --border:#22262E; --border-soft:#1A1D24; --line:rgba(255,255,255,.07); --line-2:rgba(255,255,255,.12);
  --ink:#EDEFF3; --body:#A9B0BC; --muted:#6F7787; --accent:#14A895; --accent-2:#4C8DEB; --accent-soft:rgba(20,168,149,.13);
  --ok:#0CA30C; --warn:#FAB219; --serious:#EC835A; --bad:#D03B3B; --neutral:#8B949E;
  --radius:20px; --gap:18px; --side:248px;
  --sans:"Geist","Inter","Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,Roboto,sans-serif;
  --mono:"Geist Mono","JetBrains Mono","Cascadia Code",ui-monospace,Consolas,monospace;
}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth;scroll-padding-top:24px}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:14px;line-height:1.55;
  -webkit-font-smoothing:antialiased;font-feature-settings:"ss01" 1,"cv11" 1}
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;
  background:radial-gradient(900px 480px at 18% -12%,rgba(20,168,149,.13),transparent 62%),
             radial-gradient(700px 420px at 100% 0%,rgba(76,141,235,.08),transparent 60%),
             radial-gradient(rgba(255,255,255,.035) 1px,transparent 1px) 0 0/22px 22px}
.mono{font-family:var(--mono);font-size:.9em}
.muted{color:var(--muted)}
a{color:#4FD8C3;text-decoration-color:rgba(79,216,195,.35);text-underline-offset:3px}

/* layout: barra lateral + contenido */
.app{position:relative;z-index:1;display:grid;grid-template-columns:var(--side) minmax(0,1fr);min-height:100vh}
.side{position:sticky;top:0;height:100vh;display:flex;flex-direction:column;gap:18px;padding:22px 16px;
  border-right:1px solid var(--line);background:linear-gradient(180deg,rgba(17,19,24,.92),rgba(10,11,14,.92));backdrop-filter:blur(12px)}
.logo{display:flex;align-items:center;gap:11px;padding:4px 8px 14px;border-bottom:1px solid var(--line)}
.logo .mk{width:34px;height:34px;border-radius:10px;display:grid;place-items:center;font-size:17px;flex:none;
  background:linear-gradient(135deg,#14A895,#4C8DEB);box-shadow:0 6px 18px -6px rgba(20,168,149,.6),inset 0 1px 0 rgba(255,255,255,.25)}
.logo b{display:block;font-size:14.5px;font-weight:650;letter-spacing:-.01em;color:var(--ink)}
.logo span{display:block;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.12em;font-weight:600}
.nav{flex:1;overflow:auto;display:flex;flex-direction:column;gap:2px;margin:0 -4px;padding:0 4px}
.nav .t{font-size:10.5px;text-transform:uppercase;letter-spacing:.14em;color:var(--muted);font-weight:650;padding:4px 10px 8px}
.nav a{display:flex;align-items:center;gap:10px;padding:7px 10px;border-radius:9px;color:var(--body);text-decoration:none;
  font-size:13px;line-height:1.3;transition:background .15s,color .15s}
.nav a i{width:6px;height:6px;border-radius:50%;background:var(--border);flex:none;transition:background .15s,box-shadow .15s}
.nav a:hover{background:rgba(255,255,255,.04);color:var(--ink)}
.nav a.on{background:var(--accent-soft);color:var(--ink)}
.nav a.on i{background:var(--accent);box-shadow:0 0 0 3px rgba(20,168,149,.22)}
.side-foot{font-size:11.5px;color:var(--muted);padding:12px 8px 0;border-top:1px solid var(--line)}
.main{min-width:0;padding:26px 34px 56px}
.wrap{max-width:1520px;margin:0 auto}

/* encabezado */
.top{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;flex-wrap:wrap;margin-bottom:22px}
.eyebrow{display:inline-flex;align-items:center;gap:8px;font-size:11px;text-transform:uppercase;letter-spacing:.16em;font-weight:650;color:var(--accent)}
.eyebrow::before{content:"";width:18px;height:2px;border-radius:2px;background:linear-gradient(90deg,#14A895,#4C8DEB)}
h1{font-size:36px;font-weight:680;letter-spacing:-.035em;line-height:1.08;color:var(--ink);margin:10px 0 14px}
.meta{display:flex;flex-wrap:wrap;gap:8px}
.chip{display:inline-flex;align-items:center;gap:7px;font-size:12.5px;color:var(--ink);
  background:rgba(255,255,255,.03);border:1px solid var(--line);border-radius:999px;padding:5px 12px}
.chip .k{color:var(--muted);font-size:10.5px;text-transform:uppercase;letter-spacing:.11em;font-weight:650}
.chip a{color:var(--ink);text-decoration:none;border-bottom:1px dashed var(--border)}
.buscar{display:flex;align-items:center;gap:9px;min-width:260px;padding:9px 14px;border-radius:12px;
  background:rgba(255,255,255,.03);border:1px solid var(--line);color:var(--muted)}
.buscar input{all:unset;flex:1;color:var(--ink);font-size:13px}
.buscar kbd{font-family:var(--mono);font-size:10.5px;border:1px solid var(--line-2);border-radius:5px;padding:1px 5px;color:var(--muted)}

/* grilla bento */
.grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:var(--gap)}
.grid>*{grid-column:span 12;min-width:0}
.twocol{display:contents}
.twocol>*{grid-column:span 6;min-width:0}
.grid>div[style*="margin-top"]{margin-top:0!important}
.subgrid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:var(--gap)}
.subgrid>*{grid-column:span 12;min-width:0}

/* tarjetas */
.card,.section>.card{position:relative;border-radius:var(--radius);overflow:hidden;
  background:linear-gradient(180deg,var(--surface-2),var(--surface)) padding-box,
             linear-gradient(180deg,rgba(255,255,255,.11),rgba(255,255,255,.03) 45%,rgba(255,255,255,.05)) border-box;
  border:1px solid transparent;box-shadow:0 1px 0 rgba(255,255,255,.03) inset,0 24px 48px -32px rgba(0,0,0,.9)}
.section{min-width:0;scroll-margin-top:20px}
.section>.card{height:100%}
.section-title{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:18px 22px 6px}
.section-title h2{font-size:15px;font-weight:620;letter-spacing:-.01em;color:var(--ink)}
.section-title h2::before{content:"";display:inline-block;width:7px;height:7px;border-radius:2px;margin:0 10px 2px 0;
  background:linear-gradient(135deg,#14A895,#4C8DEB);vertical-align:middle}
.section-title .sub{font-size:12px;color:var(--muted)}
.grupo-titulo{display:flex;align-items:baseline;gap:12px;margin:0 4px 12px}
.grupo-titulo h2{font-size:15px;font-weight:620;color:var(--ink)}
.grupo-titulo .sub{font-size:12px;color:var(--muted)}
.cardbody{padding:12px 22px 22px;color:var(--body)}
.cardbody p{color:var(--body)}
.cardbody p+p{margin-top:10px}
.lead{font-size:15.5px;color:var(--ink);line-height:1.65}
.subhead{font-size:10.5px;text-transform:uppercase;letter-spacing:.13em;color:var(--muted);font-weight:650;margin-bottom:10px}
.subhead.ok{color:#5BD25B}.subhead.bad{color:#F07272}.subhead.warn{color:#F5C451}

/* hero: dona + indicadores */
.hero{display:grid;grid-template-columns:260px 1fr;gap:26px;align-items:center;padding:24px 26px}
.gauge{display:flex;flex-direction:column;align-items:center;gap:14px}
.donut-num{font-size:34px;font-weight:680;fill:var(--ink);letter-spacing:-.03em}
.donut-lbl{font-size:9.5px;letter-spacing:.18em;text-transform:uppercase;fill:var(--muted);font-weight:650}
.hero .kpi{background:var(--tile)}
.hero .legend{flex-direction:column;gap:8px;align-self:stretch}

/* dona con leyenda de valores */
.panorama{display:grid;grid-template-columns:200px 1fr;gap:26px;align-items:center;padding:8px 24px 22px}
.dleg{display:flex;flex-direction:column;gap:2px}
.dleg .r{display:grid;grid-template-columns:12px minmax(0,1fr) auto 46px;gap:4px 12px;align-items:center;padding:9px 0;
  border-bottom:1px solid var(--line);font-size:13px;color:var(--body)}
.dleg .r:last-child{border-bottom:0}
.dleg i{width:10px;height:10px;border-radius:3px}
.dleg b{color:var(--ink);font-weight:620;font-variant-numeric:tabular-nums}
.dleg em{font-style:normal;color:var(--muted);text-align:right;font-variant-numeric:tabular-nums}
.dleg .p{grid-column:2/5;height:4px;border-radius:999px;background:rgba(255,255,255,.05);overflow:hidden}
.dleg .p span{display:block;height:100%;border-radius:999px}

/* leyenda */
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12.5px;color:var(--body)}
.legend span{display:inline-flex;align-items:center;gap:8px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;flex:none}
.legend b{color:var(--ink);font-weight:620;font-variant-numeric:tabular-nums;margin-left:auto;padding-left:10px}

/* indicadores */
.kpis{display:grid;grid-template-columns:repeat(var(--cols,4),minmax(0,1fr));gap:var(--gap)}
.kpi{position:relative;padding:18px 20px 18px;border-radius:18px;display:flex;flex-direction:column;min-height:148px;overflow:hidden;
  background:linear-gradient(180deg,var(--surface-2),var(--surface)) padding-box,
             linear-gradient(180deg,rgba(255,255,255,.11),rgba(255,255,255,.03)) border-box;border:1px solid transparent;
  transition:transform .2s,box-shadow .2s}
.kpi::after{content:"";position:absolute;width:180px;height:180px;right:-70px;top:-90px;border-radius:50%;pointer-events:none;
  background:radial-gradient(circle,var(--glow,rgba(20,168,149,.16)),transparent 70%)}
.kpi:hover{transform:translateY(-2px);box-shadow:0 18px 40px -26px rgba(0,0,0,.9)}
.kpi.ok{--glow:rgba(12,163,12,.16)} .kpi.bad{--glow:rgba(208,59,59,.2)} .kpi.warn{--glow:rgba(250,178,25,.13)} .kpi.blk{--glow:rgba(139,148,158,.12)}
.kpi .ic{width:38px;height:38px;border-radius:11px;display:grid;place-items:center;color:var(--accent);background:var(--accent-soft);
  box-shadow:inset 0 0 0 1px rgba(20,168,149,.18)}
.kpi.ok .ic{color:#3FCB3F;background:rgba(12,163,12,.13);box-shadow:inset 0 0 0 1px rgba(12,163,12,.25)}
.kpi.bad .ic{color:#EE6A6A;background:rgba(208,59,59,.15);box-shadow:inset 0 0 0 1px rgba(208,59,59,.28)}
.kpi.warn .ic{color:#FAB219;background:rgba(250,178,25,.12);box-shadow:inset 0 0 0 1px rgba(250,178,25,.25)}
.kpi.blk .ic{color:#A9B1BC;background:rgba(139,148,158,.12);box-shadow:inset 0 0 0 1px rgba(139,148,158,.22)}
.kpi .st{position:absolute;top:18px;right:18px;display:inline-flex;align-items:center;gap:5px;font-size:10.5px;font-weight:650;
  text-transform:uppercase;letter-spacing:.08em;padding:3px 8px 3px 6px;border-radius:999px}
.kpi.ok .st{color:#5BD25B;background:rgba(12,163,12,.12)} .kpi.bad .st{color:#F07272;background:rgba(208,59,59,.14)}
.kpi.warn .st{color:#F5C451;background:rgba(250,178,25,.12)} .kpi.blk .st{color:#A9B1BC;background:rgba(139,148,158,.12)}
.kpi .l{font-size:11.5px;font-weight:550;color:var(--muted);margin-top:auto;padding-top:16px}
.kpi .n{font-size:32px;font-weight:650;letter-spacing:-.035em;line-height:1.08;color:var(--ink);margin-top:4px}
.kpi .d{font-size:12px;color:var(--body);margin-top:5px}
.kpi .spark{margin-top:10px;height:30px}
.kpi .spark svg{width:100%;height:30px;display:block;overflow:visible}
.kpi .bar{margin-top:12px;height:5px;border-radius:999px;background:rgba(255,255,255,.06);overflow:hidden}
.kpi .bar span{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,#14A895,#4C8DEB)}

/* gráficos */
.chart{padding:6px 22px 20px}
.chart svg{width:100%;height:auto;display:block;overflow:visible}
.chart .legend{margin-top:14px}
.axis{font-size:11px;fill:var(--muted);font-variant-numeric:tabular-nums;font-family:var(--sans)}
.lbl{font-size:12px;fill:var(--body);font-family:var(--sans)}
.val{font-size:12px;fill:var(--ink);font-weight:620;font-variant-numeric:tabular-nums;font-family:var(--sans)}
.grid-l{stroke:rgba(255,255,255,.05);stroke-width:1}
.base{stroke:rgba(255,255,255,.12);stroke-width:1}
.mark{transition:opacity .15s}
svg:hover .mark{opacity:.45} svg .mark:hover,svg .mark:focus{opacity:1;outline:none}
.hit rect{fill:transparent}
.hit .cross{stroke:rgba(255,255,255,.25);stroke-width:1;opacity:0}
.hit:hover .cross{opacity:1}
.hit circle{opacity:0}.hit:hover circle{opacity:1}

/* barras horizontales */
.bars{padding:10px 22px 22px;display:flex;flex-direction:column;gap:6px}
.bar-row{display:grid;grid-template-columns:var(--lw,120px) 1fr 58px;align-items:center;gap:14px;padding:6px 8px;margin:0 -8px;
  border-radius:10px;transition:background .15s}
.bar-row:hover{background:rgba(255,255,255,.03)}
.bar-label{font-size:13px;color:var(--body);display:flex;align-items:center;gap:8px;min-width:0}
.bar-label span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bar-wrap{background:rgba(255,255,255,.045);border-radius:999px;height:12px}
.bar-track{height:12px;border-radius:999px;display:flex;gap:2px;overflow:hidden}
.bar-track .seg{height:100%;display:block}
.bar-track .seg:last-child{border-radius:0 999px 999px 0}
.bar-track .seg:first-child{border-radius:999px 0 0 999px}
.bar-track .seg:only-child{border-radius:999px}
.bar-count{font-size:13px;color:var(--ink);text-align:right;font-weight:620;font-variant-numeric:tabular-nums}

/* tablas */
.tablecard{overflow-x:auto;padding:4px 0 2px}
.tabla-barra{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:6px 22px 12px}
.tabla-barra .bq{display:flex;align-items:center;gap:8px;padding:7px 12px;border-radius:10px;background:rgba(255,255,255,.03);
  border:1px solid var(--line);color:var(--muted);min-width:220px}
.tabla-barra .bq input{all:unset;flex:1;color:var(--ink);font-size:12.5px}
.tabla-barra .f{font:inherit;font-size:12px;font-weight:550;color:var(--body);background:rgba(255,255,255,.03);border:1px solid var(--line);
  border-radius:999px;padding:5px 11px;cursor:pointer;transition:all .15s}
.tabla-barra .f b{color:var(--muted);font-weight:600;margin-left:4px}
.tabla-barra .f:hover{color:var(--ink);border-color:var(--line-2)}
.tabla-barra .f.on{color:var(--ink);background:var(--accent-soft);border-color:rgba(20,168,149,.45)}
.tabla-barra .cnt{margin-left:auto;font-size:12px;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:13.5px;font-variant-numeric:tabular-nums}
thead th{text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted);
  font-weight:650;padding:11px 18px;white-space:nowrap;background:rgba(255,255,255,.025);
  border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
thead th.ord{cursor:pointer;user-select:none}
thead th.ord:hover{color:var(--ink)}
thead th.ord::after{content:"↕";margin-left:6px;opacity:.35;font-size:10px}
thead th.asc::after{content:"↑";opacity:1;color:var(--accent)} thead th.desc::after{content:"↓";opacity:1;color:var(--accent)}
tbody td{padding:13px 18px;border-bottom:1px solid var(--line);color:var(--body);vertical-align:top}
tbody tr:last-child td{border-bottom:0}
tbody tr{transition:background .12s}
tbody tr:hover td{background:rgba(255,255,255,.025)}
tbody tr.oculta{display:none}
td .id,.id{font-family:var(--mono);font-weight:600;color:var(--ink);white-space:nowrap;font-size:12.5px}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;padding:3px 10px;border-radius:999px;white-space:nowrap}

/* banner de veredicto */
.banner{position:relative;display:flex;align-items:center;gap:16px;padding:20px 24px;border-radius:var(--radius);
  font-weight:600;font-size:16px;letter-spacing:-.01em;color:var(--ink);overflow:hidden;border:1px solid transparent;
  background:linear-gradient(100deg,var(--tint),transparent 55%) padding-box,linear-gradient(180deg,var(--surface-2),var(--surface)) padding-box,
             linear-gradient(90deg,var(--edge),rgba(255,255,255,.05) 60%) border-box}
.banner .bic{width:40px;height:40px;border-radius:12px;display:grid;place-items:center;font-size:18px;font-weight:800;flex:none}
.banner.ok{--tint:rgba(12,163,12,.16);--edge:rgba(12,163,12,.55)} .banner.ok .bic{background:rgba(12,163,12,.18);color:#3FCB3F}
.banner.bad{--tint:rgba(208,59,59,.18);--edge:rgba(208,59,59,.6)} .banner.bad .bic{background:rgba(208,59,59,.2);color:#EE6A6A}
.banner.warn{--tint:rgba(250,178,25,.13);--edge:rgba(250,178,25,.5)} .banner.warn .bic{background:rgba(250,178,25,.16);color:#FAB219}

.doclist{list-style:none;display:flex;flex-direction:column;gap:10px}
.doclist li{position:relative;padding-left:22px;color:var(--body)}
.doclist li::before{content:"";position:absolute;left:4px;top:8px;width:8px;height:8px;border-radius:3px;background:linear-gradient(135deg,#14A895,#4C8DEB)}

/* evidencia: miniaturas y visor */
.thumb{position:relative;display:inline-flex;flex-direction:column;width:156px;height:104px;border:1px solid var(--line-2);border-radius:10px;overflow:hidden;
  background:#0B0D11;vertical-align:middle;cursor:zoom-in;box-shadow:0 8px 20px -12px rgba(0,0,0,.8);transition:border-color .15s,transform .15s,box-shadow .15s}
/* marco de navegador: una página blanca se lee como página, no como un hueco */
.thumb::before{content:"";flex:none;height:13px;border-bottom:1px solid rgba(255,255,255,.07);
  background:radial-gradient(circle at 8px 6.5px,#E66767 2.1px,transparent 2.6px),radial-gradient(circle at 16px 6.5px,#FAB219 2.1px,transparent 2.6px),
             radial-gradient(circle at 24px 6.5px,#0CA30C 2.1px,transparent 2.6px),#1A1D24}
.thumb img{flex:1;min-height:0;width:100%;object-fit:cover;object-position:top left;display:block}
.thumb.chico img{object-fit:scale-down;object-position:center;padding:6px;
  background:repeating-conic-gradient(#14171C 0 25%,#101216 0 50%) 0 0/14px 14px}
.thumb.s{width:112px;height:76px}
.thumb::after{content:"⤢";position:absolute;right:6px;bottom:6px;width:20px;height:20px;border-radius:6px;display:grid;place-items:center;
  font-size:12px;color:#fff;background:rgba(8,9,12,.75);opacity:0;transition:opacity .15s}
.thumb:hover{border-color:var(--accent);transform:translateY(-2px);box-shadow:0 14px 28px -14px rgba(20,168,149,.55)}
.thumb:hover::after{opacity:1}
.thumb.falta,.falta-ev{cursor:help;color:#F5C451;font-size:11px;font-weight:600;text-align:center;line-height:1.3;padding:6px;
  background:repeating-linear-gradient(135deg,rgba(250,178,25,.06) 0 8px,transparent 8px 16px),#0B0D11;border-color:rgba(250,178,25,.35)}
.falta-ev{display:inline-flex;align-items:center;border:1px solid rgba(250,178,25,.35);border-radius:10px;padding:6px 10px}
#lb{position:fixed;inset:0;z-index:99;display:none;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:28px;
  background:rgba(5,6,8,.9);backdrop-filter:blur(6px);cursor:zoom-out}
#lb.on{display:flex}
#lb img{max-width:100%;max-height:calc(100% - 50px);border-radius:12px;box-shadow:0 20px 60px rgba(0,0,0,.7);background:#fff}
#lb .pie{display:flex;gap:14px;align-items:center;font-size:12.5px;color:var(--body)}
#lb .pie a{color:var(--ink)}
#lb .msg{display:none;max-width:560px;text-align:center;color:#F5C451;font-size:14px;line-height:1.6;padding:22px 26px;border-radius:14px;
  background:#111318;border:1px solid rgba(250,178,25,.35)}
#lb.error img{display:none}#lb.error .msg{display:block}

/* tooltip */
#tip{position:fixed;z-index:50;pointer-events:none;opacity:0;transform:translateY(4px);transition:opacity .12s,transform .12s;
  background:rgba(14,16,21,.96);border:1px solid var(--line-2);border-radius:12px;padding:9px 12px;font-size:12.5px;color:var(--ink);
  box-shadow:0 18px 40px rgba(0,0,0,.65);max-width:320px;white-space:pre-line;font-variant-numeric:tabular-nums;backdrop-filter:blur(8px)}
#tip.on{opacity:1;transform:none}

footer{margin-top:40px;display:flex;justify-content:center;gap:8px;font-size:12px;color:var(--muted)}

@media (max-width:1100px){
  .app{grid-template-columns:minmax(0,1fr)}
  .side>*{min-width:0}
  .side{position:sticky;top:0;z-index:20;height:auto;flex-direction:row;align-items:center;gap:12px;padding:10px 14px;border-right:0;border-bottom:1px solid var(--line)}
  .logo{border:0;padding:0}.logo span{display:none}
  .nav{flex-direction:row;overflow-x:auto;gap:4px;scrollbar-width:none;min-width:0;flex:1 1 0}.nav .t{display:none}
  .nav a{white-space:nowrap;padding:6px 10px}
  .side-foot{display:none}
  .main{padding:20px 16px 40px}
  .twocol>*{grid-column:span 12}
}
@media (max-width:760px){
  .hero,.panorama{grid-template-columns:1fr;justify-items:center}
  .dleg{width:100%}
  .kpis{grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:12px}
  .kpi{min-height:128px;padding:16px}.kpi .n{font-size:25px}
  .bar-row{grid-template-columns:90px 1fr 44px}
  h1{font-size:27px}.buscar{min-width:0;width:100%}
  .grid>*{grid-column:span 12!important}
}
@media print{.side,.buscar,.tabla-barra{display:none}.app{display:block}.card,.kpi{box-shadow:none}#tip{display:none}body::before{display:none}}
"""

# Comportamiento: tooltips, índice con la sección activa, buscador global y tablas con
# buscador, filtros por la columna de estado/severidad y orden por columna.
JS = r"""
(function(){
var t=document.createElement('div');t.id='tip';document.body.appendChild(t);
function show(e){var el=e.target.closest&&e.target.closest('[data-tip]');if(!el){t.className='';return;}
t.textContent=el.getAttribute('data-tip');t.className='on';var r=el.getBoundingClientRect(),x=e.clientX||r.left+r.width/2,y=e.clientY||r.top;
var w=t.offsetWidth,h=t.offsetHeight;t.style.left=Math.max(8,Math.min(x+14,innerWidth-w-8))+'px';t.style.top=(y-h-12<4?y+16:y-h-12)+'px';}
document.addEventListener('mousemove',show);document.addEventListener('focusin',show);
document.addEventListener('mouseleave',function(){t.className='';});

// Visor de evidencia: las miniaturas (a.lb) se amplían acá; si el archivo no existe, se avisa.
var lb=document.createElement('div');lb.id='lb';lb.setAttribute('role','dialog');lb.setAttribute('aria-label','Evidencia ampliada');
lb.innerHTML='<img alt=""><div class="msg"></div><div class="pie"><span class="nom"></span><a target="_blank" rel="noopener">Abrir en otra pestaña</a><span>Esc para cerrar</span></div>';
document.body.appendChild(lb);var lbi=lb.querySelector('img'),lbm=lb.querySelector('.msg');
function sinArchivo(ruta){return 'No se encontró la evidencia en '+ruta+'. Verificá que el archivo exista y que la ruta sea relativa al reporte (el HTML tiene que quedar en la misma carpeta que su carpeta de evidencia).';}
lbi.addEventListener('error',function(){lb.classList.add('error');lbm.textContent=sinArchivo(lbi.getAttribute('src'));});
document.addEventListener('click',function(ev){var a=ev.target.closest&&ev.target.closest('a.lb');
  if(a){ev.preventDefault();var r=a.getAttribute('href');lb.className='on';lbi.alt=a.title||'';lbi.src=r;
    lb.querySelector('.nom').textContent=a.title||r;lb.querySelector('.pie a').href=r;return;}
  if(ev.target.closest&&ev.target.closest('#lb')&&!ev.target.closest('.pie a'))lb.className='';});
document.addEventListener('keydown',function(ev){if(ev.key==='Escape')lb.className='';});
// Imágenes más chicas que la miniatura (un elemento recortado): se muestran a su tamaño, sin estirar.
// Capturas de escritorio anchas: la miniatura se enfoca en la parte superior izquierda (los primeros
// 800 px), donde están el encabezado y el contenido; el visor muestra la captura completa.
function medir(im){var a=im.closest&&im.closest('a.thumb');if(!a||!im.naturalWidth)return;
  if(im.naturalWidth<a.clientWidth*1.6&&im.naturalHeight<a.clientHeight*2.5){a.classList.add('chico');return;}
  if(im.naturalWidth>1000&&!a.closest('.film')){im.style.flex='none';im.style.maxWidth='none';im.style.height='auto';
    im.style.width=Math.round(a.clientWidth*im.naturalWidth/800)+'px';}}
document.addEventListener('load',function(ev){if(ev.target&&ev.target.tagName==='IMG')medir(ev.target);},true);
[].forEach.call(document.querySelectorAll('a.thumb img'),function(im){if(im.complete)medir(im);});
// Miniaturas cuyo archivo no existe: se marcan en lugar de quedar en blanco.
document.addEventListener('error',function(ev){var im=ev.target;if(!im||im.tagName!=='IMG'||!im.closest('a.lb'))return;var a=im.closest('a.lb');
  a.classList.add('falta');a.setAttribute('data-tip',sinArchivo(a.getAttribute('href')));a.textContent='Evidencia no encontrada';},true);

// Índice de la barra lateral
var nav=document.getElementById('nav'),secs=[].slice.call(document.querySelectorAll('.section[data-nav]'));
if(nav&&secs.length){var tt=document.createElement('div');tt.className='t';tt.textContent='En este reporte';nav.appendChild(tt);
secs.forEach(function(s){var a=document.createElement('a');a.href='#'+s.id;a.innerHTML='<i></i>';a.appendChild(document.createTextNode(s.getAttribute('data-nav')));nav.appendChild(a);s._a=a;});
if('IntersectionObserver' in window){var vis={};var io=new IntersectionObserver(function(es){es.forEach(function(en){vis[en.target.id]=en.isIntersecting;});
for(var i=0;i<secs.length;i++){if(vis[secs[i].id]){secs.forEach(function(x){x._a.classList.remove('on');});secs[i]._a.classList.add('on');
if(nav.scrollWidth>nav.clientWidth)secs[i]._a.scrollIntoView({block:'nearest',inline:'nearest'});break;}}},{rootMargin:'-10% 0px -60% 0px'});
secs.forEach(function(s){io.observe(s);});}}

// Tablas: buscador, filtros y orden
var FILTRAR=['severidad','estado','tipo','causa probable','categoría','resultado','riesgo','prioridad','dispositivo','nivel','cobertura'];
var tablas=[].slice.call(document.querySelectorAll('.tablecard table'));
function texto(c){return (c.innerText||c.textContent||'').trim();}
tablas.forEach(function(tb){
  var filas=[].slice.call(tb.tBodies[0]?tb.tBodies[0].rows:[]),ths=[].slice.call(tb.tHead?tb.tHead.rows[0].cells:[]);
  ths.forEach(function(th,i){th.classList.add('ord');th.addEventListener('click',function(){
    var asc=!th.classList.contains('asc');ths.forEach(function(x){x.classList.remove('asc','desc');});th.classList.add(asc?'asc':'desc');
    var cuerpo=tb.tBodies[0],fs=[].slice.call(cuerpo.rows);
    fs.sort(function(a,b){var x=texto(a.cells[i]||a),y=texto(b.cells[i]||b),nx=parseFloat(x.replace(/[^\d,.-]/g,'').replace(',','.')),ny=parseFloat(y.replace(/[^\d,.-]/g,'').replace(',','.'));
      var r=(!isNaN(nx)&&!isNaN(ny)&&/^\s*[\d.,-]/.test(x)&&/^\s*[\d.,-]/.test(y))?nx-ny:x.localeCompare(y,'es',{numeric:true});return asc?r:-r;});
    fs.forEach(function(f){cuerpo.appendChild(f);});});});
  if(filas.length<6)return;
  var col=-1;ths.forEach(function(th,i){if(col<0&&FILTRAR.indexOf(texto(th).toLowerCase())>=0)col=i;});
  var barra=document.createElement('div');barra.className='tabla-barra';
  barra.innerHTML='<label class="bq"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M16.5 16.5L21 21"/></svg><input type="search" placeholder="Buscar en la tabla…"></label>';
  var activo=null,q='';
  if(col>=0){var cuenta={};filas.forEach(function(f){var v=texto(f.cells[col]||f).replace(/^[^\wÁÉÍÓÚáéíóúÑñ]+/,'').split('\n')[0];if(v)cuenta[v]=(cuenta[v]||0)+1;});
    var claves=Object.keys(cuenta);if(claves.length>1&&claves.length<=8){
      var todos=document.createElement('button');todos.className='f on';todos.innerHTML='Todos<b>'+filas.length+'</b>';barra.appendChild(todos);
      claves.forEach(function(k){var b=document.createElement('button');b.className='f';b.innerHTML=k+'<b>'+cuenta[k]+'</b>';b._v=k;barra.appendChild(b);});
      barra.addEventListener('click',function(ev){var b=ev.target.closest('.f');if(!b)return;[].forEach.call(barra.querySelectorAll('.f'),function(x){x.classList.remove('on');});
        b.classList.add('on');activo=b._v||null;aplicar();});}}
  var cnt=document.createElement('span');cnt.className='cnt';barra.appendChild(cnt);
  function aplicar(){var n=0;filas.forEach(function(f){var ok=(!q||texto(f).toLowerCase().indexOf(q)>=0)&&(!activo||texto(f.cells[col]||f).indexOf(activo)>=0);
    f.classList.toggle('oculta',!ok);if(ok)n++;});cnt.textContent=n+' de '+filas.length+' filas';}
  barra.querySelector('input').addEventListener('input',function(e){q=e.target.value.trim().toLowerCase();aplicar();});
  var tc=tb.closest('.tablecard');tc.parentNode.insertBefore(barra,tc);aplicar();tb._aplicar=function(v){q=v;barra.querySelector('input').value=v;aplicar();};
});

// Buscador global: filtra todas las tablas (Ctrl+K o /)
var gb=document.getElementById('buscar');
if(gb){gb.addEventListener('input',function(){var v=gb.value.trim().toLowerCase();tablas.forEach(function(tb){if(tb._aplicar)tb._aplicar(v);
  else [].forEach.call(tb.tBodies[0]?tb.tBodies[0].rows:[],function(f){f.classList.toggle('oculta',v&&texto(f).toLowerCase().indexOf(v)<0);});});});
  document.addEventListener('keydown',function(e){if((e.key==='k'&&(e.ctrlKey||e.metaKey))||(e.key==='/'&&document.activeElement.tagName!=='INPUT')){e.preventDefault();gb.focus();}});}
})();
"""


def e(s):
    return html.escape(str(s if s is not None else ""))


def _slug(texto):
    s = re.sub(r"[^a-z0-9]+", "-", (texto or "").lower().translate(str.maketrans("áéíóúñü", "aeiounu"))).strip("-")
    return s or "seccion"


_IDS = {}


def _id_unico(titulo):
    base = "s-" + _slug(titulo)
    n = _IDS.get(base, 0)
    _IDS[base] = n + 1
    return base if n == 0 else f"{base}-{n + 1}"


def page(titulo, eyebrow, meta_html, body):
    _IDS.clear()
    return (f'<!doctype html>\n<html lang="es"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="color-scheme" content="dark">'
            f'<title>{e(titulo)} — k0lmenIA</title><style>{FUENTES}{CSS}</style></head>'
            f'<body><div class="app"><aside class="side">'
            f'<div class="logo"><span class="mk">🪖</span><div><b>k0lmenIA</b><span>{e(eyebrow)}</span></div></div>'
            f'<nav class="nav" id="nav" aria-label="Secciones del reporte"></nav>'
            f'<div class="side-foot">Generado por k0lmenIA · reporte autocontenido, sin internet</div></aside>'
            f'<main class="main"><div class="wrap"><header class="top"><div>'
            f'<span class="eyebrow">{e(eyebrow)}</span><h1>{e(titulo)}</h1>{meta_html}</div>'
            f'<label class="buscar"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
            f'<circle cx="11" cy="11" r="7"/><path d="M16.5 16.5L21 21"/></svg>'
            f'<input id="buscar" type="search" placeholder="Buscar en las tablas…" aria-label="Buscar en las tablas"><kbd>Ctrl K</kbd></label>'
            f'</header><div class="grid">{body}</div>'
            f'<footer><span>Generado por k0lmenIA</span></footer></div></main></div>'
            f'<script>{JS}</script></body></html>\n')


def meta(items):
    """items: lista de (clave, valor); ignora valores vacíos."""
    parts = [f'<span class="chip"><span class="k">{e(k)}</span> {e(v)}</span>' for k, v in items if v]
    return f'<div class="meta">{"".join(parts)}</div>' if parts else ""


def section(titulo, body_html, sub="", ancho=12):
    """Tarjeta de la grilla con su título adentro. ancho: columnas de 12 (12, 8, 6, 4)."""
    s = f'<span class="sub">{e(sub)}</span>' if sub else ""
    estilo = f' style="grid-column:span {ancho}"' if ancho != 12 else ""
    return (f'<section class="section" id="{_id_unico(titulo)}" data-nav="{e(titulo)}"{estilo}><div class="card">'
            f'<div class="section-title"><h2>{e(titulo)}</h2>{s}</div>{body_html}</div></section>')


def section_group(titulo, body_html, sub=""):
    s = f'<span class="sub">{e(sub)}</span>' if sub else ""
    return (f'<section class="section" id="{_id_unico(titulo)}" data-nav="{e(titulo)}"><div class="grupo-titulo"><h2>{e(titulo)}</h2>{s}</div>'
            f'<div class="subgrid">{body_html}</div></section>')


ICONO_TONO = {"ok": "✓", "bad": "✕", "warn": "!", "blk": "⊘"}
TEXTO_TONO = {"ok": "En orden", "bad": "Crítico", "warn": "Revisar", "blk": "Neutro"}

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


def sparkline(valores, color=ACENTO, ancho=160, alto=30):
    """Mini línea con área para un indicador (sin ejes)."""
    vs = [v for v in valores if v is not None]
    if len(vs) < 2:
        return ""
    lo, hi = min(vs), max(vs)
    rng = (hi - lo) or 1
    pts = [(i / (len(vs) - 1) * ancho, alto - 3 - (v - lo) / rng * (alto - 6)) for i, v in enumerate(vs)]
    d = _curva(pts)
    _GRAD[0] += 1
    gid = f"sp{_GRAD[0]}"
    return (f'<svg viewBox="0 0 {ancho} {alto}" preserveAspectRatio="none"><defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{color}" stop-opacity=".35"/><stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>'
            f'<path d="{d} L{ancho},{alto} L0,{alto} Z" fill="url(#{gid})"/>'
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" vector-effect="non-scaling-stroke"/></svg>')


def kpi_tiles(items):
    """items: (etiqueta, valor, tono[, detalle[, icono[, extra]]]). tono: '' | 'ok' | 'bad' | 'blk' | 'warn'.
    icono: un nombre de ICONOS; si falta, se elige por la etiqueta. extra: {"pct": n} suma una barra de
    progreso y {"serie": [...]} un sparkline. El tono colorea el ícono y además se muestra como etiqueta
    con símbolo y texto en la esquina: el estado nunca depende solo del color."""
    out = ""
    for it in items:
        label, val, tono = it[0], it[1], it[2]
        detalle = it[3] if len(it) > 3 else ""
        ic = it[4] if len(it) > 4 and it[4] else _icono_de(label, tono)
        extra = it[5] if len(it) > 5 and it[5] else {}
        st = f'<span class="st">{ICONO_TONO[tono]} {TEXTO_TONO[tono]}</span>' if tono in ICONO_TONO else ""
        d = f'<div class="d">{e(detalle)}</div>' if detalle else ""
        adorno = ""
        if extra.get("pct") is not None:
            adorno = f'<div class="bar"><span style="width:{max(0, min(100, extra["pct"])):.0f}%"></span></div>'
        elif extra.get("serie"):
            adorno = f'<div class="spark">{sparkline(extra["serie"])}</div>'
        out += (f'<div class="kpi {tono}"><div class="ic">{icono(ic)}</div>{st}'
                f'<div class="l">{e(label)}</div><div class="n">{e(val)}</div>{d}{adorno}</div>')
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


def resolver_evidencia(ruta, dir_html, raiz=None):
    """(ruta relativa al HTML, existe). Acepta la ruta relativa al reporte (lo correcto), relativa a la
    raíz del repo (output/ejecuciones/evidencia/x.png) o absoluta, y la devuelve relativa al HTML."""
    if not ruta:
        return None, False
    if re.match(r"^(https?:|data:)", str(ruta)):
        return ruta, True
    dir_html = Path(dir_html).resolve()
    raiz = Path(raiz).resolve() if raiz else Path(__file__).resolve().parents[1]
    p = Path(str(ruta).replace("\\", "/"))
    for cand in ([p] if p.is_absolute() else [dir_html / p, raiz / p, Path.cwd() / p]):
        if cand.exists():
            try:
                return Path(os.path.relpath(cand.resolve(), dir_html)).as_posix(), True
            except ValueError:  # otro disco en Windows: ruta absoluta como URL de archivo
                return cand.resolve().as_uri(), True
    return str(ruta).replace("\\", "/"), False


def miniatura(ruta, titulo="", clase="", existe=True):
    """Miniatura que se amplía en el visor. Con existe=False (el archivo no está) muestra el aviso."""
    if not ruta:
        return '<span class="muted">—</span>'
    if not existe:
        return (f'<span class="falta-ev" data-tip="No se encontró la evidencia en {e(ruta)}" tabindex="0">'
                f'! Evidencia no encontrada</span>')
    return (f'<a class="lb thumb {clase}" href="{e(ruta)}" title="{e(titulo)}">'
            f'<img src="{e(ruta)}" loading="lazy" alt="{e(titulo or "Evidencia")}"></a>')


def _pastilla(texto, color, icono_txt):
    return (f'<span class="pill" style="background:{_soft(color, .13)};color:var(--ink);box-shadow:inset 0 0 0 1px {_soft(color, .34)}">'
            f'<span style="color:{color}">{icono_txt}</span>{e(texto)}</span>')


def nivel_badge(nivel):
    n = (nivel or "").strip()
    return _pastilla(n or "—", NIVEL_COLOR.get(n, NEUTRO), NIVEL_ICONO.get(n, "●"))


def estado_pill(estado):
    s = (estado or "").strip()
    return _pastilla(s or "—", ESTADO_COLOR.get(s, NEUTRO), ESTADO_ICONO.get(s, "●"))


# ------------------------------------------------------------------ gráficos
_GRAD = [0]


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


def _degradado(color, vertical=True):
    """Id de un degradado del color (claro arriba/derecha → el color abajo/izquierda) y su <defs>."""
    _GRAD[0] += 1
    gid = f"g{_GRAD[0]}"
    x2, y2 = ("0", "1") if vertical else ("1", "0")
    return gid, (f'<linearGradient id="{gid}" x1="0" y1="0" x2="{x2}" y2="{y2}">'
                 f'<stop offset="0" stop-color="{_aclarar(color, .18) if vertical else color}"/>'
                 f'<stop offset="1" stop-color="{color if vertical else _aclarar(color, .18)}" stop-opacity="{.55 if vertical else 1}"/></linearGradient>')


def _barra_vertical(x, y_base, ancho, alto, color, tip, relleno=None):
    """Columna con el extremo de datos redondeado y la base recta."""
    r = min(6, ancho / 2, alto)
    if alto <= 0:
        return ""
    y = y_base - alto
    d = (f"M{x:.1f},{y_base:.1f} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} "
         f"H{x + ancho - r:.1f} Q{x + ancho:.1f},{y:.1f} {x + ancho:.1f},{y + r:.1f} V{y_base:.1f} Z")
    return f'<path class="mark" d="{d}" fill="{relleno or color}" data-tip="{e(tip)}" tabindex="0"/>'


def _grilla_y(W, izq, der, y_de, maxv, paso, fmt):
    out, i = [], 0
    while i * paso <= maxv + 1e-9:
        y = y_de(i * paso)
        out.append(f'<line class="{"base" if i == 0 else "grid-l"}" x1="{izq}" x2="{W - der}" y1="{y:.1f}" y2="{y:.1f}"/>'
                   f'<text class="axis" x="{izq - 10}" y="{y + 4:.1f}" text-anchor="end">{e(_num(i * paso, fmt))}</text>')
        i += 1
    return out


def donut(segments, pct, label="aprobados"):
    """segments: [(valor, color[, nombre])]. El centro muestra pct + label."""
    r, cx, cy, w = 74, 100, 100, 18
    C = 2 * math.pi * r
    total = sum(s[0] for s in segments) or 1
    track = (f'<circle cx="{cx}" cy="{cy}" r="{r + 15}" fill="rgba(255,255,255,.015)"/>'
             f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="rgba(255,255,255,.05)" stroke-width="{w}"/>')
    segs, acc = "", 0.0
    gap = 4 if sum(1 for s in segments if s[0]) > 1 else 0
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
            f'<text x="{cx}" y="{cy + 7}" text-anchor="middle" class="donut-num">{pct}%</text>'
            f'<text x="{cx}" y="{cy + 29}" text-anchor="middle" class="donut-lbl">{e(label)}</text></svg>')


def donut_panel(segments, pct, label):
    """Dona + leyenda en filas (nombre, valor, % y barra de proporción), para usar como cuerpo de section()."""
    total = sum(s[0] for s in segments) or 1
    filas = "".join(f'<div class="r"><i style="background:{s[1]}"></i><span>{e(s[2] if len(s) > 2 else "")}</span>'
                    f'<b>{e(_num(s[0]))}</b><em>{s[0] / total * 100:.0f} %</em>'
                    f'<div class="p"><span style="width:{s[0] / total * 100:.1f}%;background:{s[1]}"></span></div></div>' for s in segments)
    return f'<div class="panorama"><div class="gauge">{donut(segments, pct, label)}</div><div class="dleg">{filas}</div></div>'


def gauge(pct, label="", tono=None, tam=220):
    """Medidor semicircular 0-100 (puntajes). tono: ok | warn | bad (si falta, según el valor)."""
    pct = max(0, min(100, pct or 0))
    color = {"ok": OK, "warn": AVISO, "bad": CRITICO}.get(tono) or (OK if pct >= 90 else AVISO if pct >= 50 else CRITICO)
    r, cx, cy, w = tam / 2 - 16, tam / 2, tam / 2, 16
    largo = math.pi * r
    arco = f"M{cx - r:.1f},{cy:.1f} A{r:.1f},{r:.1f} 0 0 1 {cx + r:.1f},{cy:.1f}"
    _GRAD[0] += 1
    gid = f"ga{_GRAD[0]}"
    return (f'<svg viewBox="0 0 {tam} {tam / 2 + 34}" width="{tam}" role="img" aria-label="{pct:.0f} de 100 {e(label)}">'
            f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{color}" stop-opacity=".55"/>'
            f'<stop offset="1" stop-color="{_aclarar(color, .15)}"/></linearGradient></defs>'
            f'<path d="{arco}" fill="none" stroke="rgba(255,255,255,.06)" stroke-width="{w}" stroke-linecap="round"/>'
            f'<path d="{arco}" fill="none" stroke="url(#{gid})" stroke-width="{w}" stroke-linecap="round" '
            f'stroke-dasharray="{largo * pct / 100:.1f} {largo:.1f}"/>'
            f'<text x="{cx}" y="{cy - 6}" text-anchor="middle" class="donut-num">{pct:.0f}</text>'
            f'<text x="{cx}" y="{cy + 22}" text-anchor="middle" class="donut-lbl">{e(label)}</text></svg>')


def bar_chart(rows, ancho_etiqueta=120):
    """rows: [(etiqueta, valor, color)]. Barras horizontales con degradado, normalizadas al máximo,
    sobre un riel tenue; valor al final. ancho_etiqueta: ancho de la columna de etiquetas en px."""
    rows = list(rows)
    maxv = max((c for _, c, _ in rows), default=0)
    if not rows or maxv == 0:
        return '<div class="cardbody"><p class="muted">Sin datos.</p></div>'
    out = ""
    for label, count, color in rows:
        ancho = count / maxv * 100
        seg = (f'<span class="seg" style="width:100%;background:linear-gradient(90deg,{_soft(color, .55)},{color} 70%,{_aclarar(color, .2)});'
               f'box-shadow:0 0 14px -2px {_soft(color, .55)}"></span>') if count else ""
        out += (f'<div class="bar-row" data-tip="{e(label)}: {e(_num(count))}" tabindex="0"><div class="bar-label"><span>{e(label)}</span></div>'
                f'<div class="bar-wrap"><div class="bar-track" style="width:{max(ancho, 1.2 if count else 0):.1f}%">{seg}</div></div>'
                f'<div class="bar-count">{e(_num(count))}</div></div>')
    return f'<div class="bars" style="--lw:{ancho_etiqueta}px">{out}</div>'


def column_chart(rows, fmt=None, alto=280, ancho=1320):
    """rows: [(etiqueta, valor[, color])]. Columnas verticales de una serie (verde azulado por
    defecto) con degradado sobre un riel tenue y el valor sobre la punta. Hasta ~12 categorías."""
    rows = [r for r in rows if r[1] is not None]
    if not rows or max(r[1] for r in rows) <= 0:
        return '<div class="cardbody"><p class="muted">Sin datos.</p></div>'
    W, H, izq, der, arriba, abajo = ancho, alto, 52, 10, 28, 40
    maxv, paso = _escala(max(r[1] for r in rows))
    ph = H - arriba - abajo
    y0 = arriba + ph
    svg = _grilla_y(W, izq, der, lambda v: y0 - ph * v / maxv, maxv, paso, fmt)
    defs = []
    banda = (W - izq - der) / len(rows)
    col = min(48, banda * 0.56)
    for k, r in enumerate(rows):
        etiqueta, v = r[0], r[1]
        color = r[2] if len(r) > 2 and r[2] else SERIES[0]
        gid, dg = _degradado(color)
        defs.append(dg)
        x = izq + k * banda + (banda - col) / 2
        h = ph * v / maxv
        svg.append(f'<rect x="{x:.1f}" y="{arriba}" width="{col:.1f}" height="{ph}" rx="6" fill="rgba(255,255,255,.025)"/>')
        svg.append(_barra_vertical(x, y0, col, h, color, f"{etiqueta}: {_num(v, fmt)}", f"url(#{gid})"))
        svg.append(f'<text class="val" x="{x + col / 2:.1f}" y="{y0 - h - 9:.1f}" text-anchor="middle">{e(_num(v, fmt))}</text>')
        corto = etiqueta if len(etiqueta) * 6.4 <= banda else etiqueta[:max(int(banda / 6.4) - 1, 3)] + "…"
        svg.append(f'<text class="lbl" x="{izq + k * banda + banda / 2:.1f}" y="{H - 14}" text-anchor="middle">{e(corto)}<title>{e(etiqueta)}</title></text>')
    return f'<div class="chart"><svg viewBox="0 0 {W} {H}" role="img"><defs>{"".join(defs)}</defs>{"".join(svg)}</svg></div>'


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
    return f'<div class="bars">{out}<div style="margin-top:10px">{legend(series) if len(series) > 1 else ""}</div></div>'


def grouped_columns(grupos, series, fmt=None, alto=300, ancho=1320):
    """grupos: etiquetas del eje X; series: [(nombre, color, [valor por grupo])]. Un solo eje Y.
    ancho: lienzo en px (1320 a todo el ancho; 660 en una grilla de dos columnas, así el texto no cambia de tamaño)."""
    valores = [v for _, _, vs in series for v in vs if v is not None]
    if not valores:
        return '<div class="cardbody"><p class="muted">Sin datos.</p></div>'
    W, H, izq, der, arriba, abajo = ancho, alto, 58, 8, 24, 40
    maxv, paso = _escala(max(valores))
    ph = H - arriba - abajo
    y0 = arriba + ph
    svg = _grilla_y(W, izq, der, lambda v: y0 - ph * v / maxv, maxv, paso, fmt)
    defs, rellenos = [], {}
    for _, color, _ in series:
        gid, dg = _degradado(color)
        defs.append(dg)
        rellenos[color] = f"url(#{gid})"
    ancho_grupo = (W - izq - der) / len(grupos)
    col = min(30, (ancho_grupo * 0.7 - 3 * (len(series) - 1)) / len(series))
    for g, nombre in enumerate(grupos):
        x0 = izq + g * ancho_grupo + (ancho_grupo - (col * len(series) + 3 * (len(series) - 1))) / 2
        svg.append(f'<rect x="{x0 - 8:.1f}" y="{arriba}" width="{col * len(series) + 3 * (len(series) - 1) + 16:.1f}" height="{ph}" rx="8" fill="rgba(255,255,255,.02)"/>')
        for s, (sn, color, vs) in enumerate(series):
            v = vs[g]
            if v is None:
                continue
            svg.append(_barra_vertical(x0 + s * (col + 3), y0, col, ph * v / maxv, color, f"{nombre} · {sn}: {_num(v, fmt)}", rellenos[color]))
        corto = nombre if len(nombre) * 6.6 <= ancho_grupo else nombre[:max(int(ancho_grupo / 6.6) - 1, 3)] + "…"
        svg.append(f'<text class="lbl" x="{izq + g * ancho_grupo + ancho_grupo / 2:.1f}" y="{H - 14}" text-anchor="middle">'
                   f'{e(corto)}<title>{e(nombre)}</title></text>')
    if len(series) == 1:  # una sola serie: el valor sobre cada columna (son pocas)
        for g, v in enumerate(series[0][2]):
            if v is not None and len(grupos) <= 12:
                x = izq + g * ancho_grupo + ancho_grupo / 2
                svg.append(f'<text class="val" x="{x:.1f}" y="{y0 - ph * v / maxv - 9:.1f}" text-anchor="middle">{e(_num(v, fmt))}</text>')
    ley = legend([(n, c) for n, c, _ in series]) if len(series) > 1 else ""
    return f'<div class="chart"><svg viewBox="0 0 {W} {H}" role="img"><defs>{"".join(defs)}</defs>{"".join(svg)}</svg>{ley}</div>'


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


def line_chart(x, series, fmt=None, fmt_x=None, alto=300, area=None, ancho=1320):
    """x: valores del eje X (números); series: [(nombre, color, [valor por x])]. Un solo eje Y,
    curvas suaves de 2px con brillo, área con degradado (por defecto, si hay una sola serie), puntos
    y etiquetas en el máximo y el último valor, y crosshair con el valor de todas las series."""
    if len(x) < 2 or not any(v is not None for _, _, vs in series for v in vs):
        return '<p class="muted" style="padding:16px 24px">Sin datos suficientes para la evolución.</p>'
    if area is None:
        area = len(series) == 1
    W, H, izq, der, arriba, abajo = ancho, alto, 58, 18, 26, 30
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
                        f'<stop offset="0" stop-color="{color}" stop-opacity=".38"/><stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient>')
            svg.append(f'<path d="{d} L{pts[-1][0]:.1f},{py(0):.1f} L{pts[0][0]:.1f},{py(0):.1f} Z" fill="url(#{gid})"/>')
        svg.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="6" stroke-opacity=".14" stroke-linejoin="round" stroke-linecap="round"/>')
        svg.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>')
        if len(pts) <= 40:
            svg += [f'<circle cx="{a:.1f}" cy="{b:.1f}" r="3.2" fill="{SUPERFICIE}" stroke="{color}" stroke-width="2"/>' for a, b in pts]
        reales = [(xv, v) for xv, v in zip(x, vs) if v is not None]
        imax = max(range(len(reales)), key=lambda k: reales[k][1])
        for k in sorted({imax, len(reales) - 1} if len(series) == 1 else {len(reales) - 1}):
            xv, v = reales[k]
            svg.append(f'<text class="val" x="{px(xv):.1f}" y="{py(v) - 11:.1f}" text-anchor="middle">{e(_num(v, fmt))}</text>')
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
