import catalog from '../data/pdfReleases.json';

export const pdfCatalog = catalog;
export const compareVersions = (a: string, b: string) => {
  const left = a.split('.').map(Number), right = b.split('.').map(Number);
  return left[0] - right[0] || left[1] - right[1] || left[2] - right[2];
};

export function pdfReleaseRange(from: string, to: string, includeFrom = false) {
  const start = from.trim(), end = to.trim();
  const valid = /^(0|[1-9]\d?)\.(0|[1-9]\d?)\.(0|[1-9]\d{0,2})$/;
  if (!valid.test(start) || !valid.test(end)) throw new Error('Enter both versions as major.minor.patch, for example 7.6.3.');
  if (compareVersions(start, end) >= 0) throw new Error('To version must be newer than From version.');
  for (const version of [start, end]) {
    if (!catalog.releases.some(r => r.version === version)) {
      throw new Error(`Version ${version} is not in the bundled catalog (checked ${catalog.checked_at}). Check Fortinet’s library; you can still upload its PDF below.`);
    }
  }
  return catalog.releases.filter(r => (includeFrom ? compareVersions(r.version, start) >= 0 : compareVersions(r.version, start) > 0) && compareVersions(r.version, end) <= 0);
}
