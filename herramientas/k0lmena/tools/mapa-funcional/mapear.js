// Mapa funcional de un sitio web (agente documentador-proyecto).
//
// Uso (desde la raíz del repo):
//   npm run mapa-funcional -- [--url https://mi-app.com] [--paginas url1,url2] [--max-paginas 30]
//                             [--profundidad 2] [--pausa-ms 300] [--salida <carpeta>] [--headed]
//
// Recorre las páginas del mismo host a partir de la URL (por defecto APP_URL del .env, o BASEURL) y
// documenta qué hay en cada una, para que los agentes que escriben casos conozcan la aplicación real:
//   título y encabezados · menús de navegación (los que se repiten en todo el sitio van una sola vez)
//   · formularios con cada campo (etiqueta, tipo, obligatorio, largos, mínimos y máximos, patrón,
//   opciones de las listas) · botones · mensajes visibles (alertas, errores, avisos) · encabezados de
//   tablas · un extracto del texto principal.
//
// Es documentación, no una prueba: no saca capturas ni busca errores (eso es npm run explorar).
// Solo navega con GET: no completa ni envía formularios (toda navegación que no sea GET se corta) y
// no sigue links de cierre de sesión ni de borrado. Cubre las páginas públicas (sin login).
//
// Deja en input/documentacion/proyecto/ (o --salida) mapa-funcional.json y mapa-funcional.md; cada
// corrida reemplaza a la anterior.
const fs = require('fs');
const path = require('path');
const { normalizar, recorrerScroll, cargar } = require('../explorador/explorar.js');
const { descubrir } = require('../pixel-perfect/pixel-perfect.js');
const { extraerFormularios } = require('../formularios/formularios.js');

const RAIZ = path.resolve(__dirname, '..', '..', '..', '..');
const desde = (p) => path.resolve(process.env.INIT_CWD || process.cwd(), p);
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

function argumentos(argv) {
  const a = { maxPaginas: 30, profundidad: 2, pausaMs: 300, headed: false };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    const v = () => argv[++i];
    if (k === '--url') a.url = v();
    else if (k === '--paginas') a.paginas = v().split(',').map((x) => x.trim()).filter(Boolean);
    else if (k === '--max-paginas') a.maxPaginas = parseInt(v(), 10);
    else if (k === '--profundidad') a.profundidad = parseInt(v(), 10);
    else if (k === '--pausa-ms') a.pausaMs = parseInt(v(), 10);
    else if (k === '--salida') a.salida = v();
    else if (k === '--headed') a.headed = true;
    else if (k === '-h' || k === '--help') a.ayuda = true;
    else throw new Error(`Opción desconocida: ${k}`);
  }
  if (!(a.maxPaginas >= 1 && a.maxPaginas <= 200)) throw new Error('--max-paginas tiene que estar entre 1 y 200.');
  if (!(a.profundidad >= 0 && a.profundidad <= 5)) throw new Error('--profundidad tiene que estar entre 0 y 5.');
  return a;
}

// Corre en el navegador: lo visible de la página, sin los formularios (los extrae extraerFormularios).
function _contenido() {
  const visible = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const texto = (el) => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  const unicos = (xs) => [...new Set(xs.filter(Boolean))];
  const encabezados = [...document.querySelectorAll('h1, h2, h3')].filter(visible)
    .map((h) => ({ nivel: Number(h.tagName[1]), texto: texto(h).slice(0, 120) })).filter((h) => h.texto).slice(0, 40);
  const menus = [...document.querySelectorAll('nav, [role=navigation], header [role=menubar], aside [role=menu]')].filter(visible).map((n) => ({
    nombre: n.getAttribute('aria-label') || (n.closest('header') ? 'Encabezado' : n.closest('footer') ? 'Pie' : n.closest('aside') ? 'Lateral' : 'Navegación'),
    items: unicos([...n.querySelectorAll('a[href], button, [role=menuitem]')].filter(visible).map((x) => texto(x).slice(0, 60))).slice(0, 40),
  })).filter((m) => m.items.length);
  const enMenu = (el) => el.closest('nav, [role=navigation], form');
  const botones = unicos([...document.querySelectorAll('button, [role=button], input[type=submit], input[type=button], a.btn, a.button')]
    .filter((b) => visible(b) && !enMenu(b)).map((b) => (texto(b) || b.value || b.getAttribute('aria-label') || '').slice(0, 60))).slice(0, 40);
  const mensajes = unicos([...document.querySelectorAll('[role=alert], [role=status], [aria-live], .alert, .error, .warning, .notice, .toast, .message')]
    .filter(visible).map((m) => texto(m).slice(0, 200))).slice(0, 20);
  const tablas = [...document.querySelectorAll('table')].filter(visible)
    .map((t) => [...t.querySelectorAll('thead th, tr:first-child th')].map((th) => texto(th).slice(0, 40)).filter(Boolean))
    .filter((c) => c.length).slice(0, 10);
  const principal = document.querySelector('main, [role=main], article') || document.body;
  const parrafos = [...principal.querySelectorAll('p, li')].filter((p) => visible(p) && !p.closest('nav, footer, header, form')).map(texto).filter((t) => t.length > 30);
  let extracto = '';
  for (const p of parrafos) { if ((extracto + p).length > 700) break; extracto += (extracto ? ' ' : '') + p; }
  const desc = document.querySelector('meta[name=description]');
  return { titulo: document.title.trim(), descripcion: desc ? desc.content.trim() : '', idioma: document.documentElement.lang || '',
    encabezados, menus, botones, mensajes, tablas, extracto };
}

// Los menús que aparecen en la mayoría de las páginas son la navegación global: van una sola vez.
function separarMenusGlobales(paginas) {
  const clave = (m) => `${m.nombre}|${m.items.join('|')}`;
  const cuenta = new Map();
  for (const p of paginas) for (const m of p.menus || []) cuenta.set(clave(m), (cuenta.get(clave(m)) || 0) + 1);
  const minimo = Math.max(2, Math.ceil(paginas.length * 0.6));
  const globales = [];
  for (const p of paginas) {
    for (const m of p.menus || []) if (cuenta.get(clave(m)) >= minimo && !globales.some((g) => clave(g) === clave(m))) globales.push(m);
    p.menus = (p.menus || []).filter((m) => cuenta.get(clave(m)) < minimo);
  }
  return globales;
}

const celda = (x) => String(x ?? '').replace(/\|/g, '/').replace(/\s+/g, ' ').trim();

function restricciones(c) {
  const r = [];
  if (c.minlength != null) r.push(`mín. ${c.minlength} caracteres`);
  if (c.maxlength != null) r.push(`máx. ${c.maxlength} caracteres`);
  if (c.min != null) r.push(`mínimo ${c.min}`);
  if (c.max != null) r.push(`máximo ${c.max}`);
  if (c.pattern) r.push(`patrón ${c.pattern}`);
  if (c.opciones && c.opciones.length) r.push(`opciones: ${c.opciones.map((o) => o.texto || o.valor).filter(Boolean).slice(0, 12).join(', ')}`);
  if (c.placeholder) r.push(`placeholder "${c.placeholder}"`);
  return r.join('; ');
}

// Markdown del mapa (con las tablas en Markdown normal: después se pasan por formatear_tablas.py).
function aMarkdown(mapa) {
  const l = [];
  l.push('---', 'titulo: Mapa funcional del sitio', 'tipo: web', `fuentes: ${mapa.url}`, `actualizado: ${mapa.fecha.slice(0, 10)}`,
    'generado_por: npm run mapa-funcional', '---', '', `# Mapa funcional de ${mapa.host}`, '');
  l.push(`Recorrido automático (solo GET, sin login, sin enviar formularios) de ${mapa.paginas.length} página(s) a partir de ${mapa.url}.`,
    'Describe lo que la aplicación muestra hoy: sirve como contexto, **no** como fuente de requisitos.', '');
  if (mapa.sin_recorrer) l.push(`> Quedaron páginas sin recorrer (límite de ${mapa.max_paginas}): subí --max-paginas para cubrirlas.`, '');
  if (mapa.navegacion_global.length) {
    l.push('## Navegación global', '');
    for (const m of mapa.navegacion_global) l.push(`- **${m.nombre}**: ${m.items.join(' · ')}`);
    l.push('');
  }
  l.push('## Páginas', '', '| # | Página | Título | Formularios | Campos |', '|---|---|---|---|---|');
  mapa.paginas.forEach((p, i) => l.push(`| ${i + 1} | ${celda(p.ruta)} | ${celda(p.titulo || p.error)} | ${(p.formularios || []).length} | ${(p.formularios || []).reduce((s, f) => s + f.campos.length, 0)} |`));
  l.push('');
  mapa.paginas.forEach((p, i) => {
    l.push(`## ${i + 1}. ${p.titulo || p.ruta}`, '', `- URL: ${p.url}`);
    if (p.error) { l.push(`- No se pudo abrir: ${p.error}`, ''); return; }
    if (p.descripcion) l.push(`- Descripción: ${p.descripcion}`);
    if (p.encabezados.length) l.push(`- Secciones: ${p.encabezados.map((h) => h.texto).join(' · ')}`);
    for (const m of p.menus) l.push(`- Menú ${m.nombre}: ${m.items.join(' · ')}`);
    if (p.botones.length) l.push(`- Botones: ${p.botones.join(' · ')}`);
    if (p.mensajes.length) l.push(`- Mensajes visibles: ${p.mensajes.map((m) => `"${m}"`).join(' · ')}`);
    for (const t of p.tablas) l.push(`- Tabla con columnas: ${t.join(' · ')}`);
    if (p.extracto) l.push(`- Texto: ${p.extracto}`);
    l.push('');
    for (const f of p.formularios) {
      l.push(`### Formulario: ${f.nombre}${f.metodo ? ` (${f.metodo}${f.accion ? ` ${f.accion}` : ''})` : ''}`, '');
      l.push('| Campo | Etiqueta | Tipo | Obligatorio | Restricciones |', '|---|---|---|---|---|');
      for (const c of f.campos) {
        l.push(`| ${celda(c.nombre)} | ${celda(c.etiqueta)} | ${celda(c.tipo)} | ${c.requerido ? 'Sí' : c.marca_obligatorio ? 'Marcado (*)' : 'No'} | ${celda(restricciones(c))} |`);
      }
      l.push('', f.boton ? '' : '> Sin botón de envío visible.', '');
    }
  });
  return l.filter((x, i, xs) => !(x === '' && xs[i - 1] === '')).join('\n') + '\n';
}

function formatearTablas(archivo) {
  const py = process.platform === 'win32' ? 'python' : 'python3';
  const r = require('child_process').spawnSync(py, [path.join(RAIZ, 'scripts', 'formatear_tablas.py'), archivo], { encoding: 'utf8' });
  if (r.status !== 0) console.log(`No pude alinear las tablas (${(r.stderr || r.error || '').toString().trim().split('\n').pop()}). Corré: python scripts/formatear_tablas.py ${path.relative(RAIZ, archivo)}`);
}

async function main() {
  const a = argumentos(process.argv.slice(2));
  if (a.ayuda) {
    console.log(fs.readFileSync(__filename, 'utf8').split('\n').filter((l) => l.startsWith('//')).map((l) => l.slice(3)).join('\n'));
    return;
  }
  const url = a.url || (a.paginas && a.paginas[0]) || process.env.APP_URL || process.env.BASEURL;
  if (!url) throw new Error('No hay URL: pasala con --url o definí APP_URL en el .env de la raíz.');
  if (!/^https?:\/\//i.test(url)) throw new Error(`La URL tiene que empezar con http:// o https:// (recibí "${url}").`);
  const inicio = normalizar(url);
  const host = new URL(inicio).hostname;
  const carpeta = a.salida ? desde(a.salida) : path.join(RAIZ, 'input', 'documentacion', 'proyecto');
  fs.mkdirSync(carpeta, { recursive: true });

  const { chromium } = require('playwright'); // acá y no arriba: los tests usan las funciones sin instalar k0lmena
  const browser = await chromium.launch({ headless: !a.headed });
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, locale: process.env.LOCALE || 'es-AR' });
  const page = await ctx.newPage();
  // Nunca se envía nada: cualquier navegación que no sea GET se corta.
  await page.route('**/*', (route) => {
    const rq = route.request();
    return rq.isNavigationRequest() && rq.method() !== 'GET' ? route.abort() : route.continue();
  });

  console.log(`Mapa funcional de ${inicio} · hasta ${a.maxPaginas} páginas · profundidad ${a.profundidad}`);
  const urls = await descubrir(page, inicio, a);
  const paginas = [];
  for (const [i, u] of urls.entries()) {
    process.stdout.write(`[${i + 1}/${urls.length}] ${u} `);
    const reg = { url: u, ruta: new URL(u).pathname + new URL(u).search };
    try {
      const { resp } = await cargar(page, u);
      reg.status = resp ? resp.status() : 0;
      await recorrerScroll(page);
      Object.assign(reg, await page.evaluate(_contenido));
      reg.formularios = (await page.evaluate(extraerFormularios)).map(({ indice, ...f }) => f);
      console.log(`· ${reg.formularios.length} formulario(s)`);
    } catch (e) {
      reg.error = String(e.message || e).split('\n')[0];
      console.log(`· error: ${reg.error}`);
    }
    paginas.push(reg);
    if (a.pausaMs) await esperar(a.pausaMs);
  }
  await browser.close();

  const navegacion_global = separarMenusGlobales(paginas.filter((p) => !p.error));
  const mapa = { url: inicio, host, fecha: new Date().toISOString(), max_paginas: a.maxPaginas,
    sin_recorrer: !a.paginas && urls.length >= a.maxPaginas, navegacion_global, paginas };
  const json = path.join(carpeta, 'mapa-funcional.json');
  const md = path.join(carpeta, 'mapa-funcional.md');
  fs.writeFileSync(json, JSON.stringify(mapa, null, 2));
  fs.writeFileSync(md, aMarkdown(mapa));
  formatearTablas(md);
  const rel = (p) => path.relative(RAIZ, p).split(path.sep).join('/');
  console.log(`\n${paginas.length} página(s), ${paginas.reduce((s, p) => s + (p.formularios || []).length, 0)} formulario(s).`);
  console.log(`Mapa: ${rel(md)} (datos: ${rel(json)})`);
}

if (require.main === module) {
  main().catch((e) => { console.error(`Error: ${e.message}`); process.exit(1); });
}

module.exports = { argumentos, separarMenusGlobales, restricciones, aMarkdown };
