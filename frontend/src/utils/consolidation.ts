import type { JobDetail, Notice, RichSection } from '../types';
import { sourceRowId } from './sourceRowId';

/** Object-key order is irrelevant; array order, text and formatting are not. */
export function contentKey(value: unknown): string {
  if (Array.isArray(value)) return '[' + value.map(contentKey).join(',') + ']';
  if (value && typeof value === 'object') return '{' + Object.entries(value)
    .filter(([, v]) => v !== undefined).sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => JSON.stringify(k) + ':' + contentKey(v)).join(',') + '}';
  return JSON.stringify(value) ?? 'null';
}
export function groupContent<T>(items: T[], enabled: boolean, version: (item: T) => string, identity: (item: T, index: number) => unknown) {
  const groups: { item: T; versions: string[]; members: T[] }[] = [];
  const seen = new Map<string, (typeof groups)[number]>();
  for (const [index, item] of items.entries()) {
    const key = enabled ? contentKey(identity(item, index)) : '';
    let group = enabled ? seen.get(key) : undefined;
    if (!group) {
      group = {item, versions: [], members: []}; groups.push(group);
      if (enabled) seen.set(key, group);
    }
    const build = version(item);
    if (build && !group.versions.includes(build)) group.versions.push(build);
    group.members.push(item);
  }
  return groups;
}
export function groupRows<T extends {_version: string}>(rows: T[], enabled: boolean) {
  return groupContent(rows, enabled, r => r._version, r => {
    const {_version, ...content} = r; return content;
  }).map(g => ({...g.item, _versions: g.versions, _members: g.members}));
}
export function rowIds<T extends {_version: string; Description: string}>(section: string, row: T & {_members?: T[]}) {
  return [...new Set((row._members ?? [row]).map(member => sourceRowId(section, member._version, member)))];
}
export function groupNotices(notices: Notice[], enabled: boolean) {
  return groupContent(notices, enabled, n => n.version ?? '', n => {
    const {version, ...content} = n; return content;
  });
}
export function richGroups(job: JobDetail, key: string, enabled: boolean) {
  const entries = (job.versions ?? []).flatMap(version => {
    const section = job.all_data?.[version]?.[key] as RichSection | undefined;
    return section?.markdown || section?.blocks?.length ? [{version, section}] : [];
  });
  return groupContent(entries, enabled, e => e.version, e => e.section);
}
export function consolidationKeys(job: JobDetail) {
  return [...new Set(['special_notices', ...(job.versions ?? []).flatMap(v =>
    Object.keys(job.all_data?.[v] ?? {}).filter(k => !k.startsWith('_')))])];
}
