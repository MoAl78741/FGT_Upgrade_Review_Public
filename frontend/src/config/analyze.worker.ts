import { analyzeConfig } from './analyze';
self.onmessage = (event: MessageEvent<string>) => {
  try { self.postMessage({ profile: analyzeConfig(event.data) }); }
  catch (error) { self.postMessage({ error: error instanceof Error ? error.message : 'Unable to analyze this configuration.' }); }
};
