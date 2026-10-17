#!/usr/bin/env node
// Lanzador de los conectores MCP playwright y playwright-headless (ver CONECTORES.md).
// Arranca el server oficial de Playwright con la carpeta de evidencias del repo y, si existe el
// .env de la raíz, con --secrets .env: Playwright oculta esos valores (contraseñas, tokens) en
// las respuestas que ve el modelo. Sin .env arranca igual (el server falla si el archivo no existe).
//
// Con SESION en el .env (ver herramientas/k0lmena/tools/login/sesion.js) arranca con la sesión
// guardada por npm run login: --isolated --storage-state .auth/sesion[-<nombre>].json.
//
// Uso (en .mcp.json): node scripts/mcp/playwright.js [--headless]
const fs = require('fs');
const path = require('path');
const { lanzarNpx, RAIZ } = require('./lanzar');
const { variable } = require('./leer-env');
const { sesionActiva } = require('../../herramientas/k0lmena/tools/login/sesion');

const args = ['--output-dir', 'output/ejecuciones/evidencia'];
if (process.argv.includes('--headless')) args.push('--headless');
if (fs.existsSync(path.join(RAIZ, '.env'))) args.push('--secrets', '.env');

let sesion = null;
try {
  sesion = sesionActiva(variable('SESION'), (msg) => console.error(`playwright: ${msg}`));
} catch (e) {
  console.error(`playwright: ${e.message}; se sigue sin sesión.`);
}
if (sesion) {
  // Relativa a la raíz (el server corre ahí) y con /: la línea de npx solo admite rutas simples.
  args.push('--isolated', '--storage-state', path.relative(RAIZ, sesion).split(path.sep).join('/'));
}
lanzarNpx('playwright', '@playwright/mcp', args);
