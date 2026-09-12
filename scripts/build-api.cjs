const path = require('node:path');
const fs = require('node:fs');
const root = path.resolve(__dirname, '..');
const esbuild = require(path.join(root, 'frontend/node_modules/esbuild'));
const output = path.join(root, 'frontend/dist');
fs.mkdirSync(path.join(output, 'api-docs'), {recursive:true});
for (const name of ['swagger-ui.css', 'swagger-ui-bundle.js', 'LICENSE', 'NOTICE']) {
  const source = path.join(root, 'frontend/node_modules/swagger-ui-dist', name);
  if (fs.existsSync(source)) fs.copyFileSync(source, path.join(output, 'api-docs', name));
}
const common = {bundle:true, jsx:'automatic', loader:{'.woff2':'dataurl'}, define:{'process.env.NODE_ENV':'"production"'}};
esbuild.buildSync({...common, entryPoints:[path.join(root,'frontend/src/localApi.ts')], platform:'browser', alias:{'decode-named-character-reference':path.join(root,'frontend/node_modules/decode-named-character-reference/index.js')}, format:'esm', outfile:path.join(output,'assets/local-api.mjs')});
esbuild.buildSync({...common, entryPoints:[path.join(root,'frontend/src/serverRenderer.ts')], platform:'node', format:'cjs', outfile:path.join(output,'server-renderer.cjs')});
