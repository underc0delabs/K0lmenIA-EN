// performance/k6/esbuild.k6.config.mjs
// Compiles the k6 TypeScript scripts (performance/k6/http/*.ts) to performance/k6/dist/.
// Usage: node performance/k6/esbuild.k6.config.mjs [script.ts ...]   (no arguments: all of them)

import { build } from 'esbuild';
import { globby } from 'globby';
import path from 'node:path';
import fs from 'node:fs';

const requested = process.argv.slice(2);
const files = requested.length ? requested : await globby('performance/k6/http/*.ts');

const entries = files.map((f) => ({
  in: f,
  out: path.join('performance/k6/dist', path.relative('performance/k6', f)).replace(/\.ts$/, '.js'),
}));

for (const e of entries) fs.mkdirSync(path.dirname(e.out), { recursive: true });

// Native k6 modules (resolved at runtime) and remote libraries from jslib.k6.io
const K6_EXTERNAL = ['k6', 'k6/*', 'https://*'];

await Promise.all(
  entries.map((e) =>
    build({
      entryPoints: [e.in],
      outfile: e.out,
      bundle: true,
      platform: 'neutral',
      format: 'esm',
      target: ['es2020'],
      sourcemap: false,
      logLevel: 'error',
      external: K6_EXTERNAL,
    }),
  ),
);

console.log(`k6: ${entries.length} script(s) compiled to performance/k6/dist/
`);
