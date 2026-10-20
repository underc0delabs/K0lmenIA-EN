#!/usr/bin/env python3
"""
Design system for the k0lmenIA HTML reports (bento dashboard, dark mode, k0lmena.com style).

Every HTML deliverable generator uses it (test plan, run report, closure report, performance,
security, exploratory, accessibility, web performance, failures and coverage), so they all look
the same and the theme lives in a single place.

Page structure: sidebar with the brand and the report index (built automatically from the
sections, highlighting the one being read), header with a search box and a 12-column bento grid.
Long tables automatically get a search box, filters on the status or severity column and sorting
when the header is clicked.

Page and structure
  page(title, eyebrow, meta_html, body)     full document (sidebar, header, footer)
  meta(items)                               context chips (Story, Date, ...)
  section(title, body_html, sub="", width=12)   grid card (12 = full width, 6 = half, 4 = third)
  section_group(title, body_html, sub="")   title of a group of cards (goes outside)
  two_col(left, right)                      two sections side by side (each takes half)
  banner(text, tone)                        highlighted verdict (ok | warn | bad)
  kpi_tiles(items)                          indicators (label, value, tone[, detail[, icon[, extra]]])
                                            extra: {"pct": 0-100} progress bar · {"series": [numbers]} sparkline
  table(headers, rows)                      table (cells may contain HTML)
  doc_list(items)                           bulleted list
  missing_info(items, sub="")               "Missing information" section ({id, what_is_missing, question}; "description" works as an alias)
  warn_analysis(analysis, ids)              warns on stderr about analysis IDs that do not exist and severities off the scale
  level_badge(level) / status_pill(status)  pills with icon + text (never color alone)
  legend(items)                             legend (name, color[, value])

Charts (inline SVG, with a tooltip on hover or focus)
  donut(segments, pct, label)               donut: segments = [(value, color[, name])]
  donut_panel(segments, pct, label)         donut + legend with value, % and proportion bar
  gauge(pct, label, tone)                   semicircular gauge (0-100 scores)
  sparkline(values, color)                  mini line for an indicator
  bar_chart(rows)                           horizontal bars: [(label, value, color)]
  column_chart(rows, fmt)                   columns: [(label, value[, color])], value on top
  stacked_bars(rows, series)                stacked bars: rows = [(label, [v1, v2...])]
  grouped_columns(groups, series, fmt)      grouped columns, a single axis
  line_chart(x, series, fmt, area)          smooth lines on one axis, with area and crosshair

Brand (k0lmena.com): night background #0E0C09, charcoal surfaces #1A1712 / #221E17, wax text #F4EFE6,
  amber accent #F9B006 (neon #FFD60A -> #FF8A00), honeycomb pattern in the header.
Data colors (dataviz skill, validated with its script against the #1A1712 surface):
  categorical #C98500 #14A895 #4C8DEB #E0702E #9085E9 #D55181 #008300 #E66767
              (fixed order, never cycled; the first is the brand amber lowered to the charts'
              lightness band; the first three also pass every pair)
  status      ok #5CBF4A · warning #FFD60A · serious #FF8A00 · critical #FF5A4E (always with icon and text)
Typography (the k0lmena.com one, scripts/fonts, OFL license, embedded in base64):
  Saira (titles), Inter (text) and JetBrains Mono (code, IDs, labels and numbers).
No external dependencies: CSS, fonts, SVG and JS are inline, no internet needed.
"""
import base64
import html
import math
import os
import re
import sys
from pathlib import Path

# ------------------------------------------------------------------ tokens
BACKGROUND = "#0E0C09"  # night (k0lmena.com)
SURFACE = "#1A1712"     # charcoal
# Categorical (fixed order, never cycled): amber, teal, blue, orange, violet, magenta, green, red
SERIES = ["#C98500", "#14A895", "#4C8DEB", "#E0702E", "#9085E9", "#D55181", "#008300", "#E66767"]
# Status (reserved: never used as "series 4")
OK, WARNING, SERIOUS, CRITICAL, NEUTRAL = "#5CBF4A", "#FFD60A", "#FF8A00", "#FF5A4E", "#8A8172"
ACCENT = "#F9B006"      # brand amber (UI and single-series charts)

PALETTE = {"bg": BACKGROUND, "surface": SURFACE, "tile": "#221E17", "border": "#2E281F",
          "ink": "#F4EFE6", "body": "#CFC7B8", "muted": "#8A8172",
          "ok": OK, "bad": CRITICAL, "blk": NEUTRAL, "warn": WARNING, "accent": ACCENT}

# Levels / severities -> status scale (with its icon and text, never color alone)
LEVEL_COLOR = {"Critical": CRITICAL, "High": SERIOUS, "Medium": WARNING, "Low": NEUTRAL}
LEVEL_ICON = {"Critical": "▲", "High": "▲", "Medium": "●", "Low": "▼"}
STATUS_COLOR = {"Passed": OK, "Failed": CRITICAL, "Blocked": NEUTRAL, "Pending": WARNING, "N/A": NEUTRAL,
                "In progress": SERIES[2]}
STATUS_ICON = {"Passed": "✓", "Failed": "✕", "Blocked": "⊘", "Pending": "◷", "N/A": "–", "In progress": "▶"}


def _soft(hexcolor, alpha=0.16):
    h = hexcolor.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _lighten(hexcolor, f=0.35):
    """The color mixed with white (for the light end of a gradient)."""
    h = hexcolor.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02X%02X%02X" % tuple(round(c + (255 - c) * f) for c in (r, g, b))


# Line icons (24x24, 1.8 stroke) for the indicators and navigation.
ICONS = {
    "grid": '<rect x="4" y="4" width="6" height="6" rx="1.5"/><rect x="14" y="4" width="6" height="6" rx="1.5"/><rect x="4" y="14" width="6" height="6" rx="1.5"/><rect x="14" y="14" width="6" height="6" rx="1.5"/>',
    "ok": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.7 2.7L16 9.8"/>',
    "bad": '<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>',
    "warn": '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17.2v.1"/>',
    "blk": '<circle cx="12" cy="12" r="9"/><path d="M6 6l12 12"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "page": '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5M10 13h6M10 17h6"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "image": '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="M21 16l-5-5-8 8"/>',
    "code": '<path d="M9 8l-4 4 4 4M15 8l4 4-4 4"/>',
    "screen": '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M9 20h6M12 16v4"/>',
    "bolt": '<path d="M13 3L5 14h6l-1 7 8-11h-6z"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
    "keyboard": '<rect x="3" y="7" width="18" height="10" rx="2"/><path d="M7 11h.1M11 11h.1M15 11h.1M8 14h8"/>',
    "person": '<circle cx="12" cy="6" r="2.2"/><path d="M5 9.5l7 1.5 7-1.5M12 11v4l-3 5M12 15l3 5"/>',
    "list": '<path d="M9 6h11M9 12h11M9 18h11M4.5 6h.1M4.5 12h.1M4.5 18h.1"/>',
    "bug": '<rect x="8" y="7" width="8" height="12" rx="4"/><path d="M12 7V4M8 11H4M16 11h4M8 15H5M16 15h3M9 5l1.5 2M15 5l-1.5 2"/>',
    "load": '<path d="M4 18l5-6 4 3 7-9"/><path d="M15 6h5v5"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
    "target": '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1"/>',
    "move": '<path d="M12 3v18M3 12h18M12 3l-3 3M12 3l3 3M12 21l-3-3M12 21l3-3M3 12l3-3M3 12l3 3M21 12l-3-3M21 12l-3 3"/>',
    "browser": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M6.5 6.5h.1M9 6.5h.1"/>',
    "key": '<path d="M14.5 4a5.5 5.5 0 0 0-5 7.8L3 18.3V21h2.7l1-1v-2h2v-2h2l1.2-1.2A5.5 5.5 0 1 0 14.5 4z"/><circle cx="16" cy="8" r="1.2"/>',
    "filter": '<path d="M4 5h16l-6 7.5V19l-4 2v-8.5z"/>',
}


def icon(name, size=20):
    return (f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" stroke="currentColor" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS.get(name, ICONS["grid"])}</svg>')


def _fonts():
    """Embedded @font-face for Saira, Inter and JetBrains Mono (if the files are present)."""
    folder = Path(__file__).resolve().parent / "fonts"
    css = ""
    for family, file, weights in (("Saira", "saira.woff2", "500 700"), ("Inter", "inter.woff2", "400 600"),
                                  ("JetBrains Mono", "jetbrains-mono.woff2", "400 700")):
        f = folder / file
        if f.exists():
            data = base64.b64encode(f.read_bytes()).decode()
            css += (f"@font-face{{font-family:'{family}';font-style:normal;font-weight:{weights};font-display:swap;"
                    f"src:url(data:font/woff2;base64,{data}) format('woff2')}}")
    return css


FONTS = _fonts()

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{
  color-scheme:dark;
  --bg:#0E0C09; --surface:#1A1712; --surface-2:#1E1A14; --tile:#221E17; --raised:#2A251D;
  --border:#2E281F; --border-soft:#241F18; --line:rgba(244,239,230,.09); --line-2:rgba(244,239,230,.15);
  --ink:#F4EFE6; --body:#CFC7B8; --muted:#8A8172; --accent:#F9B006; --accent-2:#FF8A00; --accent-soft:rgba(249,176,6,.12);
  --honey:#FFD60A; --neon:linear-gradient(135deg,#FFD60A,#FF8A00); --yellow-line:rgba(249,176,6,.38);
  --glow-k0:0 0 0 1px rgba(249,176,6,.35),0 0 32px -6px rgba(249,176,6,.40);
  --ok:#5CBF4A; --warn:#FFD60A; --serious:#FF8A00; --bad:#FF5A4E; --neutral:#8A8172;
  --radius:14px; --gap:18px; --side:248px;
  --display:"Saira","Inter",ui-sans-serif,system-ui,sans-serif;
  --sans:"Inter",ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --mono:"JetBrains Mono",ui-monospace,"SFMono-Regular",Menlo,Consolas,monospace;
  --honeycomb:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='56' height='100'%3E%3Cpath d='M28 66L0 50L0 16L28 0L56 16L56 50L28 66L28 100' fill='none' stroke='%23F9B006' stroke-opacity='.10' stroke-width='1.2'/%3E%3Cpath d='M28 0L28 34L0 50L0 84L28 100L56 84L56 50L28 34' fill='none' stroke='%23F9B006' stroke-opacity='.07' stroke-width='1.2'/%3E%3C/svg%3E");
}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth;scroll-padding-top:24px}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:14px;line-height:1.55;
  -webkit-font-smoothing:antialiased}
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;
  background:radial-gradient(760px 420px at 100% -8%,rgba(249,176,6,.12),transparent 62%),
             radial-gradient(640px 360px at 0% 0%,rgba(255,138,0,.05),transparent 60%),
             var(--honeycomb) 0 0/56px 100px;
  -webkit-mask-image:linear-gradient(180deg,#000 0,rgba(0,0,0,.55) 420px,rgba(0,0,0,.18) 900px);
  mask-image:linear-gradient(180deg,#000 0,rgba(0,0,0,.55) 420px,rgba(0,0,0,.18) 900px)}
.mono{font-family:var(--mono);font-size:.9em}
.muted{color:var(--muted)}
a{color:var(--accent);text-decoration-color:rgba(249,176,6,.35);text-underline-offset:3px}

/* layout: sidebar + content */
.app{position:relative;z-index:1;display:grid;grid-template-columns:var(--side) minmax(0,1fr);min-height:100vh}
.side{position:sticky;top:0;height:100vh;display:flex;flex-direction:column;gap:18px;padding:22px 16px;
  border-right:1px solid var(--line);background:linear-gradient(180deg,rgba(26,23,18,.94),rgba(14,12,9,.94));backdrop-filter:blur(12px)}
.logo{display:flex;align-items:center;gap:11px;padding:4px 8px 14px;border-bottom:1px solid var(--line)}
.logo .mk{width:36px;height:34px;display:grid;place-items:center;flex:none;clip-path:polygon(25% 3%,75% 3%,100% 50%,75% 97%,25% 97%,0 50%);
  background:var(--neon);color:#0E0C09;font-family:var(--display);font-weight:700;font-size:14px;letter-spacing:-.02em;
  filter:drop-shadow(0 0 10px rgba(249,176,6,.45))}
.logo b{display:block;font-family:var(--display);font-size:16px;font-weight:700;letter-spacing:.02em;color:var(--ink)}
.logo span{display:block;font-family:var(--mono);font-size:10.5px;color:var(--accent);letter-spacing:.04em;font-weight:500;text-transform:lowercase}
.nav{flex:1;overflow:auto;display:flex;flex-direction:column;gap:2px;margin:0 -4px;padding:0 4px}
.nav .t{font-family:var(--mono);font-size:11px;letter-spacing:.02em;color:var(--accent);font-weight:500;padding:4px 10px 8px;text-transform:lowercase}
.nav .t::before{content:"// "}
.nav a{display:flex;align-items:center;gap:10px;padding:7px 10px;border-radius:9px;color:var(--body);text-decoration:none;
  font-size:13px;line-height:1.3;transition:background .15s,color .15s}
.nav a i{width:8px;height:8px;clip-path:polygon(25% 3%,75% 3%,100% 50%,75% 97%,25% 97%,0 50%);background:var(--border);flex:none;transition:background .15s}
.nav a:hover{background:rgba(244,239,230,.04);color:var(--ink)}
.nav a.on{background:var(--accent-soft);color:var(--ink)}
.nav a.on i{background:var(--accent)}
.nav a.on{box-shadow:inset 2px 0 0 var(--accent)}
.side-foot{font-size:11.5px;color:var(--muted);padding:12px 8px 0;border-top:1px solid var(--line)}
.main{min-width:0;padding:26px 34px 56px}
.wrap{max-width:1520px;margin:0 auto}

/* header */
.top{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;flex-wrap:wrap;margin-bottom:22px}
.eyebrow{display:inline-flex;align-items:center;gap:0;font-family:var(--mono);font-size:13px;letter-spacing:.01em;font-weight:500;
  color:var(--accent);text-transform:lowercase}
.eyebrow::before{content:"// "}
h1{font-family:var(--display);font-size:44px;font-weight:700;letter-spacing:-.012em;line-height:1.05;color:var(--ink);margin:12px 0 16px}
.meta{display:flex;flex-wrap:wrap;gap:8px}
.chip{display:inline-flex;align-items:center;gap:7px;font-size:12.5px;color:var(--ink);
  background:rgba(26,23,18,.8);border:1px solid var(--line);border-radius:8px;padding:5px 11px}
.chip .k{color:var(--muted);font-family:var(--mono);font-size:11px;letter-spacing:.02em;font-weight:500;text-transform:lowercase}
.chip a{color:var(--ink);text-decoration:none;border-bottom:1px dashed var(--border)}
.search{display:flex;align-items:center;gap:9px;min-width:260px;padding:9px 14px;border-radius:12px;
  background:var(--surface);border:1px solid var(--line);color:var(--muted)}
.search:focus-within{border-color:var(--yellow-line);box-shadow:var(--glow-k0)}
.search input{all:unset;flex:1;color:var(--ink);font-size:13px}
.search kbd{font-family:var(--mono);font-size:10.5px;border:1px solid var(--line-2);border-radius:5px;padding:1px 5px;color:var(--muted)}

/* bento grid */
.grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:var(--gap)}
.grid>*{grid-column:span 12;min-width:0}
.twocol{display:contents}
.twocol>*{grid-column:span 6;min-width:0}
.grid>div[style*="margin-top"]{margin-top:0!important}
.subgrid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:var(--gap)}
.subgrid>*{grid-column:span 12;min-width:0}

/* cards */
.card,.section>.card{position:relative;border-radius:var(--radius);overflow:hidden;
  background:linear-gradient(180deg,var(--surface-2),var(--surface)) padding-box,
             linear-gradient(180deg,rgba(244,239,230,.12),rgba(244,239,230,.04) 45%,rgba(244,239,230,.06)) border-box;
  border:1px solid transparent;box-shadow:0 1px 0 rgba(244,239,230,.03) inset,0 24px 48px -32px rgba(0,0,0,.9)}
.section{min-width:0;scroll-margin-top:20px}
.section>.card{height:100%}
.section-title{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:18px 22px 6px}
.section-title h2{font-family:var(--display);font-size:18px;font-weight:700;letter-spacing:-.005em;color:var(--ink)}
.section-title h2::before{content:"";display:inline-block;width:11px;height:10px;clip-path:polygon(25% 3%,75% 3%,100% 50%,75% 97%,25% 97%,0 50%);margin:0 10px 2px 0;
  background:var(--neon);vertical-align:middle}
.section-title .sub{font-size:12px;color:var(--muted)}
.group-title{display:flex;align-items:baseline;gap:12px;margin:0 4px 12px}
.group-title h2{font-family:var(--display);font-size:22px;font-weight:700;letter-spacing:-.01em;color:var(--ink)}
.group-title .sub{font-size:12px;color:var(--muted)}
.cardbody{padding:12px 22px 22px;color:var(--body)}
.cardbody p{color:var(--body)}
.cardbody p+p{margin-top:10px}
.lead{font-size:15.5px;color:var(--ink);line-height:1.65}
.subhead{font-family:var(--mono);font-size:11.5px;letter-spacing:.02em;color:var(--accent);font-weight:500;margin-bottom:10px;text-transform:lowercase}
.subhead::before{content:"// "}
.subhead.ok{color:#7BD36A}.subhead.bad{color:#FF7B70}.subhead.warn{color:#FFE066}

/* hero: donut + indicators */
.hero{display:grid;grid-template-columns:260px 1fr;gap:26px;align-items:center;padding:24px 26px}
.gauge{display:flex;flex-direction:column;align-items:center;gap:14px}
.donut-num{font-family:var(--display);font-size:36px;font-weight:700;fill:var(--ink);letter-spacing:-.02em}
.donut-lbl{font-family:var(--mono);font-size:10px;letter-spacing:.06em;text-transform:lowercase;fill:var(--muted);font-weight:500}
.hero .kpi{background:var(--tile)}
.hero .legend{flex-direction:column;gap:8px;align-self:stretch}

/* donut with value legend */
.panorama{display:grid;grid-template-columns:200px 1fr;gap:26px;align-items:center;padding:8px 24px 22px}
.dleg{display:flex;flex-direction:column;gap:2px}
.dleg .r{display:grid;grid-template-columns:12px minmax(0,1fr) auto 46px;gap:4px 12px;align-items:center;padding:9px 0;
  border-bottom:1px solid var(--line);font-size:13px;color:var(--body)}
.dleg .r:last-child{border-bottom:0}
.dleg i{width:10px;height:10px;border-radius:3px}
.dleg b{color:var(--ink);font-weight:620;font-variant-numeric:tabular-nums}
.dleg em{font-style:normal;color:var(--muted);text-align:right;font-variant-numeric:tabular-nums}
.dleg .p{grid-column:2/5;height:4px;border-radius:999px;background:rgba(244,239,230,.06);overflow:hidden}
.dleg .p span{display:block;height:100%;border-radius:999px}

/* legend */
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12.5px;color:var(--body)}
.legend span{display:inline-flex;align-items:center;gap:8px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;flex:none}
.legend b{color:var(--ink);font-weight:620;font-variant-numeric:tabular-nums;margin-left:auto;padding-left:10px}

/* indicators */
.kpis{display:grid;grid-template-columns:repeat(var(--cols,4),minmax(0,1fr));gap:var(--gap)}
.kpi{position:relative;padding:18px 20px 18px;border-radius:18px;display:flex;flex-direction:column;min-height:148px;overflow:hidden;
  background:linear-gradient(180deg,var(--surface-2),var(--surface)) padding-box,
             linear-gradient(180deg,rgba(244,239,230,.12),rgba(244,239,230,.04)) border-box;border:1px solid transparent;
  transition:transform .2s,box-shadow .2s}
.kpi::after{content:"";position:absolute;width:180px;height:180px;right:-70px;top:-90px;border-radius:50%;pointer-events:none;
  background:radial-gradient(circle,var(--glow,rgba(249,176,6,.16)),transparent 70%)}
.kpi:hover{transform:translateY(-2px);box-shadow:var(--glow-k0)}
.kpi.ok{--glow:rgba(92,191,74,.16)} .kpi.bad{--glow:rgba(255,90,78,.2)} .kpi.warn{--glow:rgba(255,214,10,.13)} .kpi.blk{--glow:rgba(138,129,114,.14)}
.kpi .ic{width:42px;height:38px;clip-path:polygon(25% 3%,75% 3%,100% 50%,75% 97%,25% 97%,0 50%);display:grid;place-items:center;color:var(--accent);background:rgba(249,176,6,.14)}
.kpi.ok .ic{color:#7BD36A;background:rgba(92,191,74,.16)}
.kpi.bad .ic{color:#FF7B70;background:rgba(255,90,78,.17)}
.kpi.warn .ic{color:#FFD60A;background:rgba(255,214,10,.14)}
.kpi.blk .ic{color:#B5AC9C;background:rgba(138,129,114,.16)}
.kpi .st{position:absolute;top:18px;right:18px;display:inline-flex;align-items:center;gap:5px;font-family:var(--mono);font-size:10.5px;font-weight:500;
  text-transform:lowercase;letter-spacing:.02em;padding:3px 8px 3px 6px;border-radius:6px}
.kpi.ok .st{color:#7BD36A;background:rgba(92,191,74,.13)} .kpi.bad .st{color:#FF7B70;background:rgba(255,90,78,.15)}
.kpi.warn .st{color:#FFE066;background:rgba(255,214,10,.12)} .kpi.blk .st{color:#B5AC9C;background:rgba(138,129,114,.15)}
.kpi .l{font-size:12px;font-weight:500;color:var(--muted);margin-top:auto;padding-top:16px}
.kpi .n{font-family:var(--display);font-size:34px;font-weight:700;letter-spacing:-.015em;line-height:1.05;color:var(--ink);margin-top:4px;font-variant-numeric:tabular-nums}
.kpi .d{font-size:12px;color:var(--body);margin-top:5px}
.kpi .spark{margin-top:10px;height:30px}
.kpi .spark svg{width:100%;height:30px;display:block;overflow:visible}
.kpi .bar{margin-top:12px;height:5px;border-radius:999px;background:rgba(244,239,230,.07);overflow:hidden}
.kpi .bar span{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,#FFD60A,#FF8A00)}

/* charts */
.chart{padding:6px 22px 20px}
.chart svg{width:100%;height:auto;display:block;overflow:visible}
.chart .legend{margin-top:14px}
.axis{font-size:11px;fill:var(--muted);font-variant-numeric:tabular-nums;font-family:var(--sans)}
.lbl{font-size:12px;fill:var(--body);font-family:var(--sans)}
.val{font-size:12px;fill:var(--ink);font-weight:620;font-variant-numeric:tabular-nums;font-family:var(--sans)}
.grid-l{stroke:rgba(244,239,230,.06);stroke-width:1}
.base{stroke:rgba(244,239,230,.14);stroke-width:1}
.mark{transition:opacity .15s}
svg:hover .mark{opacity:.45} svg .mark:hover,svg .mark:focus{opacity:1;outline:none}
.hit rect{fill:transparent}
.hit .cross{stroke:rgba(249,176,6,.45);stroke-width:1;opacity:0}
.hit:hover .cross{opacity:1}
.hit circle{opacity:0}.hit:hover circle{opacity:1}

/* horizontal bars */
.bars{padding:10px 22px 22px;display:flex;flex-direction:column;gap:6px}
.bar-row{display:grid;grid-template-columns:var(--lw,120px) 1fr 58px;align-items:center;gap:14px;padding:6px 8px;margin:0 -8px;
  border-radius:10px;transition:background .15s}
.bar-row:hover{background:rgba(244,239,230,.03)}
.bar-label{font-size:13px;color:var(--body);display:flex;align-items:center;gap:8px;min-width:0}
.bar-label span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bar-wrap{background:rgba(244,239,230,.05);border-radius:999px;height:12px}
.bar-track{height:12px;border-radius:999px;display:flex;gap:2px;overflow:hidden}
.bar-track .seg{height:100%;display:block}
.bar-track .seg:last-child{border-radius:0 999px 999px 0}
.bar-track .seg:first-child{border-radius:999px 0 0 999px}
.bar-track .seg:only-child{border-radius:999px}
.bar-count{font-size:13px;color:var(--ink);text-align:right;font-weight:620;font-variant-numeric:tabular-nums}

/* tables */
.tablecard{overflow-x:auto;padding:4px 0 2px}
.table-bar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:6px 22px 12px}
.table-bar .bq{display:flex;align-items:center;gap:8px;padding:7px 12px;border-radius:10px;background:var(--surface);
  border:1px solid var(--line);color:var(--muted);min-width:220px}
.table-bar .bq input{all:unset;flex:1;color:var(--ink);font-size:12.5px}
.table-bar .f{font:inherit;font-size:12px;font-weight:500;color:var(--body);background:var(--surface);border:1px solid var(--line);
  border-radius:8px;padding:5px 11px;cursor:pointer;transition:all .15s}
.table-bar .f b{color:var(--muted);font-weight:600;margin-left:4px}
.table-bar .f:hover{color:var(--ink);border-color:var(--line-2)}
.table-bar .f.on{color:#0E0C09;background:var(--accent);border-color:var(--accent);font-weight:600}
.table-bar .f.on b{color:rgba(14,12,9,.7)}
.table-bar .cnt{margin-left:auto;font-size:12px;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:13.5px;font-variant-numeric:tabular-nums}
thead th{text-align:left;font-family:var(--mono);font-size:11px;text-transform:lowercase;letter-spacing:.02em;color:var(--muted);
  font-weight:500;padding:11px 18px;white-space:nowrap;background:rgba(244,239,230,.025);
  border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
thead th.ord{cursor:pointer;user-select:none}
thead th.ord:hover{color:var(--ink)}
thead th.ord::after{content:"↕";margin-left:6px;opacity:.35;font-size:10px}
thead th.asc::after{content:"↑";opacity:1;color:var(--accent)} thead th.desc::after{content:"↓";opacity:1;color:var(--accent)}
tbody td{padding:13px 18px;border-bottom:1px solid var(--line);color:var(--body);vertical-align:top}
tbody tr:last-child td{border-bottom:0}
tbody tr{transition:background .12s}
tbody tr:hover td{background:rgba(249,176,6,.035)}
tbody tr.hidden{display:none}
td .id,.id{font-family:var(--mono);font-weight:600;color:var(--ink);white-space:nowrap;font-size:12.5px}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;padding:3px 10px;border-radius:999px;white-space:nowrap}

/* verdict banner */
.banner{position:relative;display:flex;align-items:center;gap:16px;padding:20px 24px;border-radius:var(--radius);
  font-weight:600;font-size:16px;letter-spacing:-.01em;color:var(--ink);overflow:hidden;border:1px solid transparent;
  background:linear-gradient(100deg,var(--tint),transparent 55%) padding-box,linear-gradient(180deg,var(--surface-2),var(--surface)) padding-box,
             linear-gradient(90deg,var(--edge),rgba(244,239,230,.05) 60%) border-box}
.banner .bic{width:44px;height:40px;clip-path:polygon(25% 3%,75% 3%,100% 50%,75% 97%,25% 97%,0 50%);display:grid;place-items:center;font-size:18px;font-weight:800;flex:none}
.banner.ok{--tint:rgba(92,191,74,.15);--edge:rgba(92,191,74,.55)} .banner.ok .bic{background:rgba(92,191,74,.18);color:#7BD36A}
.banner.bad{--tint:rgba(255,90,78,.16);--edge:rgba(255,90,78,.6)} .banner.bad .bic{background:rgba(255,90,78,.2);color:#FF7B70}
.banner.warn{--tint:rgba(255,214,10,.12);--edge:rgba(255,214,10,.5)} .banner.warn .bic{background:rgba(255,214,10,.15);color:#FFD60A}

.doclist{list-style:none;display:flex;flex-direction:column;gap:10px}
.doclist li{position:relative;padding-left:22px;color:var(--body)}
.doclist li::before{content:"";position:absolute;left:3px;top:7px;width:11px;height:10px;clip-path:polygon(25% 3%,75% 3%,100% 50%,75% 97%,25% 97%,0 50%);background:var(--accent)}

/* evidence: thumbnails and viewer */
.thumb{position:relative;display:inline-flex;flex-direction:column;width:156px;height:104px;border:1px solid var(--line-2);border-radius:10px;overflow:hidden;
  background:#120F0B;vertical-align:middle;cursor:zoom-in;box-shadow:0 8px 20px -12px rgba(0,0,0,.8);transition:border-color .15s,transform .15s,box-shadow .15s}
/* browser frame: a white page reads as a page, not as a hole */
.thumb::before{content:"";flex:none;height:13px;border-bottom:1px solid rgba(244,239,230,.08);
  background:radial-gradient(circle at 8px 6.5px,#5A5246 2.1px,transparent 2.6px),radial-gradient(circle at 16px 6.5px,#5A5246 2.1px,transparent 2.6px),
             radial-gradient(circle at 24px 6.5px,#5A5246 2.1px,transparent 2.6px),#221E17}
.thumb img{flex:1;min-height:0;width:100%;object-fit:cover;object-position:top left;display:block}
.thumb.small img{object-fit:scale-down;object-position:center;padding:6px;
  background:repeating-conic-gradient(#1A1712 0 25%,#15120E 0 50%) 0 0/14px 14px}
.thumb.s{width:112px;height:76px}
.thumb::after{content:"⤢";position:absolute;right:6px;bottom:6px;width:20px;height:20px;border-radius:6px;display:grid;place-items:center;
  font-size:12px;color:#F4EFE6;background:rgba(14,12,9,.78);opacity:0;transition:opacity .15s}
.thumb:hover{border-color:var(--accent);transform:translateY(-2px);box-shadow:var(--glow-k0)}
.thumb:hover::after{opacity:1}
.thumb.missing,.missing-ev{cursor:help;color:#FFE066;font-size:11px;font-weight:600;text-align:center;line-height:1.3;padding:6px;
  background:repeating-linear-gradient(135deg,rgba(255,214,10,.06) 0 8px,transparent 8px 16px),#120F0B;border-color:rgba(255,214,10,.35)}
.missing-ev{display:inline-flex;align-items:center;border:1px solid rgba(255,214,10,.35);border-radius:10px;padding:6px 10px}
#lb{position:fixed;inset:0;z-index:99;display:none;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:28px;
  background:rgba(10,8,6,.92);backdrop-filter:blur(6px);cursor:zoom-out}
#lb.on{display:flex}
#lb img{max-width:100%;max-height:calc(100% - 50px);border-radius:12px;box-shadow:0 20px 60px rgba(0,0,0,.7);background:#fff}
#lb .foot{display:flex;gap:14px;align-items:center;font-size:12.5px;color:var(--body)}
#lb .foot a{color:var(--ink)}
#lb .msg{display:none;max-width:560px;text-align:center;color:#FFE066;font-size:14px;line-height:1.6;padding:22px 26px;border-radius:14px;
  background:#1A1712;border:1px solid rgba(255,214,10,.35)}
#lb.error img{display:none}#lb.error .msg{display:block}

/* tooltip */
#tip{position:fixed;z-index:50;pointer-events:none;opacity:0;transform:translateY(4px);transition:opacity .12s,transform .12s;
  background:rgba(26,23,18,.97);border:1px solid var(--yellow-line);border-radius:12px;padding:9px 12px;font-size:12.5px;color:var(--ink);
  box-shadow:0 18px 40px rgba(0,0,0,.65);max-width:320px;white-space:pre-line;font-variant-numeric:tabular-nums;backdrop-filter:blur(8px)}
#tip.on{opacity:1;transform:none}

footer{margin-top:40px;display:flex;justify-content:center;gap:8px;font-family:var(--mono);font-size:12px;color:var(--muted);text-transform:lowercase}
footer span::before{content:"// ";color:var(--accent)}

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
  h1{font-size:27px}.search{min-width:0;width:100%}
  .grid>*{grid-column:span 12!important}
}
@media print{.side,.search,.table-bar{display:none}.app{display:block}.card,.kpi{box-shadow:none}#tip{display:none}body::before{display:none}}
"""

# Behavior: tooltips, index with the active section, global search and tables with
# search, filters on the status/severity column and sorting by column.
JS = r"""
(function(){
var t=document.createElement('div');t.id='tip';document.body.appendChild(t);
function show(e){var el=e.target.closest&&e.target.closest('[data-tip]');if(!el){t.className='';return;}
t.textContent=el.getAttribute('data-tip');t.className='on';var r=el.getBoundingClientRect(),x=e.clientX||r.left+r.width/2,y=e.clientY||r.top;
var w=t.offsetWidth,h=t.offsetHeight;t.style.left=Math.max(8,Math.min(x+14,innerWidth-w-8))+'px';t.style.top=(y-h-12<4?y+16:y-h-12)+'px';}
document.addEventListener('mousemove',show);document.addEventListener('focusin',show);
document.addEventListener('mouseleave',function(){t.className='';});

// Evidence viewer: thumbnails (a.lb) are enlarged here; if the file does not exist, a warning is shown.
var lb=document.createElement('div');lb.id='lb';lb.setAttribute('role','dialog');lb.setAttribute('aria-label','Enlarged evidence');
lb.innerHTML='<img alt=""><div class="msg"></div><div class="foot"><span class="name"></span><a target="_blank" rel="noopener">Open in a new tab</a><span>Esc to close</span></div>';
document.body.appendChild(lb);var lbi=lb.querySelector('img'),lbm=lb.querySelector('.msg');
function noFile(path){return 'Evidence not found at '+path+'. Check that the file exists and that the path is relative to the report (the HTML must sit in the same folder as its evidence folder).';}
lbi.addEventListener('error',function(){lb.classList.add('error');lbm.textContent=noFile(lbi.getAttribute('src'));});
document.addEventListener('click',function(ev){var a=ev.target.closest&&ev.target.closest('a.lb');
  if(a){ev.preventDefault();var r=a.getAttribute('href');lb.className='on';lbi.alt=a.title||'';lbi.src=r;
    lb.querySelector('.name').textContent=a.title||r;lb.querySelector('.foot a').href=r;return;}
  if(ev.target.closest&&ev.target.closest('#lb')&&!ev.target.closest('.foot a'))lb.className='';});
document.addEventListener('keydown',function(ev){if(ev.key==='Escape')lb.className='';});
// Images smaller than the thumbnail (a cropped element): shown at their size, not stretched.
// Wide desktop screenshots: the thumbnail focuses on the top left (the first 800 px),
// where the header and content are; the viewer shows the full screenshot.
function measure(im){var a=im.closest&&im.closest('a.thumb');if(!a||!im.naturalWidth)return;
  if(im.naturalWidth<a.clientWidth*1.6&&im.naturalHeight<a.clientHeight*2.5){a.classList.add('small');return;}
  if(im.naturalWidth>1000&&!a.closest('.film')){im.style.flex='none';im.style.maxWidth='none';im.style.height='auto';
    im.style.width=Math.round(a.clientWidth*im.naturalWidth/800)+'px';}}
document.addEventListener('load',function(ev){if(ev.target&&ev.target.tagName==='IMG')measure(ev.target);},true);
[].forEach.call(document.querySelectorAll('a.thumb img'),function(im){if(im.complete)measure(im);});
// Thumbnails whose file does not exist: they are flagged instead of staying blank.
document.addEventListener('error',function(ev){var im=ev.target;if(!im||im.tagName!=='IMG'||!im.closest('a.lb'))return;var a=im.closest('a.lb');
  a.classList.add('missing');a.setAttribute('data-tip',noFile(a.getAttribute('href')));a.textContent='Evidence not found';},true);

// Sidebar index
var nav=document.getElementById('nav'),secs=[].slice.call(document.querySelectorAll('.section[data-nav]'));
if(nav&&secs.length){var tt=document.createElement('div');tt.className='t';tt.textContent='In this report';nav.appendChild(tt);
secs.forEach(function(s){var a=document.createElement('a');a.href='#'+s.id;a.innerHTML='<i></i>';a.appendChild(document.createTextNode(s.getAttribute('data-nav')));nav.appendChild(a);s._a=a;});
if('IntersectionObserver' in window){var vis={};var io=new IntersectionObserver(function(es){es.forEach(function(en){vis[en.target.id]=en.isIntersecting;});
for(var i=0;i<secs.length;i++){if(vis[secs[i].id]){secs.forEach(function(x){x._a.classList.remove('on');});secs[i]._a.classList.add('on');
if(nav.scrollWidth>nav.clientWidth)secs[i]._a.scrollIntoView({block:'nearest',inline:'nearest'});break;}}},{rootMargin:'-10% 0px -60% 0px'});
secs.forEach(function(s){io.observe(s);});}}

// Tables: search, filters and sorting
var FILTER=['group','severity','status','diagnosis','type','probable cause','likely cause','category','result','risk','priority','device','level','coverage','browser'];
var tables=[].slice.call(document.querySelectorAll('.tablecard table'));
function text(c){return (c.innerText||c.textContent||'').trim();}
tables.forEach(function(tb){
  var rows=[].slice.call(tb.tBodies[0]?tb.tBodies[0].rows:[]),ths=[].slice.call(tb.tHead?tb.tHead.rows[0].cells:[]);
  ths.forEach(function(th,i){th.classList.add('ord');th.addEventListener('click',function(){
    var asc=!th.classList.contains('asc');ths.forEach(function(x){x.classList.remove('asc','desc');});th.classList.add(asc?'asc':'desc');
    var tbody=tb.tBodies[0],fs=[].slice.call(tbody.rows);
    fs.sort(function(a,b){var x=text(a.cells[i]||a),y=text(b.cells[i]||b),nx=parseFloat(x.replace(/[^\d.-]/g,'')),ny=parseFloat(y.replace(/[^\d.-]/g,''));
      var r=(!isNaN(nx)&&!isNaN(ny)&&/^\s*[\d.,-]/.test(x)&&/^\s*[\d.,-]/.test(y))?nx-ny:x.localeCompare(y,'en',{numeric:true});return asc?r:-r;});
    fs.forEach(function(f){tbody.appendChild(f);});});});
  if(rows.length<6)return;
  var col=-1;ths.forEach(function(th,i){if(col<0&&FILTER.indexOf(text(th).toLowerCase())>=0)col=i;});
  var bar=document.createElement('div');bar.className='table-bar';
  bar.innerHTML='<label class="bq"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M16.5 16.5L21 21"/></svg><input type="search" placeholder="Search the table…"></label>';
  var active=null,q='';
  if(col>=0){var count={};rows.forEach(function(f){var v=text(f.cells[col]||f).replace(/^[^\wÁÉÍÓÚáéíóúÑñ]+/,'').split('\n')[0];if(v)count[v]=(count[v]||0)+1;});
    var keys=Object.keys(count);if(keys.length>1&&keys.length<=8){
      var all=document.createElement('button');all.className='f on';all.innerHTML='All<b>'+rows.length+'</b>';bar.appendChild(all);
      keys.forEach(function(k){var b=document.createElement('button');b.className='f';b.innerHTML=k+'<b>'+count[k]+'</b>';b._v=k;bar.appendChild(b);});
      bar.addEventListener('click',function(ev){var b=ev.target.closest('.f');if(!b)return;[].forEach.call(bar.querySelectorAll('.f'),function(x){x.classList.remove('on');});
        b.classList.add('on');active=b._v||null;apply();});}}
  var cnt=document.createElement('span');cnt.className='cnt';bar.appendChild(cnt);
  function apply(){var n=0;rows.forEach(function(f){var ok=(!q||text(f).toLowerCase().indexOf(q)>=0)&&(!active||text(f.cells[col]||f).indexOf(active)>=0);
    f.classList.toggle('hidden',!ok);if(ok)n++;});cnt.textContent=n+' of '+rows.length+' rows';}
  bar.querySelector('input').addEventListener('input',function(e){q=e.target.value.trim().toLowerCase();apply();});
  var tc=tb.closest('.tablecard');tc.parentNode.insertBefore(bar,tc);apply();tb._apply=function(v){q=v;bar.querySelector('input').value=v;apply();};
});

// Global search: filters every table (Ctrl+K or /)
var gb=document.getElementById('search');
if(gb){gb.addEventListener('input',function(){var v=gb.value.trim().toLowerCase();tables.forEach(function(tb){if(tb._apply)tb._apply(v);
  else [].forEach.call(tb.tBodies[0]?tb.tBodies[0].rows:[],function(f){f.classList.toggle('hidden',v&&text(f).toLowerCase().indexOf(v)<0);});});});
  document.addEventListener('keydown',function(e){if((e.key==='k'&&(e.ctrlKey||e.metaKey))||(e.key==='/'&&document.activeElement.tagName!=='INPUT')){e.preventDefault();gb.focus();}});}
})();
"""


def e(s):
    return html.escape(str(s if s is not None else ""))


def _slug(text):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower().translate(str.maketrans("áéíóúñü", "aeiounu"))).strip("-")
    return s or "section"


_IDS = {}


def _unique_id(title):
    base = "s-" + _slug(title)
    n = _IDS.get(base, 0)
    _IDS[base] = n + 1
    return base if n == 0 else f"{base}-{n + 1}"


def page(title, eyebrow, meta_html, body):
    _IDS.clear()
    try:  # when the process ends, the reports portal (output/index.html) picks up this report
        import reports_portal
        reports_portal.schedule()
    except Exception:
        pass
    return (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="color-scheme" content="dark">'
            f'<title>{e(title)} — k0lmenIA</title><style>{FONTS}{CSS}</style></head>'
            f'<body><div class="app"><aside class="side">'
            f'<div class="logo"><span class="mk">k0</span><div><b>K0LMENIA</b><span>{e(eyebrow)}</span></div></div>'
            f'<nav class="nav" id="nav" aria-label="Report sections"></nav>'
            f'<div class="side-foot">Generated by k0lmenIA · part of the <a href="https://k0lmena.com">k0lmena</a> suite · self-contained report, no internet needed</div></aside>'
            f'<main class="main"><div class="wrap"><header class="top"><div>'
            f'<span class="eyebrow">{e(eyebrow)}</span><h1>{e(title)}</h1>{meta_html}</div>'
            f'<label class="search"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
            f'<circle cx="11" cy="11" r="7"/><path d="M16.5 16.5L21 21"/></svg>'
            f'<input id="search" type="search" placeholder="Search the tables…" aria-label="Search the tables"><kbd>Ctrl K</kbd></label>'
            f'</header><div class="grid">{body}</div>'
            f'<footer><span>Generated by k0lmenIA</span></footer></div></main></div>'
            f'<script>{JS}</script></body></html>\n')


def meta(items):
    """items: list of (key, value); skips empty values."""
    parts = [f'<span class="chip"><span class="k">{e(k)}</span> {e(v)}</span>' for k, v in items if v]
    return f'<div class="meta">{"".join(parts)}</div>' if parts else ""


def section(title, body_html, sub="", width=12):
    """Grid card with its title inside. width: columns out of 12 (12, 8, 6, 4)."""
    s = f'<span class="sub">{e(sub)}</span>' if sub else ""
    style = f' style="grid-column:span {width}"' if width != 12 else ""
    return (f'<section class="section" id="{_unique_id(title)}" data-nav="{e(title)}"{style}><div class="card">'
            f'<div class="section-title"><h2>{e(title)}</h2>{s}</div>{body_html}</div></section>')


def section_group(title, body_html, sub=""):
    s = f'<span class="sub">{e(sub)}</span>' if sub else ""
    return (f'<section class="section" id="{_unique_id(title)}" data-nav="{e(title)}"><div class="group-title"><h2>{e(title)}</h2>{s}</div>'
            f'<div class="subgrid">{body_html}</div></section>')


TONE_ICON = {"ok": "✓", "bad": "✕", "warn": "!", "blk": "⊘"}
TONE_TEXT = {"ok": "OK", "bad": "Critical", "warn": "Review", "blk": "Neutral"}

# Icon for each indicator based on its label (the first match wins).
ICON_BY_LABEL = [
    ("risk", "shield"), ("informational", "search"), ("passed", "ok"), ("failed", "bad"), ("blocked", "blk"),
    ("js error", "code"), ("error %", "warn"), ("% error", "warn"), ("error", "warn"), ("resource", "code"), ("link", "link"),
    ("image", "image"), ("responsive", "screen"), ("keyboard", "keyboard"), ("page", "page"),
    ("compliance", "target"), ("threshold", "target"), ("target", "target"), ("criteri", "list"),
    ("p95", "clock"), ("latency", "clock"), ("average load", "clock"), ("avg load", "clock"), ("duration", "clock"),
    ("req/s", "bolt"), ("request", "load"), ("user", "person"), ("manual", "person"),
    ("review", "search"), ("finding", "search"), ("assumption", "search"), ("question", "search"), ("bug", "bug"),
    ("case", "list"), ("run", "list"), ("total", "list"), ("types", "grid"), ("element", "grid"),
]


def _icon_for(label, tone):
    low = (label or "").lower()
    for key, name in ICON_BY_LABEL:
        if key in low:
            return name
    return tone if tone in TONE_ICON else "grid"


def sparkline(values, color=ACCENT, width=160, height=30):
    """Mini line with area for an indicator (no axes)."""
    vs = [v for v in values if v is not None]
    if len(vs) < 2:
        return ""
    lo, hi = min(vs), max(vs)
    rng = (hi - lo) or 1
    pts = [(i / (len(vs) - 1) * width, height - 3 - (v - lo) / rng * (height - 6)) for i, v in enumerate(vs)]
    d = _curve(pts)
    _GRAD[0] += 1
    gid = f"sp{_GRAD[0]}"
    return (f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none"><defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{color}" stop-opacity=".35"/><stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>'
            f'<path d="{d} L{width},{height} L0,{height} Z" fill="url(#{gid})"/>'
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" vector-effect="non-scaling-stroke"/></svg>')


def kpi_tiles(items):
    """items: (label, value, tone[, detail[, icon[, extra]]]). tone: '' | 'ok' | 'bad' | 'blk' | 'warn'.
    icon: a name from ICONS; if missing, it is picked from the label. extra: {"pct": n} adds a progress
    bar and {"series": [...]} a sparkline. The tone colors the icon and is also shown as a label with
    symbol and text in the corner: status never depends on color alone."""
    out = ""
    for it in items:
        label, val, tone = it[0], it[1], it[2]
        detail = it[3] if len(it) > 3 else ""
        ic = it[4] if len(it) > 4 and it[4] else _icon_for(label, tone)
        extra = it[5] if len(it) > 5 and it[5] else {}
        st = f'<span class="st">{TONE_ICON[tone]} {TONE_TEXT[tone]}</span>' if tone in TONE_ICON else ""
        d = f'<div class="d">{e(detail)}</div>' if detail else ""
        adornment = ""
        if extra.get("pct") is not None:
            adornment = f'<div class="bar"><span style="width:{max(0, min(100, extra["pct"])):.0f}%"></span></div>'
        elif extra.get("series"):
            adornment = f'<div class="spark">{sparkline(extra["series"])}</div>'
        out += (f'<div class="kpi {tone}"><div class="ic">{icon(ic)}</div>{st}'
                f'<div class="l">{e(label)}</div><div class="n">{e(val)}</div>{d}{adornment}</div>')
    n = len(items)
    cols = n if n <= 6 else math.ceil(n / 2)  # 7 or 8 in two even rows, never 6 + 2
    return f'<div class="kpis" style="--cols:{cols}">{out}</div>'


def legend(items):
    """items: (name, color[, value])."""
    parts = []
    for it in items:
        value = f' <b>{e(it[2])}</b>' if len(it) > 2 else ""
        parts.append(f'<span><i style="background:{it[1]}"></i>{e(it[0])}{value}</span>')
    return f'<div class="legend">{"".join(parts)}</div>'


def banner(text, tone="ok"):
    return f'<div class="banner {tone}"><span class="bic">{TONE_ICON.get(tone, "i")}</span>{e(text)}</div>'


def doc_list(items):
    if not items:
        return '<div class="cardbody"><p class="muted">—</p></div>'
    lis = "".join(f'<li>{e(it)}</li>' for it in items)
    return f'<div class="cardbody"><ul class="doclist">{lis}</ul></div>'


def two_col(left, right):
    return f'<div class="twocol">{left}{right}</div>'


def table(headers, rows):
    """headers: list of strings. rows: list of lists; each cell may contain HTML."""
    th = "".join(f'<th>{e(h)}</th>' for h in headers)
    trs = "".join("<tr>" + "".join(f'<td>{c}</td>' for c in row) + "</tr>" for row in rows)
    return f'<div class="tablecard"><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'


def missing_info(items, sub=""):
    """"Missing information" section of the reports: {id, what_is_missing, question} ("description" works as an alias of what_is_missing)."""
    rows = [[e(f.get("id")), e(f.get("what_is_missing") or f.get("description")), e(f.get("question") or "—")]
            for f in items or [] if isinstance(f, dict)]
    return section("Missing information", table(["ID", "What is missing", "Question for the PO"], rows), sub) if rows else ""


VALID_SEVERITIES = ("Critical", "High", "Medium", "Low")


def warn_analysis(analysis, ids):
    """Warns on stderr (without stopping the report) about what the script would silently ignore: IDs in notes,
    severities, findings and discarded that are not in the data, and severities off the scale. Returns the warnings."""
    ids = {str(i) for i in ids}
    cited = [(c, str(k)) for c in ("notes", "severities", "findings") if isinstance(analysis.get(c), dict) for k in analysis[c]]
    cited += [("discarded", str(d.get("id"))) for d in analysis.get("discarded") or [] if isinstance(d, dict)]
    sevs = list((analysis.get("severities") or {}).values()) if isinstance(analysis.get("severities"), dict) else []
    sevs += [x["severity"] for x in (analysis.get("findings") or {}).values() if isinstance(x, dict) and x.get("severity")]         if isinstance(analysis.get("findings"), dict) else []
    warnings = [f"{c}: {i} is not in the data (ignored)" for c, i in cited if i not in ids]
    warnings += [f"severity {s!r} off the scale {'/'.join(VALID_SEVERITIES)} (ignored)" for s in sevs if s not in VALID_SEVERITIES]
    for a in warnings:
        print(f"[warning] analysis.json · {a}", file=sys.stderr)
    return warnings


def resolve_evidence(path, html_dir, root=None):
    """(path relative to the HTML, exists). Accepts the path relative to the report (the right way), relative
    to the repo root (output/runs/evidence/x.png) or absolute, and returns it relative to the HTML."""
    if not path:
        return None, False
    if re.match(r"^(https?:|data:)", str(path)):
        return path, True
    html_dir = Path(html_dir).resolve()
    root = Path(root).resolve() if root else Path(__file__).resolve().parents[1]
    p = Path(str(path).replace("\\", "/"))
    for cand in ([p] if p.is_absolute() else [html_dir / p, root / p, Path.cwd() / p]):
        if cand.exists():
            try:
                return Path(os.path.relpath(cand.resolve(), html_dir)).as_posix(), True
            except ValueError:  # a different drive on Windows: absolute path as a file URL
                return cand.resolve().as_uri(), True
    return str(path).replace("\\", "/"), False


def thumbnail(path, title="", css_class="", exists=True):
    """Thumbnail that is enlarged in the viewer. With exists=False (the file is not there) it shows the warning."""
    if not path:
        return '<span class="muted">—</span>'
    if not exists:
        return (f'<span class="missing-ev" data-tip="Evidence not found at {e(path)}" tabindex="0">'
                f'! Evidence not found</span>')
    return (f'<a class="lb thumb {css_class}" href="{e(path)}" title="{e(title)}">'
            f'<img src="{e(path)}" loading="lazy" alt="{e(title or "Evidence")}"></a>')


def _pill(text, color, icon_txt):
    return (f'<span class="pill" style="background:{_soft(color, .13)};color:var(--ink);box-shadow:inset 0 0 0 1px {_soft(color, .34)}">'
            f'<span style="color:{color}">{icon_txt}</span>{e(text)}</span>')


def level_badge(level):
    n = (level or "").strip()
    return _pill(n or "—", LEVEL_COLOR.get(n, NEUTRAL), LEVEL_ICON.get(n, "●"))


def status_pill(status):
    s = (status or "").strip()
    return _pill(s or "—", STATUS_COLOR.get(s, NEUTRAL), STATUS_ICON.get(s, "●"))


# ------------------------------------------------------------------ charts
_GRAD = [0]


def _num(v, fmt=None):
    if v is None:
        return "—"
    if fmt:
        return fmt(v)
    if float(v).is_integer():
        return f"{v:,.0f}"
    return f"{v:,.2f}".rstrip("0").rstrip(".")


def _scale(maxv):
    """A "round" maximum and step for 4-5 grid lines."""
    if maxv <= 0:
        return 1, 0.25
    exp = 10 ** math.floor(math.log10(maxv))
    for m in (1, 2, 2.5, 5, 10):
        step = m * exp / 4
        if step * 4 >= maxv:
            return step * 4, step
    return maxv, maxv / 4


def _gradient(color, vertical=True):
    """Id of a gradient of the color (light at top/right -> the color at bottom/left) and its <defs>."""
    _GRAD[0] += 1
    gid = f"g{_GRAD[0]}"
    x2, y2 = ("0", "1") if vertical else ("1", "0")
    return gid, (f'<linearGradient id="{gid}" x1="0" y1="0" x2="{x2}" y2="{y2}">'
                 f'<stop offset="0" stop-color="{_lighten(color, .18) if vertical else color}"/>'
                 f'<stop offset="1" stop-color="{color if vertical else _lighten(color, .18)}" stop-opacity="{.55 if vertical else 1}"/></linearGradient>')


def _vertical_bar(x, y_base, width, height, color, tip, fill=None):
    """Column with the data end rounded and a straight base."""
    r = min(6, width / 2, height)
    if height <= 0:
        return ""
    y = y_base - height
    d = (f"M{x:.1f},{y_base:.1f} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} "
         f"H{x + width - r:.1f} Q{x + width:.1f},{y:.1f} {x + width:.1f},{y + r:.1f} V{y_base:.1f} Z")
    return f'<path class="mark" d="{d}" fill="{fill or color}" data-tip="{e(tip)}" tabindex="0"/>'


def _grid_y(W, left, right, y_of, maxv, step, fmt):
    out, i = [], 0
    while i * step <= maxv + 1e-9:
        y = y_of(i * step)
        out.append(f'<line class="{"base" if i == 0 else "grid-l"}" x1="{left}" x2="{W - right}" y1="{y:.1f}" y2="{y:.1f}"/>'
                   f'<text class="axis" x="{left - 10}" y="{y + 4:.1f}" text-anchor="end">{e(_num(i * step, fmt))}</text>')
        i += 1
    return out


def donut(segments, pct, label="passed"):
    """segments: [(value, color[, name])]. The center shows pct + label."""
    r, cx, cy, w = 74, 100, 100, 18
    C = 2 * math.pi * r
    total = sum(s[0] for s in segments) or 1
    track = (f'<circle cx="{cx}" cy="{cy}" r="{r + 15}" fill="rgba(244,239,230,.015)"/>'
             f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="rgba(244,239,230,.05)" stroke-width="{w}"/>')
    segs, acc = "", 0.0
    gap = 4 if sum(1 for s in segments if s[0]) > 1 else 0
    for s in segments:
        value, color = s[0], s[1]
        if not value:
            continue
        name = s[2] if len(s) > 2 else ""
        frac = value / total
        dash = max(frac * C - gap, 0.1)
        tip = f"{name}: {value} ({frac * 100:.0f}%)" if name else f"{value} ({frac * 100:.0f}%)"
        segs += (f'<circle class="mark" cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="{w}" '
                 f'stroke-dasharray="{dash:.2f} {C - dash:.2f}" stroke-dashoffset="{-acc * C:.2f}" '
                 f'transform="rotate(-90 {cx} {cy})" data-tip="{e(tip)}" tabindex="0"/>')
        acc += frac
    return (f'<svg viewBox="0 0 200 200" width="200" height="200" role="img" '
            f'aria-label="{pct} percent {e(label)}">{track}{segs}'
            f'<text x="{cx}" y="{cy + 7}" text-anchor="middle" class="donut-num">{pct}%</text>'
            f'<text x="{cx}" y="{cy + 29}" text-anchor="middle" class="donut-lbl">{e(label)}</text></svg>')


def donut_panel(segments, pct, label):
    """Donut + legend in rows (name, value, % and proportion bar), to use as the body of section()."""
    total = sum(s[0] for s in segments) or 1
    rows = "".join(f'<div class="r"><i style="background:{s[1]}"></i><span>{e(s[2] if len(s) > 2 else "")}</span>'
                    f'<b>{e(_num(s[0]))}</b><em>{s[0] / total * 100:.0f}%</em>'
                    f'<div class="p"><span style="width:{s[0] / total * 100:.1f}%;background:{s[1]}"></span></div></div>' for s in segments)
    return f'<div class="panorama"><div class="gauge">{donut(segments, pct, label)}</div><div class="dleg">{rows}</div></div>'


def gauge(pct, label="", tone=None, size=220):
    """Semicircular 0-100 gauge (scores). tone: ok | warn | bad (if missing, based on the value)."""
    pct = max(0, min(100, pct or 0))
    color = {"ok": OK, "warn": WARNING, "bad": CRITICAL}.get(tone) or (OK if pct >= 90 else WARNING if pct >= 50 else CRITICAL)
    r, cx, cy, w = size / 2 - 16, size / 2, size / 2, 16
    length = math.pi * r
    arc = f"M{cx - r:.1f},{cy:.1f} A{r:.1f},{r:.1f} 0 0 1 {cx + r:.1f},{cy:.1f}"
    _GRAD[0] += 1
    gid = f"ga{_GRAD[0]}"
    return (f'<svg viewBox="0 0 {size} {size / 2 + 34}" width="{size}" role="img" aria-label="{pct:.0f} out of 100 {e(label)}">'
            f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{color}" stop-opacity=".55"/>'
            f'<stop offset="1" stop-color="{_lighten(color, .15)}"/></linearGradient></defs>'
            f'<path d="{arc}" fill="none" stroke="rgba(244,239,230,.06)" stroke-width="{w}" stroke-linecap="round"/>'
            f'<path d="{arc}" fill="none" stroke="url(#{gid})" stroke-width="{w}" stroke-linecap="round" '
            f'stroke-dasharray="{length * pct / 100:.1f} {length:.1f}"/>'
            f'<text x="{cx}" y="{cy - 6}" text-anchor="middle" class="donut-num">{pct:.0f}</text>'
            f'<text x="{cx}" y="{cy + 22}" text-anchor="middle" class="donut-lbl">{e(label)}</text></svg>')


def bar_chart(rows, label_width=120):
    """rows: [(label, value, color)]. Horizontal bars with a gradient, normalized to the maximum,
    on a faint rail; value at the end. label_width: width of the label column in px."""
    rows = list(rows)
    maxv = max((c for _, c, _ in rows), default=0)
    if not rows or maxv == 0:
        return '<div class="cardbody"><p class="muted">No data.</p></div>'
    out = ""
    for label, count, color in rows:
        width = count / maxv * 100
        seg = (f'<span class="seg" style="width:100%;background:linear-gradient(90deg,{_soft(color, .55)},{color} 70%,{_lighten(color, .2)});'
               f'box-shadow:0 0 14px -2px {_soft(color, .55)}"></span>') if count else ""
        out += (f'<div class="bar-row" data-tip="{e(label)}: {e(_num(count))}" tabindex="0"><div class="bar-label"><span>{e(label)}</span></div>'
                f'<div class="bar-wrap"><div class="bar-track" style="width:{max(width, 1.2 if count else 0):.1f}%">{seg}</div></div>'
                f'<div class="bar-count">{e(_num(count))}</div></div>')
    return f'<div class="bars" style="--lw:{label_width}px">{out}</div>'


def column_chart(rows, fmt=None, height=280, width=1320):
    """rows: [(label, value[, color])]. Single-series vertical columns (teal by default) with a
    gradient on a faint rail and the value above the top. Up to ~12 categories."""
    rows = [r for r in rows if r[1] is not None]
    if not rows or max(r[1] for r in rows) <= 0:
        return '<div class="cardbody"><p class="muted">No data.</p></div>'
    W, H, left, right, top, bottom = width, height, 52, 10, 28, 40
    maxv, step = _scale(max(r[1] for r in rows))
    ph = H - top - bottom
    y0 = top + ph
    svg = _grid_y(W, left, right, lambda v: y0 - ph * v / maxv, maxv, step, fmt)
    defs = []
    band = (W - left - right) / len(rows)
    col = min(48, band * 0.56)
    for k, r in enumerate(rows):
        label, v = r[0], r[1]
        color = r[2] if len(r) > 2 and r[2] else SERIES[0]
        gid, dg = _gradient(color)
        defs.append(dg)
        x = left + k * band + (band - col) / 2
        h = ph * v / maxv
        svg.append(f'<rect x="{x:.1f}" y="{top}" width="{col:.1f}" height="{ph}" rx="6" fill="rgba(244,239,230,.025)"/>')
        svg.append(_vertical_bar(x, y0, col, h, color, f"{label}: {_num(v, fmt)}", f"url(#{gid})"))
        svg.append(f'<text class="val" x="{x + col / 2:.1f}" y="{y0 - h - 9:.1f}" text-anchor="middle">{e(_num(v, fmt))}</text>')
        short = label if len(label) * 6.4 <= band else label[:max(int(band / 6.4) - 1, 3)] + "…"
        svg.append(f'<text class="lbl" x="{left + k * band + band / 2:.1f}" y="{H - 14}" text-anchor="middle">{e(short)}<title>{e(label)}</title></text>')
    return f'<div class="chart"><svg viewBox="0 0 {W} {H}" role="img"><defs>{"".join(defs)}</defs>{"".join(svg)}</svg></div>'


def stacked_bars(rows, series):
    """rows: [(label, [value per series])]; series: [(name, color)]. Stacked horizontal bars,
    with 2px between segments and length proportional to the total."""
    rows = [f for f in rows if sum(f[1])]
    if not rows:
        return '<div class="cardbody"><p class="muted">No data.</p></div>'
    maxt = max(sum(v) for _, v in rows)
    out = ""
    for label, values in rows:
        tot = sum(values)
        segs = "".join(f'<span class="seg" style="width:{v / tot * 100:.2f}%;background:{c}" '
                       f'data-tip="{e(label)} · {e(n)}: {v} ({v / tot * 100:.0f}%)"></span>'
                       for v, (n, c) in zip(values, series) if v)
        out += (f'<div class="bar-row"><div class="bar-label"><span>{e(label)}</span></div>'
                f'<div class="bar-wrap"><div class="bar-track" style="width:{tot / maxt * 100:.1f}%">{segs}</div></div>'
                f'<div class="bar-count">{tot}</div></div>')
    return f'<div class="bars">{out}<div style="margin-top:10px">{legend(series) if len(series) > 1 else ""}</div></div>'


def grouped_columns(groups, series, fmt=None, height=300, width=1320):
    """groups: X-axis labels; series: [(name, color, [value per group])]. A single Y axis.
    width: canvas in px (1320 for full width; 660 in a two-column grid, so the text keeps its size)."""
    values = [v for _, _, vs in series for v in vs if v is not None]
    if not values:
        return '<div class="cardbody"><p class="muted">No data.</p></div>'
    W, H, left, right, top, bottom = width, height, 58, 8, 24, 40
    maxv, step = _scale(max(values))
    ph = H - top - bottom
    y0 = top + ph
    svg = _grid_y(W, left, right, lambda v: y0 - ph * v / maxv, maxv, step, fmt)
    defs, fills = [], {}
    for _, color, _ in series:
        gid, dg = _gradient(color)
        defs.append(dg)
        fills[color] = f"url(#{gid})"
    group_width = (W - left - right) / len(groups)
    col = min(30, (group_width * 0.7 - 3 * (len(series) - 1)) / len(series))
    for g, name in enumerate(groups):
        x0 = left + g * group_width + (group_width - (col * len(series) + 3 * (len(series) - 1))) / 2
        svg.append(f'<rect x="{x0 - 8:.1f}" y="{top}" width="{col * len(series) + 3 * (len(series) - 1) + 16:.1f}" height="{ph}" rx="8" fill="rgba(244,239,230,.02)"/>')
        for s, (sn, color, vs) in enumerate(series):
            v = vs[g]
            if v is None:
                continue
            svg.append(_vertical_bar(x0 + s * (col + 3), y0, col, ph * v / maxv, color, f"{name} · {sn}: {_num(v, fmt)}", fills[color]))
        short = name if len(name) * 6.6 <= group_width else name[:max(int(group_width / 6.6) - 1, 3)] + "…"
        svg.append(f'<text class="lbl" x="{left + g * group_width + group_width / 2:.1f}" y="{H - 14}" text-anchor="middle">'
                   f'{e(short)}<title>{e(name)}</title></text>')
    if len(series) == 1:  # a single series: the value above each column (there are few)
        for g, v in enumerate(series[0][2]):
            if v is not None and len(groups) <= 12:
                x = left + g * group_width + group_width / 2
                svg.append(f'<text class="val" x="{x:.1f}" y="{y0 - ph * v / maxv - 9:.1f}" text-anchor="middle">{e(_num(v, fmt))}</text>')
    leg = legend([(n, c) for n, c, _ in series]) if len(series) > 1 else ""
    return f'<div class="chart"><svg viewBox="0 0 {W} {H}" role="img"><defs>{"".join(defs)}</defs>{"".join(svg)}</svg>{leg}</div>'


def _curve(pts):
    """Smooth monotone curve (Fritsch–Carlson) through the points: it never overshoots the real values."""
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


def line_chart(x, series, fmt=None, fmt_x=None, height=300, area=None, width=1320):
    """x: X-axis values (numbers); series: [(name, color, [value per x])]. A single Y axis,
    smooth 2px glowing curves, gradient area (by default, if there is a single series), points
    and labels at the maximum and the last value, and a crosshair with the value of every series."""
    if len(x) < 2 or not any(v is not None for _, _, vs in series for v in vs):
        return '<p class="muted" style="padding:16px 24px">Not enough data for the trend.</p>'
    if area is None:
        area = len(series) == 1
    W, H, left, right, top, bottom = width, height, 58, 18, 26, 30
    values = [v for _, _, vs in series for v in vs if v is not None]
    maxv, step = _scale(max(values))
    ph, pw = H - top - bottom, W - left - right
    x0, x1 = x[0], x[-1]
    rx = (x1 - x0) or 1
    px = lambda xv: left + (xv - x0) / rx * pw
    py = lambda v: top + ph - ph * v / maxv
    svg = _grid_y(W, left, right, py, maxv, step, fmt)
    # Few points (for example, runs): one tick per point; otherwise, five even ticks.
    ticks = list(x) if len(x) <= 8 else [x0, x0 + rx / 4, x0 + rx / 2, x0 + 3 * rx / 4, x1]
    for xv in ticks:
        anchor = "start" if xv == x0 else "end" if xv == x1 else "middle"  # the ends are not cut off
        svg.append(f'<text class="axis" x="{px(xv):.1f}" y="{H - 8}" text-anchor="{anchor}">{e(fmt_x(xv) if fmt_x else _num(xv))}</text>')
    defs = []
    for name, color, vs in series:
        pts = [(px(xv), py(v)) for xv, v in zip(x, vs) if v is not None]
        if not pts:
            continue
        d = _curve(pts)
        if area:
            _GRAD[0] += 1
            gid = f"g{_GRAD[0]}"
            defs.append(f'<linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
                        f'<stop offset="0" stop-color="{color}" stop-opacity=".38"/><stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient>')
            svg.append(f'<path d="{d} L{pts[-1][0]:.1f},{py(0):.1f} L{pts[0][0]:.1f},{py(0):.1f} Z" fill="url(#{gid})"/>')
        svg.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="6" stroke-opacity=".14" stroke-linejoin="round" stroke-linecap="round"/>')
        svg.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>')
        if len(pts) <= 40:
            svg += [f'<circle cx="{a:.1f}" cy="{b:.1f}" r="3.2" fill="{SURFACE}" stroke="{color}" stroke-width="2"/>' for a, b in pts]
        real = [(xv, v) for xv, v in zip(x, vs) if v is not None]
        imax = max(range(len(real)), key=lambda k: real[k][1])
        for k in sorted({imax, len(real) - 1} if len(series) == 1 else {len(real) - 1}):
            xv, v = real[k]
            anchor = "start" if xv == x0 else "end" if xv == x1 else "middle"
            svg.append(f'<text class="val" x="{px(xv):.1f}" y="{py(v) - 11:.1f}" text-anchor="{anchor}">{e(_num(v, fmt))}</text>')
    for k, xv in enumerate(x):
        leftz = px(x[k - 1]) if k else px(xv)
        rightz = px(x[k + 1]) if k < len(x) - 1 else px(xv)
        a, b = (leftz + px(xv)) / 2, (px(xv) + rightz) / 2
        tip = (fmt_x(xv) if fmt_x else _num(xv)) + "\n" + "\n".join(
            f"{n}: {_num(vs[k], fmt)}" for n, _, vs in series if vs[k] is not None)
        points = "".join(f'<circle cx="{px(xv):.1f}" cy="{py(vs[k]):.1f}" r="5.5" fill="{c}" stroke="{SURFACE}" stroke-width="2"/>'
                         for _, c, vs in series if vs[k] is not None)
        svg.append(f'<g class="hit" data-tip="{e(tip)}"><rect x="{a:.1f}" y="{top}" width="{max(b - a, 1):.1f}" height="{ph}"/>'
                   f'<line class="cross" x1="{px(xv):.1f}" x2="{px(xv):.1f}" y1="{top}" y2="{top + ph}"/>{points}</g>')
    leg = legend([(n, c) for n, c, _ in series]) if len(series) > 1 else ""
    return f'<svg viewBox="0 0 {W} {H}" role="img"><defs>{"".join(defs)}</defs>{"".join(svg)}</svg>{leg}'
