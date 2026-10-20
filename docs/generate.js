// Regenerates the k0lmenIA documentation assets:
//   docs/assets/img/architecture.png   ← docs/diagrams/architecture.html
//   docs/assets/img/relationships.png  ← docs/diagrams/relationships.html
//   docs/assets/img/usage.png          ← docs/diagrams/usage.html
//   docs/assets/img/setup.png          ← docs/diagrams/setup.html
//   docs/k0lmenIA-documentation.pdf    ← docs/index.html (print styles)
//
// Usage, from the repo root (with k0lmena installed: it uses its Playwright):
//   node docs/generate.js
// The cover is generated separately, without header or footer, and replaces the first page with pypdf
// (pip install pypdf). Without pypdf the PDF is still generated, with the footer on the cover too.
const path = require('path');
const { pathToFileURL } = require('url');

const k0lmena = path.resolve(__dirname, '../tools/k0lmena');
let chromium;
try {
  ({ chromium } = require(require.resolve('playwright', { paths: [k0lmena] })));
} catch {
  console.error('Playwright is missing: run "npm install" and "npx playwright install chromium" in tools/k0lmena.');
  process.exit(1);
}

// PDF header or footer: fills the whole margin with k0lmena's night background (#0E0C09).
// The @page margins (docs/assets/styles.css) are 13 mm at the top and 15 mm at the bottom. Chromium draws the
// template ~5 mm from the edge of the sheet (measured: 5.0 at the top and 5.5 at the bottom): the visible part is the
// margin minus that, and the background stretches 7 mm outward (up in the header, down in the footer)
// to reach the edge without covering the content.
const BORDER_TOP = 5.0;
const BORDER_BOTTOM = 5.5;
const EXTRA = '7mm';
const MARGIN = (content, height, top) =>
  '<style>html,body{margin:0;padding:0;-webkit-print-color-adjust:exact;print-color-adjust:exact}</style>' +
  `<div style="width:100%;margin:${top ? `-${EXTRA} 0 0` : `0 0 -${EXTRA}`};padding:${top ? `${EXTRA} 0 0` : `0 0 ${EXTRA}`};background:#0E0C09">` +
  `<div style="height:${height}">${content}</div></div>`;

const url = (file) => pathToFileURL(path.join(__dirname, file)).href;
const filePath = (file) => path.join(__dirname, file);

(async () => {
  const browser = await chromium.launch();

  const PDF = 'k0lmenIA-documentation.pdf';
  const FOOTER = 'documentation';

  // Diagrams → PNG (2x so they read well on high-density screens)
  const canvas = await browser.newPage({ viewport: { width: 1900, height: 1200 }, deviceScaleFactor: 2 });
  require('fs').mkdirSync(filePath('assets/img'), { recursive: true });
  for (const name of ['architecture', 'relationships', 'usage', 'setup']) {
    await canvas.goto(url(`diagrams/${name}.html`));
    await canvas.locator('#capture').screenshot({ path: filePath(`assets/img/${name}.png`) });
    console.log(`docs/assets/img/${name}.png`);
  }

  // Site → PDF
  const page = await browser.newPage();
  await page.goto(url('index.html'), { waitUntil: 'networkidle' });
  await page.emulateMedia({ media: 'print' });
  const final = filePath(PDF);
  const cover = filePath(`.cover-${PDF}`);
  await page.pdf({ path: cover, printBackground: true, preferCSSPageSize: true, pageRanges: '1' });
  await page.pdf({
    path: final,
    printBackground: true,
    preferCSSPageSize: true,
    displayHeaderFooter: true,
    // Chromium doesn't paint the page background in the @page margins (they stay gray): the header
    // and the footer, which are drawn in those margins, cover them with the k0lmena background.
    headerTemplate: MARGIN('', `${13 - BORDER_TOP}mm`, true),
    footerTemplate: MARGIN(
      '<div style="height:100%;display:flex;align-items:center;justify-content:space-between;padding:0 15mm;' +
      'font:9px Consolas,\'Cascadia Mono\',monospace;color:#8A8172">' +
      `<span><span style="color:#F9B006">//</span> k0lmenIA · ${FOOTER}</span>` +
      '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>', `${15 - BORDER_BOTTOM}mm`, false),
  });
  await page.close();
  await browser.close();

  // Cover without footer: replaces the first page (pypdf).
  const py = process.platform === 'win32' ? 'python' : 'python3';
  const merge = [
    'import sys',
    'from pypdf import PdfReader, PdfWriter',
    'final, cover = sys.argv[1], sys.argv[2]',
    'w = PdfWriter(clone_from=final)',
    'w.remove_page(0)',
    'w.insert_page(PdfReader(cover).pages[0], 0)',
    'w.write(final)',
  ].join(String.fromCharCode(10));
  const r = require('child_process').spawnSync(py, ['-c', merge, final, cover], { encoding: 'utf8' });
  if (r.status !== 0) console.log(`(Could not remove the footer from the cover: ${(r.stderr || r.error || '').toString().trim().split(String.fromCharCode(10)).pop()}. Install pypdf.)`);
  require('fs').rmSync(cover, { force: true });
  console.log(`docs/${PDF}`);
})();
