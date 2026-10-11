// Pruebas cross-browser: Chromium (Chrome y Edge), Firefox y WebKit (Safari) (agente cross-browser).
//
// Uso (desde la raíz del repo):
//   npm run cross-browser -- [--modo suite|paginas] [--navegadores chromium,firefox,webkit]
//                            [--resoluciones 1366x768,390x844] [--tags "@HU-001"] [--historia HU-001]
//                            [--url https://mi-app.com] [--paginas url1,url2] [--max-paginas 6]
//                            [--base chromium] [--tolerancia-px 6] [--umbral 0.1] [--ocultar ".banner"] [--headed]
//
// Dos modos (por defecto, suite si hay .feature en web/features; si no, páginas):
//   suite   → corre la suite web de k0lmena (npm test) una vez por navegador y resolución, cada una
//             en su carpeta (no pisa el último npm test), y arma la matriz escenario × navegador:
//             qué pasa en todos, qué falla en todos (no es un problema de navegador) y qué falla solo
//             en algunos (diferencia entre navegadores: lo que busca esta prueba). Corre contra el
//             ambiente como npm test: puede crear datos.
//   paginas → recorre las páginas del sitio en cada navegador y resolución (solo GET) y compara
//             contra el navegador base: errores de JavaScript, de consola y recursos que fallan solo
//             en un navegador, desborde horizontal, elementos que faltan o se corren, cambios de
//             estilo y porcentaje de la pantalla que se ve distinto.
//
// Los navegadores que no están instalados se informan con el comando para instalarlos
// (npx playwright install firefox webkit). WebKit es el motor de Safari; en Windows y Linux es una
// muy buena aproximación, pero no reemplaza probar en un Safari real de Mac o iPhone.
//
// Deja todo en output/cross-browser/<HU, host o suite>/ y cada corrida REEMPLAZA a la anterior:
// cross-browser.json, informe-cross-browser.html, capturas/, diferencias/, recortes/ y suite/.
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const { normalizar, slug, sello, recorrerScroll, cargar } = require('../explorador/explorar.js');
const { parsearResoluciones, descubrir } = require('../pixel-perfect/pixel-perfect.js');
const visual = require('../visual/comparar.js');

const RAIZ = path.resolve(__dirname, '..', '..', '..', '..');
const desde = (p) => path.resolve(process.env.INIT_CWD || process.cwd(), p); // npm run cambia el cwd a herramientas/k0lmena
const K0 = path.resolve(__dirname, '..', '..');
const GENERADOS = ['cross-browser.json', 'analisis.json', 'informe-cross-browser.html', 'capturas', 'diferencias', 'recortes', 'suite'];
const NAVEGADORES = ['chromium', 'firefox', 'webkit'];
const NOMBRE = { chromium: 'Chromium (Chrome, Edge)', firefox: 'Firefox', webkit: 'WebKit (Safari)' };
const SEV_ORDEN = { 'Crítica': 0, 'Alta': 1, 'Media': 2, 'Baja': 3 };

function argumentos(argv) {
  const a = { navegadores: NAVEGADORES, base: 'chromium', maxPaginas: 6, profundidad: 1, tolerancia: 6, umbral: 0.1, ocultar: [], headed: false };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    const v = () => argv[++i];
    if (k === '--modo') a.modo = v().toLowerCase();
    else if (k === '--navegadores') a.navegadores = v().split(',').map((x) => x.trim().toLowerCase()).filter(Boolean);
    else if (k === '--resoluciones') a.resoluciones = v();
    else if (k === '--tags') a.tags = v();
    else if (k === '--historia') a.historia = v();
    else if (k === '--url') a.url = v();
    else if (k === '--paginas') a.paginas = v().split(',').map((x) => x.trim()).filter(Boolean);
    else if (k === '--max-paginas') a.maxPaginas = parseInt(v(), 10);
    else if (k === '--profundidad') a.profundidad = parseInt(v(), 10);
    else if (k === '--base') a.base = v().toLowerCase();
    else if (k === '--tolerancia-px') a.tolerancia = parseInt(v(), 10);
    else if (k === '--umbral') a.umbral = parseFloat(v());
    else if (k === '--ocultar') a.ocultar = v().split(',').map((x) => x.trim()).filter(Boolean);
    else if (k === '--salida') a.salida = v();
    else if (k === '--headed') a.headed = true;
    else if (k === '-h' || k === '--help') a.ayuda = true;
    else throw new Error(`Opción desconocida: ${k}`);
  }
  const malos = a.navegadores.filter((n) => !NAVEGADORES.includes(n));
  if (malos.length) throw new Error(`Navegador desconocido: ${malos.join(', ')}. Opciones: ${NAVEGADORES.join(', ')}.`);
  if (a.modo && !['suite', 'paginas'].includes(a.modo)) throw new Error('--modo: suite o paginas.');
  if (!a.navegadores.includes(a.base)) a.base = a.navegadores[0];
  return a;
}

// ¿Está instalado y arranca? Devuelve la versión o el motivo.
async function probarNavegador(nombre) {
  const pw = require('playwright');
  try {
    const b = await pw[nombre].launch();
    const version = b.version();
    await b.close();
    return { nombre, ok: true, version };
  } catch (e) {
    const msg = String(e.message || e);
    const falta = /Executable doesn't exist|browserType\.launch.*install|Please run the following command/i.test(msg);
    return { nombre, ok: false, error: falta ? 'No está instalado' : msg.split('\n')[0].slice(0, 200),
      instalar: falta ? `cd herramientas/k0lmena && npx playwright install ${nombre}` : null };
  }
}

function hayFeatures() {
  const dir = path.join(K0, 'web', 'features');
  return fs.existsSync(dir) && fs.readdirSync(dir).some((f) => f.endsWith('.feature'));
}

// ------------------------------------------------------------------ modo suite
// Los errores de Playwright traen códigos de color de la terminal: se sacan para leerlos.
const sinAnsi = (s) => String(s).replace(/\x1b\[[0-9;]*m/g, '');

function leerCucumber(archivo) {
  let features = [];
  try { features = JSON.parse(fs.readFileSync(archivo, 'utf8') || '[]'); } catch { return []; }
  const salida = new Map();
  for (const f of features) {
    for (const esc of f.elements || []) {
      if (esc.type === 'background') continue;
      const tags = [...new Set([...(f.tags || []), ...(esc.tags || [])].map((t) => t.name.replace(/^@/, '')))];
      let estado = 'Aprobado';
      let paso = null;
      let error = '';
      let dur = 0;
      const capturas = [];
      for (const p of esc.steps || []) {
        const r = p.result || {};
        dur += r.duration || 0;
        const kw = (p.keyword || '').trim();
        if (r.status === 'failed' || r.status === 'ambiguous') {
          estado = 'Fallido';
          if (!paso) paso = `${kw} ${p.name || ''}`.trim();
          if (!error) error = sinAnsi(r.error_message || '').trim();
        } else if (['undefined', 'pending'].includes(r.status) && estado !== 'Fallido') {
          estado = 'Fallido';
          paso = paso || `${kw} ${p.name || ''}`.trim();
          error = error || `Paso ${r.status === 'undefined' ? 'sin definir' : 'pendiente'}`;
        } else if (r.status === 'skipped' && estado === 'Aprobado' && !['Before', 'After'].includes(kw)) estado = 'Salteado';
        for (const emb of p.embeddings || []) if (emb.mime_type === 'image/png') capturas.push(emb.data);
      }
      const clave = `${f.uri}:${esc.line}`;
      // Con retry, el mismo escenario aparece más de una vez: vale el último intento.
      salida.set(clave, { clave, escenario: esc.name, feature: f.name, uri: f.uri, linea: esc.line, tags,
        historia: tags.find((t) => /^HU-\d+$/i.test(t)) || null, caso: tags.find((t) => /^CP(-API)?-\d+$/.test(t)) || null,
        estado, paso, error: error.slice(0, 3000), duracion_s: Math.round(dur / 1e7) / 100, _captura: capturas[capturas.length - 1] });
    }
  }
  return [...salida.values()];
}

function correrSuite(a, combos, carpeta, rel) {
  const dirSuite = path.join(carpeta, 'suite');
  const dirCap = path.join(carpeta, 'capturas');
  const corridas = [];
  for (const c of combos) {
    const dir = path.join(dirSuite, c.id);
    fs.mkdirSync(dir, { recursive: true });
    process.stdout.write(`Suite web en ${c.id.padEnd(18)} `);
    const t0 = Date.now();
    const env = { ...process.env, BROWSER: c.navegador, REPORT_DIR: dir, VIEWPORT_WIDTH: String(c.res.ancho),
      VIEWPORT_HEIGHT: String(c.res.alto), EVIDENCE: 'captura', HEADLESS: a.headed ? 'false' : 'true' };
    if (a.tags) env.TAGS = a.tags;
    const r = spawnSync('npx cucumber-js --profile web', { cwd: K0, env, shell: true, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
    const escenarios = leerCucumber(path.join(dir, 'cucumber-report.json'));
    for (const e of escenarios) {
      if (e._captura) {
        const arch = path.join(dirCap, `${c.id}-${slug(`http://x/${e.caso || ''}-${e.escenario}`)}.png`);
        fs.writeFileSync(arch, Buffer.from(e._captura, 'base64'));
        e.captura = rel(arch);
      }
      delete e._captura;
    }
    const ap = escenarios.filter((e) => e.estado === 'Aprobado').length;
    const salida = `${r.stdout || ''}\n${r.stderr || ''}`;
    const fallaGeneral = !escenarios.length ? salida.trim().split(/\r?\n/).filter(Boolean).slice(-6).join('\n') : null;
    console.log(escenarios.length ? `→ ${ap}/${escenarios.length} aprobados (${Math.round((Date.now() - t0) / 1000)} s)` : '→ sin resultados');
    corridas.push({ ...c, res: c.res.id, escenarios, duracion_s: Math.round((Date.now() - t0) / 1000), error: fallaGeneral,
      reporte: fs.existsSync(path.join(dir, 'front-report.html')) ? rel(path.join(dir, 'front-report.html')) : null });
  }
  return corridas;
}

const comboTxt = (id) => { const [n, r] = id.split('-'); return `${NOMBRE[n] ? NOMBRE[n].split(' ')[0] : n} ${r || ''}`.trim(); };
const listaTxt = (ids) => ids.map(comboTxt).join(', ');

function analizarSuite(corridas, base) {
  const claves = new Map();
  for (const c of corridas) for (const e of c.escenarios) if (!claves.has(e.clave)) claves.set(e.clave, e);
  const filas = [];
  const hallazgos = [];
  for (const [clave, e0] of claves) {
    const res = {};
    for (const c of corridas) {
      const e = c.escenarios.find((x) => x.clave === clave);
      res[c.id] = e ? { estado: e.estado, paso: e.paso, error: e.error, captura: e.captura, duracion_s: e.duracion_s }
        : { estado: c.error ? 'Sin resultado' : 'No corrió' };
    }
    const estados = Object.values(res).map((x) => x.estado);
    const fallan = Object.entries(res).filter(([, x]) => x.estado === 'Fallido').map(([k]) => k);
    const pasan = Object.entries(res).filter(([, x]) => x.estado === 'Aprobado').map(([k]) => k);
    let clase;
    if (estados.every((s) => s === 'Aprobado')) clase = 'Pasa en todos';
    else if (fallan.length && !pasan.length) clase = 'Falla en todos';
    else if (fallan.length && pasan.length) clase = 'Diferencia entre navegadores';
    else clase = 'Sin resultado completo';
    filas.push({ clave, escenario: e0.escenario, feature: e0.feature, uri: e0.uri, linea: e0.linea, historia: e0.historia,
      caso: e0.caso, clase, resultados: res });
    const ident = [e0.historia, e0.caso].filter(Boolean).join(' · ');
    if (clase === 'Diferencia entre navegadores') {
      const err = res[fallan[0]];
      hallazgos.push({ tipo: 'Falla solo en algunos navegadores', severidad: 'Alta',
        titulo: `${ident ? `${ident} · ` : ''}${e0.escenario}: falla en ${listaTxt(fallan)} y pasa en ${listaTxt(pasan)}`,
        detalle: `Paso que falla: ${err.paso || '—'}. ${(err.error || '').split('\n')[0].slice(0, 220)}`,
        escenario: clave, fallan, pasan, error: err.error, paso: err.paso,
        evidencias: [...fallan, ...pasan.slice(0, 1)].map((k) => ({ combo: k, estado: res[k].estado, captura: res[k].captura })).filter((x) => x.captura) });
    } else if (clase === 'Falla en todos') {
      const err = res[fallan[0]];
      hallazgos.push({ tipo: 'Falla en todos los navegadores', severidad: 'Media',
        titulo: `${ident ? `${ident} · ` : ''}${e0.escenario}: falla en todos los navegadores`,
        detalle: 'No es una diferencia entre navegadores: es un bug o un test roto en cualquier navegador (analizalo con el analista-fallos). ' +
          `Paso: ${err.paso || '—'}. ${(err.error || '').split('\n')[0].slice(0, 200)}`,
        escenario: clave, fallan, pasan: [], error: err.error, paso: err.paso,
        evidencias: fallan.slice(0, 1).map((k) => ({ combo: k, estado: 'Fallido', captura: res[k].captura })).filter((x) => x.captura) });
    }
  }
  return { filas, hallazgos };
}

// ------------------------------------------------------------------ modo páginas
async function recorrerPaginas(a, combos, paginas, carpeta, rel) {
  const pw = require('playwright');
  const dirCap = path.join(carpeta, 'capturas');
  const medidas = {}; // `${pagina}|${combo}` → datos
  for (const c of combos) {
    const browser = await pw[c.navegador].launch({ headless: !a.headed });
    const movil = c.res.ancho < 768;
    for (const [i, u] of paginas.entries()) {
      const id = `${String(i + 1).padStart(2, '0')}-${slug(u)}`;
      process.stdout.write(`[${c.id.padEnd(18)}] ${u} `);
      const ctx = await browser.newContext({ viewport: { width: c.res.ancho, height: c.res.alto }, deviceScaleFactor: 1,
        locale: process.env.LOCALE || 'es-AR', ...(movil && c.navegador !== 'firefox' ? { isMobile: true, hasTouch: true } : {}) });
      const page = await ctx.newPage();
      const m = { pagina: id, url: u, combo: c.id, navegador: c.navegador, resolucion: c.res.id, errores_js: [], errores_consola: [], recursos_fallidos: [] };
      page.on('pageerror', (e) => m.errores_js.push(String(e.message || e).split('\n')[0].slice(0, 300)));
      page.on('console', (msg) => { if (msg.type() === 'error') m.errores_consola.push(msg.text().slice(0, 300)); });
      page.on('requestfailed', (rq) => {
        const f = rq.failure();
        if (f && !/ABORTED|NS_BINDING_ABORTED|cancelled/i.test(f.errorText)) m.recursos_fallidos.push({ url: rq.url(), error: f.errorText });
      });
      page.on('response', (rs) => { if (rs.status() >= 400 && rs.request().resourceType() !== 'document') m.recursos_fallidos.push({ url: rs.url(), error: `HTTP ${rs.status()}` }); });
      try {
        const { resp, ms } = await cargar(page, u);
        m.status = resp ? resp.status() : 0;
        m.tiempo_ms = ms;
        await recorrerScroll(page);
        await page.evaluate(() => window.scrollTo(0, 0));
        await visual.estabilizar(page, { ocultar: a.ocultar });
        const med = await visual.medirElementos(page);
        m.elementos = med.elementos;
        m.alto = med.alto;
        m.desborde = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        const arch = path.join(dirCap, `${id}-${c.id}.png`);
        const alto = Math.min(med.alto, 10000);
        await page.screenshot({ path: arch, fullPage: alto === med.alto, timeout: 30000,
          ...(alto < med.alto ? { clip: { x: 0, y: 0, width: c.res.ancho, height: alto } } : {}) });
        m.captura = rel(arch);
        m._archivo = arch;
        console.log(`→ ${m.status} · ${m.errores_js.length} error(es) JS`);
      } catch (e) {
        m.error = String(e.message || e).split('\n')[0].slice(0, 200);
        console.log(`→ error: ${m.error}`);
      }
      m.errores_js = [...new Set(m.errores_js)];
      m.errores_consola = [...new Set(m.errores_consola)];
      m.recursos_fallidos = [...new Map(m.recursos_fallidos.map((r) => [r.url, r])).values()];
      medidas[`${id}|${c.id}`] = m;
      await ctx.close();
    }
    await browser.close();
  }
  return medidas;
}

const textoEl = (e) => (e.texto ? `“${e.texto.slice(0, 50)}”` : e.desc);
const caja = (e) => ({ x: e.x, y: e.y, w: e.w, h: e.h });

function analizarPaginas(a, combos, paginas, medidas, carpeta, rel) {
  const dirDif = path.join(carpeta, 'diferencias');
  const dirRec = path.join(carpeta, 'recortes');
  const hallazgos = [];
  const filas = [];
  const resols = [...new Set(combos.map((c) => c.res.id))];
  for (const [i, u] of paginas.entries()) {
    const id = `${String(i + 1).padStart(2, '0')}-${slug(u)}`;
    for (const res of resols) {
      const cs = combos.filter((c) => c.res.id === res);
      const base = cs.find((c) => c.navegador === a.base) || cs[0];
      const mb = medidas[`${id}|${base.id}`];
      const fila = { pagina: id, url: u, resolucion: res, base: base.id, resultados: {} };
      // Lo que pasa en todos no es un problema de navegador (lo ve el explorador-web).
      const enTodos = (campo, f = (x) => x) => {
        const conj = cs.map((c) => new Set((medidas[`${id}|${c.id}`] || {})[campo] ? medidas[`${id}|${c.id}`][campo].map(f) : []));
        return new Set([...conj[0]].filter((x) => conj.every((s) => s.has(x))));
      };
      const jsTodos = enTodos('errores_js');
      const recTodos = enTodos('recursos_fallidos', (r) => r.url);
      for (const c of cs) {
        const m = medidas[`${id}|${c.id}`];
        const r = { estado: 'OK', captura: m && m.captura, errores_js: m ? m.errores_js.length : 0, desborde: m ? m.desborde : null,
          tiempo_ms: m && m.tiempo_ms, status: m && m.status };
        fila.resultados[c.id] = r;
        if (!m || m.error) { r.estado = 'Error'; r.error = m ? m.error : 'sin datos'; continue; }
        const propios = [];
        const h = (x) => { propios.push(x); hallazgos.push({ pagina: id, url: u, resolucion: res, navegador: c.navegador, combo: c.id, ...x }); };
        for (const err of m.errores_js.filter((x) => !jsTodos.has(x))) {
          h({ tipo: 'Error de JavaScript', severidad: 'Alta', titulo: `Error de JavaScript solo en ${NOMBRE[c.navegador]}`, detalle: err, captura: m.captura });
        }
        const consolaOtros = new Set(cs.filter((x) => x.id !== c.id).flatMap((x) => (medidas[`${id}|${x.id}`] || {}).errores_consola || []));
        for (const err of m.errores_consola.filter((x) => !consolaOtros.has(x) && !m.errores_js.some((j) => x.includes(j))).slice(0, 5)) {
          h({ tipo: 'Error de consola', severidad: 'Media', titulo: `Error de consola solo en ${NOMBRE[c.navegador]}`, detalle: err, captura: m.captura });
        }
        for (const rf of m.recursos_fallidos.filter((x) => !recTodos.has(x.url)).slice(0, 5)) {
          h({ tipo: 'Recurso que falla', severidad: 'Media', titulo: `No carga en ${NOMBRE[c.navegador]}: ${rf.url.split('/').pop() || rf.url}`,
            detalle: `${rf.url} → ${rf.error}`, captura: m.captura });
        }
        const otrosDesb = cs.filter((x) => x.id !== c.id).map((x) => (medidas[`${id}|${x.id}`] || {}).desborde || 0);
        if (m.desborde > 4 && otrosDesb.some((d) => d <= 4)) {
          h({ tipo: 'Desborde horizontal', severidad: 'Media', titulo: `La página se sale ${m.desborde} px de ancho solo en ${NOMBRE[c.navegador]}`,
            detalle: 'Aparece scroll horizontal en este navegador y no en los demás: un elemento se renderiza más ancho.', captura: m.captura });
        }
        if (m.status && mb && mb.status && m.status !== mb.status) {
          h({ tipo: 'Respuesta distinta', severidad: 'Alta', titulo: `Responde ${m.status} en ${NOMBRE[c.navegador]} y ${mb.status} en ${NOMBRE[base.navegador]}`,
            detalle: 'El servidor responde distinto según el navegador (detección de user agent).', captura: m.captura });
        }
        if (c.id !== base.id && mb && !mb.error && m._archivo && mb._archivo) {
          const cmp = visual.compararPng(mb._archivo, m._archivo, { umbral: a.umbral });
          const dif = path.join(dirDif, `${id}-${c.id}.png`);
          fs.writeFileSync(dif, cmp.diff);
          r.pct = cmp.pct;
          r.diferencia = rel(dif);
          const el = visual.compararElementos(mb.elementos, m.elementos, { tolerancia: a.tolerancia });
          const nombreNav = NOMBRE[c.navegador];
          const conRecorte = (x, cajaBase, cajaNav) => {
            const cajas = [cajaBase, cajaNav].filter(Boolean);
            const v = visual.ventanaDe(cajas, 70);
            const pref = path.join(dirRec, `${id}-${c.id}-${hallazgos.length + 1}`);
            if (cajaBase) { fs.writeFileSync(`${pref}-base.png`, visual.recorteMarcado(mb._archivo, v, cajaBase)); x.base_captura = rel(`${pref}-base.png`); }
            if (cajaNav) { fs.writeFileSync(`${pref}-nav.png`, visual.recorteMarcado(m._archivo, v, cajaNav, [20, 168, 149])); x.nav_captura = rel(`${pref}-nav.png`); }
            return x;
          };
          for (const f of el.faltantes.filter((x) => ['a', 'button', 'input', 'select', 'textarea', 'img', 'h1', 'h2', 'h3', 'form'].includes(x.tag)).slice(0, 8)) {
            h(conRecorte({ tipo: 'Elemento faltante', severidad: ['a', 'button', 'input', 'select', 'textarea', 'form'].includes(f.tag) ? 'Alta' : 'Media',
              titulo: `${textoEl(f)} no aparece en ${nombreNav}`, detalle: `${f.desc} está en ${NOMBRE[base.navegador]} y no se ve en ${nombreNav}.` }, caja(f), null));
          }
          for (const b of el.bloques.filter((x) => Math.hypot(x.dx, x.dy) >= 12).slice(0, 3)) {
            h(conRecorte({ tipo: 'Bloque desplazado', severidad: Math.hypot(b.dx, b.dy) >= 40 ? 'Media' : 'Baja',
              titulo: `${b.elementos} elementos desplazados ${b.dx ? `${b.dx} px en X ` : ''}${b.dy ? `${b.dy} px en Y` : ''} en ${nombreNav}`,
              detalle: `Desde ${textoEl(b.desde)}: algo de arriba se renderiza con otro tamaño en ${nombreNav}.` }, caja(b.desde),
            { ...caja(b.desde), x: b.desde.x + b.dx, y: b.desde.y + b.dy }));
          }
          for (const mv of el.movidos.filter((x) => Math.hypot(x.dx, x.dy) >= 12).slice(0, 8)) {
            h(conRecorte({ tipo: 'Elemento corrido', severidad: mv.severidad, titulo: `${textoEl(mv)} se corre ${mv.dx >= 0 ? '+' : ''}${mv.dx} px en X y ${mv.dy >= 0 ? '+' : ''}${mv.dy} px en Y en ${nombreNav}`,
              detalle: `${mv.desc}: (${mv.x}, ${mv.y}) en ${NOMBRE[base.navegador]} y (${mv.actual.x}, ${mv.actual.y}) en ${nombreNav}.`,
              delta: { dx: mv.dx, dy: mv.dy, dw: mv.dw, dh: mv.dh } }, caja(mv), caja(mv.actual)));
          }
          for (const s of (el.estilos || []).filter((x) => x.prop === 'fondo' || x.prop === 'color').slice(0, 4)) {
            const ej = s.elementos[0];
            h(conRecorte({ tipo: 'Estilo distinto', severidad: 'Media', titulo: `${s.elementos.length === 1 ? textoEl(ej) : `${s.elementos.length} elementos`}: ${s.nombre} ${s.de} → ${s.a} en ${nombreNav}`,
              detalle: `El ${s.nombre} se calcula distinto en ${nombreNav} (una propiedad CSS no soportada o con otro valor por defecto).`,
              estilo: { propiedad: s.prop, de: s.de, a: s.a } }, caja(ej), caja(ej.actual)));
          }
          if (cmp.pct > 15 && !propios.some((x) => ['Elemento faltante', 'Bloque desplazado', 'Elemento corrido'].includes(x.tipo))) {
            h({ tipo: 'Se ve distinto', severidad: cmp.pct > 35 ? 'Media' : 'Baja', titulo: `El ${cmp.pct} % de la pantalla se ve distinto en ${nombreNav}`,
              detalle: 'Cambia el renderizado (fuentes, suavizado, imágenes o estilos) aunque los elementos estén en su lugar: compará las capturas.',
              captura: m.captura, base_captura: mb.captura, nav_captura: m.captura });
          }
        }
        if (propios.some((x) => SEV_ORDEN[x.severidad] <= 1)) r.estado = 'Con problemas';
        else if (propios.length) r.estado = 'Diferencias menores';
        r.hallazgos = propios.length;
      }
      filas.push(fila);
    }
  }
  for (const k of Object.keys(medidas)) { delete medidas[k]._archivo; delete medidas[k].elementos; }
  return { filas, hallazgos };
}

// El mismo error (o recurso) en varias páginas y resoluciones es un solo hallazgo con la lista de
// pantallas donde aparece: suele ser una sola causa (un script o un estilo de la plantilla).
const AGRUPABLES = new Set(['Error de JavaScript', 'Error de consola', 'Recurso que falla', 'Respuesta distinta']);
function agrupar(hallazgos) {
  const salida = [];
  const grupos = new Map();
  for (const h of hallazgos) {
    if (!h.pagina) { salida.push(h); continue; }
    const pantalla = { pagina: h.pagina, url: h.url, resolucion: h.resolucion, combo: h.combo, captura: h.captura };
    if (!AGRUPABLES.has(h.tipo)) { salida.push({ ...h, pantallas: [pantalla] }); continue; }
    const k = `${h.tipo}|${h.navegador}|${h.detalle}`;
    if (!grupos.has(k)) { const g = { ...h, pantallas: [] }; grupos.set(k, g); salida.push(g); }
    grupos.get(k).pantallas.push(pantalla);
  }
  for (const g of grupos.values()) {
    const urls = new Set(g.pantallas.map((p) => p.url));
    if (g.pantallas.length > 1) g.titulo += ` · ${urls.size} página(s), ${g.pantallas.length} pantalla(s)`;
  }
  return salida;
}

function generarInforme(carpeta) {
  const py = process.platform === 'win32' ? 'python' : 'python3';
  const r = spawnSync(py, [path.join(RAIZ, 'scripts', 'generar_informe_cross_browser.py'),
    path.join(carpeta, 'cross-browser.json'), path.join(carpeta, 'informe-cross-browser.html')], { encoding: 'utf8' });
  if (r.status !== 0) {
    const motivo = (r.stderr || r.error || '').toString().trim().split(/\r?\n/).pop();
    console.log(`No pude generar el informe HTML (${motivo}). Generalo con: python scripts/generar_informe_cross_browser.py ` +
      '<carpeta>/cross-browser.json <carpeta>/informe-cross-browser.html');
    return false;
  }
  return true;
}

async function main() {
  const a = argumentos(process.argv.slice(2));
  if (a.ayuda) {
    console.log(fs.readFileSync(__filename, 'utf8').split('\n').filter((l) => l.startsWith('//')).map((l) => l.slice(3)).join('\n'));
    return;
  }
  const modo = a.modo || (hayFeatures() ? 'suite' : 'paginas');
  if (modo === 'suite' && !hayFeatures()) throw new Error('No hay escenarios en herramientas/k0lmena/web/features: automatizá primero (web-mapper) o usá --modo paginas.');
  if (a.historia && !/^[A-Za-z]+-\d+$/.test(a.historia)) throw new Error('--historia tiene que ser un ID como HU-001.');
  let inicio = null;
  let host = null;
  if (modo === 'paginas') {
    const url = a.url || (a.paginas && a.paginas[0]) || process.env.APP_URL || process.env.BASEURL;
    if (!url) throw new Error('No hay URL: pasala con --url o definí APP_URL en el .env de la raíz.');
    if (!/^https?:\/\//i.test(url)) throw new Error(`La URL tiene que empezar con http:// o https:// (recibí "${url}").`);
    inicio = normalizar(url);
    host = new URL(inicio).hostname;
  }
  if (modo === 'suite' && a.historia && !a.tags) a.tags = `@${a.historia}`;
  const nombre = a.historia || (modo === 'paginas' ? host : 'suite');
  const carpeta = a.salida ? desde(a.salida) : path.join(RAIZ, 'output', 'cross-browser', nombre);
  for (const n of GENERADOS) fs.rmSync(path.join(carpeta, n), { recursive: true, force: true });
  for (const d of ['capturas', 'diferencias', 'recortes']) fs.mkdirSync(path.join(carpeta, d), { recursive: true });
  const rel = (p) => path.relative(carpeta, p).split(path.sep).join('/');
  const relRaiz = (p) => path.relative(RAIZ, p).split(path.sep).join('/');
  const t0 = Date.now();

  console.log(`Cross-browser · modo ${modo} · navegadores: ${a.navegadores.join(', ')}`);
  const navegadores = [];
  for (const n of a.navegadores) navegadores.push(await probarNavegador(n));
  for (const n of navegadores) console.log(`  ${n.nombre.padEnd(9)} ${n.ok ? `OK (${n.version})` : `${n.error}${n.instalar ? ` → ${n.instalar}` : ''}`}`);
  const disponibles = navegadores.filter((n) => n.ok).map((n) => n.nombre);
  if (!disponibles.length) throw new Error('Ningún navegador disponible. Instalalos con: cd herramientas/k0lmena && npx playwright install chromium firefox webkit');
  if (!disponibles.includes(a.base)) a.base = disponibles[0];
  const resoluciones = parsearResoluciones(a.resoluciones || (modo === 'suite' ? '1366x768' : '1366x768,390x844'));
  const combos = [];
  for (const res of resoluciones) for (const n of disponibles) combos.push({ id: `${n}-${res.id}`, navegador: n, res });
  console.log(`Salida: ${relRaiz(carpeta)} (reemplaza la corrida anterior)`);

  let datos;
  if (modo === 'suite') {
    const corridas = correrSuite(a, combos, carpeta, rel);
    const { filas, hallazgos } = analizarSuite(corridas, a.base);
    const cuenta = (c) => filas.filter((f) => f.clase === c).length;
    datos = { corridas: corridas.map((c) => ({ id: c.id, navegador: c.navegador, resolucion: c.res, duracion_s: c.duracion_s, error: c.error,
      reporte: c.reporte, aprobados: c.escenarios.filter((e) => e.estado === 'Aprobado').length,
      fallidos: c.escenarios.filter((e) => e.estado === 'Fallido').length, total: c.escenarios.length })),
    escenarios: filas, hallazgos,
    resumen: { escenarios: filas.length, pasan_en_todos: cuenta('Pasa en todos'), diferencias: cuenta('Diferencia entre navegadores'),
      fallan_en_todos: cuenta('Falla en todos'), incompletos: cuenta('Sin resultado completo') } };
  } else {
    const pw = require('playwright');
    const b = await pw[a.base].launch();
    const ctx = await b.newContext();
    const paginas = await descubrir(await ctx.newPage(), inicio, a);
    await b.close();
    console.log(`${paginas.length} página(s) × ${combos.length} combinación(es) de navegador y resolución`);
    const medidas = await recorrerPaginas(a, combos, paginas, carpeta, rel);
    const { filas, hallazgos } = analizarPaginas(a, combos, paginas, medidas, carpeta, rel);
    const conProblemas = filas.filter((f) => Object.values(f.resultados).some((r) => r.estado === 'Con problemas')).length;
    const pcts = filas.flatMap((f) => Object.values(f.resultados).map((r) => r.pct).filter((x) => x != null));
    datos = { paginas: filas, medidas: Object.values(medidas), hallazgos,
      resumen: { paginas: paginas.length, pantallas: filas.length, comparaciones: pcts.length,
        sin_diferencias: filas.filter((f) => Object.values(f.resultados).every((r) => r.estado === 'OK')).length,
        con_problemas: conProblemas, pct_max: pcts.length ? Math.max(...pcts) : 0, pct_prom: pcts.length ? Math.round(pcts.reduce((s, x) => s + x, 0) / pcts.length * 100) / 100 : 0,
        errores_js_exclusivos: hallazgos.filter((h) => h.tipo === 'Error de JavaScript').length } };
  }
  datos.hallazgos = agrupar(datos.hallazgos);
  datos.hallazgos.sort((x, y) => SEV_ORDEN[x.severidad] - SEV_ORDEN[y.severidad] || (y.pantallas || []).length - (x.pantallas || []).length);
  datos.hallazgos.forEach((h, i) => { h.id = `X-${String(i + 1).padStart(2, '0')}`; });
  const porNav = {};
  for (const n of disponibles) porNav[n] = datos.hallazgos.filter((h) => (h.navegador ? h.navegador === n : (h.fallan || []).some((f) => f.startsWith(n)))).length;
  const resultado = {
    modo, url: inicio, host, historia: a.historia || null, tags: a.tags || null, fecha: new Date().toISOString(), marca: sello(),
    duracion_s: Math.round((Date.now() - t0) / 1000), base: a.base, herramienta: `Playwright ${require('playwright/package.json').version}`,
    navegadores: navegadores.map((n) => ({ ...n, titulo: NOMBRE[n.nombre] })), resoluciones: resoluciones.map((r) => r.id),
    config: { tolerancia_px: a.tolerancia, umbral: a.umbral, ocultar: a.ocultar },
    ...datos,
  };
  resultado.resumen.hallazgos = datos.hallazgos.length;
  resultado.resumen.por_navegador = porNav;
  resultado.resumen.por_severidad = Object.fromEntries(['Crítica', 'Alta', 'Media', 'Baja'].map((s) => [s, datos.hallazgos.filter((h) => h.severidad === s).length]));
  resultado.resumen.no_instalados = navegadores.filter((n) => !n.ok).map((n) => n.nombre);
  const salida = path.join(carpeta, 'cross-browser.json');
  fs.writeFileSync(salida, JSON.stringify(resultado, null, 2), 'utf8');
  const r = resultado.resumen;
  if (modo === 'suite') console.log(`\nEscenarios: ${r.escenarios} · pasan en todos: ${r.pasan_en_todos} · diferencias entre navegadores: ${r.diferencias} · fallan en todos: ${r.fallan_en_todos}`);
  else console.log(`\nPantallas: ${r.pantallas} · sin diferencias: ${r.sin_diferencias} · con problemas: ${r.con_problemas} · hallazgos: ${r.hallazgos}`);
  console.log(`Datos: ${relRaiz(salida)}`);
  if (generarInforme(carpeta)) console.log(`Informe: ${relRaiz(path.join(carpeta, 'informe-cross-browser.html'))}`);
}

if (require.main === module) {
  main().catch((e) => { console.error(`Error: ${e.message}`); process.exit(1); });
}

module.exports = { argumentos, leerCucumber, analizarSuite, sinAnsi, NOMBRE, GENERADOS };
