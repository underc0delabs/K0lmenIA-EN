// Regenera los recursos de la documentación de k0lmenIA:
//   docs/assets/img/arquitectura.png  ← docs/diagramas/arquitectura.html
//   docs/assets/img/relaciones.png    ← docs/diagramas/relaciones.html
//   docs/assets/img/uso.png           ← docs/diagramas/uso.html
//   docs/assets/img/puesta-en-marcha.png ← docs/diagramas/puesta-en-marcha.html
//   docs/k0lmenIA-documentacion.pdf   ← docs/index.html (estilos de impresión)
//
// Uso, desde la raíz del repo (con k0lmena instalado: usa su Playwright):
//   node docs/generar.js
const path = require('path');
const { pathToFileURL } = require('url');

const k0lmena = path.resolve(__dirname, '../herramientas/k0lmena');
let chromium;
try {
  ({ chromium } = require(require.resolve('playwright', { paths: [k0lmena] })));
} catch {
  console.error('Falta Playwright: corré "npm install" y "npx playwright install chromium" en herramientas/k0lmena.');
  process.exit(1);
}

// Encabezado o pie del PDF: ocupa todo el margen con el fondo noche (#0E0C09) de k0lmena.
// Los márgenes de @page (docs/assets/estilos.css) son 13 mm arriba y 15 mm abajo. Chromium dibuja la
// plantilla a ~5 mm del borde de la hoja (medido: 5,0 arriba y 5,5 abajo): la parte visible mide el
// margen menos eso, y el fondo se estira 7 mm hacia afuera (arriba en el encabezado, abajo en el pie)
// para llegar al borde sin tapar el contenido.
const BORDE_ARRIBA = 5.0;
const BORDE_ABAJO = 5.5;
const EXTRA = '7mm';
const MARGEN = (contenido, alto, arriba) =>
  '<style>html,body{margin:0;padding:0;-webkit-print-color-adjust:exact;print-color-adjust:exact}</style>' +
  `<div style="width:100%;margin:${arriba ? `-${EXTRA} 0 0` : `0 0 -${EXTRA}`};padding:${arriba ? `${EXTRA} 0 0` : `0 0 ${EXTRA}`};background:#0E0C09">` +
  `<div style="height:${alto}">${contenido}</div></div>`;

const url = (archivo) => pathToFileURL(path.join(__dirname, archivo)).href;
const ruta = (archivo) => path.join(__dirname, archivo);

(async () => {
  const navegador = await chromium.launch();

  // Diagramas → PNG (2x para que se lean bien en pantallas de alta densidad)
  const lienzo = await navegador.newPage({ viewport: { width: 1900, height: 1200 }, deviceScaleFactor: 2 });
  for (const nombre of ['arquitectura', 'relaciones', 'uso', 'puesta-en-marcha']) {
    await lienzo.goto(url(`diagramas/${nombre}.html`));
    await lienzo.locator('#captura').screenshot({ path: ruta(`assets/img/${nombre}.png`) });
    console.log(`docs/assets/img/${nombre}.png`);
  }

  // Sitio → PDF
  const pagina = await navegador.newPage();
  await pagina.goto(url('index.html'), { waitUntil: 'networkidle' });
  await pagina.emulateMedia({ media: 'print' });
  await pagina.pdf({
    path: ruta('k0lmenIA-documentacion.pdf'),
    printBackground: true,
    preferCSSPageSize: true,
    displayHeaderFooter: true,
    // Chromium no pinta el fondo de la página en los márgenes de @page (quedan grises): el encabezado
    // y el pie, que se dibujan en esos márgenes, los cubren con el fondo de k0lmena.
    headerTemplate: MARGEN('', `${13 - BORDE_ARRIBA}mm`, true),
    footerTemplate: MARGEN(
      '<div style="height:100%;display:flex;align-items:center;justify-content:space-between;padding:0 15mm;' +
      'font:9px Consolas,\'Cascadia Mono\',monospace;color:#8A8172">' +
      '<span><span style="color:#F9B006">//</span> k0lmenIA · documentación</span>' +
      '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>', `${15 - BORDE_ABAJO}mm`, false),
  });
  console.log('docs/k0lmenIA-documentacion.pdf');
  await navegador.close();
})();
