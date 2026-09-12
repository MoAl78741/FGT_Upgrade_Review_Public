const {createRequire} = require('node:module');
const {mkdtempSync, rmSync} = require('node:fs');
const {join} = require('node:path');
const {tmpdir} = require('node:os');
const {execFileSync} = require('node:child_process');
const esbuild = require('esbuild');
const dir = mkdtempSync(join(tmpdir(), 'fgt-content-test-'));
try {
  const out = join(dir, 'test.cjs');
  esbuild.buildSync({entryPoints: [join(__dirname, 'content-parity.tsx')], bundle: true, loader: {'.woff2': 'dataurl'}, platform: 'node', outfile: out, jsx: 'automatic'});
  execFileSync(process.execPath, [out], {stdio: 'inherit'});
} finally { rmSync(dir, {recursive: true, force: true}); }
