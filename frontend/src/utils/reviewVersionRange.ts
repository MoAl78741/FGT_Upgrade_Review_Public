import {pdfCatalog, pdfReleaseRange} from './pdfReleaseRange';
export function reviewVersionRange(from: string, to: string, includeFrom: boolean): string[] {
  if (!from.trim() && !to.trim()) return [];
  if (from.trim() === to.trim() && pdfCatalog.releases.some(r => r.version === from.trim())) return [from.trim()];
  return pdfReleaseRange(from, to, includeFrom).map(r => r.version);
}
