const KEY = 'fgt-pdf-timeout-minutes';
export function readPdfTimeout(): string {
  try { return localStorage.getItem(KEY) || ''; } catch { return ''; }
}
export function savePdfTimeout(value: string) {
  if (!value) { localStorage.removeItem(KEY); return; }
  const minutes = Number(value);
  if (!Number.isInteger(minutes) || minutes < 1) throw new Error('Invalid timeout');
  localStorage.setItem(KEY, String(minutes));
}
export function pdfTimeoutHeaders(): Record<string, string> {
  const value = readPdfTimeout();
  return value ? {'X-PDF-Timeout-Minutes': value} : {};
}
