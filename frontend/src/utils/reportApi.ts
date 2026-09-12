import type {JobDetail} from '../types';
import {groupContent, consolidationKeys} from './consolidation';
import {generateHtml, getAvailableSections} from './htmlExport';

export interface SourceCoordinate {version: string; section: string; index: number}
export interface ReportOptions {
  sections?: string[]; versions?: string[]; search?: string; category?: string;
  consolidate?: string[]; consolidate_all?: boolean; selection?: SourceCoordinate[] | null;
}
interface Entry {source: Record<string, unknown>; coordinate: SourceCoordinate}
export function reportEntries(job: JobDetail): Entry[] {
  const entries: Entry[] = [];
  for (const version of job.versions ?? []) for (const [section, data] of Object.entries(job.all_data?.[version] ?? {})) {
    if (section.startsWith('_')) continue;
    const rows = Array.isArray(data) ? data : data && typeof data === 'object' ? [data] : [];
    rows.forEach((source, index) => entries.push({source: {...source}, coordinate: {version, section, index}}));
  }
  (job.special_notices ?? []).forEach((source, index) => entries.push({source: {...source}, coordinate: {version: source.version ?? '', section: 'special_notices', index}}));
  return entries;
}
const coordinateKey = (c: SourceCoordinate) => JSON.stringify([c.version,c.section,c.index]);
export function filteredEntries(job: JobDetail, options: ReportOptions): Entry[] {
  const selected = options.selection == null ? null : new Set(options.selection.map(coordinateKey));
  const query = options.search?.toLowerCase();
  return reportEntries(job).filter(({source, coordinate: c}) =>
    (!options.sections?.length || options.sections.includes(c.section)) &&
    (!options.versions?.length || options.versions.includes(c.version)) &&
    (!selected || selected.has(coordinateKey(c))) &&
    (!options.category || source.category === options.category) &&
    (!query || `${c.version} ${c.section} ${JSON.stringify(source)}`.toLowerCase().includes(query)));
}
export function reportView(job: JobDetail, options: ReportOptions = {}) {
  const entries = filteredEntries(job, options);
  const grouped = groupContent(entries, true, e => e.coordinate.version, (e, index) => {
    if (!options.consolidate_all && !options.consolidate?.includes(e.coordinate.section)) return ['occurrence', index];
    const source = {...e.source};
    if (e.coordinate.section === 'special_notices') delete source.version;
    return [e.coordinate.section, source];
  });
  return {job_id: job.id, source_count: entries.length, count: grouped.length,
    sections: consolidationKeys(job),
    entries: grouped.map(g => ({section: g.item.coordinate.section, builds: g.versions, source: g.item.source, selection: g.members.map(e => e.coordinate)}))};
}
export function reportHtml(job: JobDetail, options: ReportOptions = {}) {
  const entries = filteredEntries(job, options);
  const selection = new Set(entries.map(e => coordinateKey(e.coordinate)));
  const copy: JobDetail = {...job, versions: (job.versions ?? []).filter(v => !options.versions?.length || options.versions.includes(v)),
    all_data: {}, special_notices: [], localConsolidation: options.consolidate_all ? consolidationKeys(job) : options.consolidate ?? []};
  for (const version of copy.versions!) {
    const data: Record<string, any> = {};
    for (const [section, value] of Object.entries(job.all_data?.[version] ?? {})) {
      if (section.startsWith('_')) {data[section] = value; continue;}
      const has = (index: number) => selection.has(coordinateKey({version, section, index}));
      if (Array.isArray(value)) data[section] = value.filter((_, i) => has(i));
      else if (has(0)) data[section] = value;
    }
    copy.all_data![version] = data;
  }
  copy.special_notices = (job.special_notices ?? []).filter((n, index) => selection.has(coordinateKey({version:n.version ?? '',section:'special_notices',index})));
  return generateHtml(copy, new Set(getAvailableSections(copy).map(s => s.id)));
}
export function reportDelimited(job: JobDetail, options: ReportOptions, delimiter = ',') {
  const esc = (value: unknown) => `"${String(value ?? '').replace(/"/g, '""')}"`;
  return [['Section','Builds','Category','ID','Description'], ...reportView(job, options).entries.map(e => [
    e.section, e.builds.join(', '), e.source.category ?? '', e.source['Bug ID'] ?? e.source['Feature ID'] ?? '',
    e.source.Description ?? e.source.content ?? e.source.markdown ?? JSON.stringify(e.source.blocks ?? e.source),
  ])].map(row => row.map(esc).join(delimiter)).join('\n');
}
