import assert from 'node:assert/strict';
import { groupRows, groupNotices, richGroups, rowIds } from '../src/utils/consolidation';
import { generateHtml } from '../src/utils/htmlExport';
import { toTXT } from '../src/components/dashboard/ExportButton';
import type { JobDetail } from '../src/types';
const base = {'Bug ID': '90001', category: 'System', Description: 'Retain **source** text.', markdown: 'Retain **source** text.'};
const rows = [{...base, _version: '8.4.9'}, {...base, _version: '8.4.10'}, {...base, _version: '8.4.10'}];
const original = JSON.stringify(rows);
assert.equal(groupRows(rows, false).length, 3, 'Off retains even duplicates within one build');
const merged = groupRows(rows, true);
assert.equal(merged.length, 1);
assert.deepEqual(merged[0]._versions, ['8.4.9', '8.4.10']);
assert.equal(rowIds('known_issues', merged[0]).length, 2, 'Group selection targets original source identities once');
assert.equal(JSON.stringify(rows), original, 'Grouping never mutates source rows');
assert.equal(groupRows([...rows,
  {...rows[0], Description: 'Changed text'}, {...rows[0], category: 'VPN'},
  {...rows[0], markdown: 'Retain source text.'}, {...rows[0], 'Bug ID': '90002'}], true).length, 5);
const section = {title: 'Future guidance', blocks: [{type: 'paragraph' as const, text: 'Repeated warning.'}, {type: 'paragraph' as const, text: 'Repeated warning.'}]};
const notice = {title: 'Warning', content: 'Retain this warning.'};
const job: JobDetail = {id: 'fixture', status: 'completed', from_version: '8.4.9', to_version: '8.4.10', use_selenium: false, created_at: '2026-09-11', versions: ['8.4.9','8.4.10'], all_data: {
  '8.4.9': {known_issues: [base], 'resolved-issues': [base], changes_cli: [base], new_features: [{...base, 'Feature ID': '90001'}], guidance: section},
  '8.4.10': {known_issues: [base, base], 'resolved-issues': [base], changes_cli: [base], new_features: [{...base, 'Feature ID': '90001'}], guidance: section}},
  special_notices: [{...notice,version:'8.4.9'},{...notice,version:'8.4.10'}]};
assert.equal(groupNotices(job.special_notices!, false).length, 2);
assert.equal(groupNotices(job.special_notices!, true).length, 1);
assert.equal(richGroups(job, 'guidance', true).length, 1);
assert.equal(richGroups(job, 'guidance', true)[0].item.section.blocks.length, 2, 'Do not remove repeated paragraphs within a chapter');
const selected = new Set(['issues','resolved','cli','features','notices','ext:guidance']);
const off = generateHtml(job, selected);
const on = generateHtml({...job, localConsolidation: ['known_issues','changes_cli','new_features','special_notices','guidance']}, selected);
const countRows = (html: string, tab: string) => html.split(`id="${tab}-table"`)[1].split('</table>')[0].split('<tr data-version=').length - 1;
assert.equal(countRows(off,'issues'),3);
assert.equal(countRows(on,'issues'),1);
assert.equal(countRows(on,'resolved'),2,'An unchecked section remains expanded');
assert.equal(countRows(on,'cli'),1);
assert.equal(countRows(on,'features'),1);
assert.ok(on.includes('8.4.9, 8.4.10'));
assert.equal((off.match(/class="notice-card"/g) ?? []).length,2);
assert.equal((on.match(/class="notice-card"/g) ?? []).length,1);
assert.equal((off.match(/class="ext-rich-ver"/g) ?? []).length,2);
assert.equal((on.match(/class="ext-rich-ver"/g) ?? []).length,1);
assert.equal((on.match(/Repeated warning\./g) ?? []).length,2);
console.log('Consolidation: default off, exact matches, source selection, per-section exports, notices and rich source text passed.');

const builds = Array.from({length: 19}, (_, i) => `8.4.${i}`).join(', ');
assert.ok(toTXT([{Builds: builds}], ['Builds']).includes(builds), 'TXT export retains the entire build list');
