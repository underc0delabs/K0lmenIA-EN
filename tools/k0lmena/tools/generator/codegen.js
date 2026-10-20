#!/usr/bin/env node
/**
 * tools/generator/codegen.js
 *
 * Reads the APP_URL URL from the .env at the project root
 * and launches playwright codegen pointing at that URL.
 */

const { execSync } = require('child_process');
require('dotenv').config();  // loads .env from process.cwd()

// 1️⃣ Get the URL from .env
const url = process.env.BASEURL;
if (!url) {
  console.error('⚠️ ERROR: The APP_URL variable is not defined in your .env');
  process.exit(1);
}

// 2️⃣ Call parameters
const outputPath = 'tools/generator/gen.ts';
const target     = 'javascript';

// 3️⃣ Build and run the command
const cmd = `npx playwright codegen ${url} --target=${target} --output=${outputPath}`;
console.log(`\n⚡️ Running: ${cmd}\n`);
try {
  execSync(cmd, { stdio: 'inherit' });
} catch (e) {
  console.error('\n❌ Playwright Codegen run failed\n', e.message);
  process.exit(1);
}
