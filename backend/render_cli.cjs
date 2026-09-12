'use strict';
const fs = require('node:fs');
const {render} = require('../frontend/dist/server-renderer.cjs');
try {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  process.stdout.write(JSON.stringify({result: render(input)}));
} catch (error) {
  process.stdout.write(JSON.stringify({error: error instanceof Error ? error.message : 'Unable to render report'}));
  process.exitCode = 2;
}
