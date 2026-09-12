import './report-api';
import assert from 'node:assert/strict';
import { renderToStaticMarkup } from 'react-dom/server';
import SourceContent from '../src/components/dashboard/SourceContent';
import PrintModal from '../src/components/dashboard/PrintModal';
import { generateHtml, getAvailableSections } from '../src/utils/htmlExport';
import type { JobDetail } from '../src/types';

const markdown = 'First **important** paragraph.\n\n1. Step one\n2. Step two\n\n```\nconfig system\n    end\n```\n\nLast paragraph.';
const text = 'First important paragraph. Step one Step two config system end Last paragraph.';
const job: JobDetail = {
  id: 'test', from_version: '7.4.10', to_version: '7.4.11', status: 'completed',
  use_selenium: false, created_at: '2026-09-08', versions: ['7.4.11'],
  all_data: {'7.4.11': {
    known_issues: [{category: 'System', 'Bug ID': '123456', Description: text, markdown}],
    'upgrade-information': {title: 'Upgrade information', blocks: [], markdown},
  }}, special_notices: [{title: 'Notice', content: text, markdown}],
};
const screen = renderToStaticMarkup(<SourceContent markdown={markdown} />);
const html = generateHtml(job, new Set(getAvailableSections(job).map(s => s.id)));
assert.ok(html.includes(screen), 'Export must use exactly the screen renderer');
assert.equal(html.split(screen).length - 1, 3, 'Issue, notice and Markdown-only rich section all export');
const print = renderToStaticMarkup(<PrintModal onClose={() => {}} items={[{
  compositeId: 'issues|7.4.11|123456', sectionLabel: 'Known Issues', version: '7.4.11',
  id: '123456', idLabel: 'Bug ID', category: 'System', description: text, markdown,
}]} />);
assert.ok(print.includes(screen), 'Print preview must use exactly the screen renderer');
assert.ok(screen.includes('<ol>') && screen.includes('<strong>important</strong>') && screen.includes('config system\n    end'));
const unsafe = renderToStaticMarkup(<SourceContent markdown={'[bad](javascript:alert(1))\n\n<script>alert(1)</script>'} />);
assert.ok(!unsafe.includes('href="javascript:') && !unsafe.includes('<script>'));
console.log('Content parity: screen, print, export, Markdown-only sections and safe rendering passed.');

const blockSection = {title: 'Fallback section', blocks: [
  {type: 'paragraph' as const, text: 'Keep this warning.', bold: true},
  {type: 'code' as const, text: 'config system\n    end'},
]};
job.all_data!['7.4.11']['fallback-section'] = blockSection;
const fallbackHtml = generateHtml(job, new Set(['ext:fallback-section']));
assert.ok(fallbackHtml.includes('<strong>Keep this warning.</strong>'));
assert.ok(fallbackHtml.includes('config system\n    end'));

import { sourceRowId } from '../src/utils/sourceRowId';
const original = {'Bug ID': '123', Description: 'OK', category: 'System'};
const identity = sourceRowId('known_issues', '7.4.11', original);
assert.notEqual(identity, sourceRowId('known_issues', '7.4.11', {...original, category: 'VPN'}));
assert.notEqual(identity, sourceRowId('known_issues', '7.4.11', {...original, Description: 'Different text'}));
assert.equal(identity, sourceRowId('known_issues', '7.4.11', {...original}));

job.all_data!['7.4.11']['saml-test'] = {title: 'SAML certificate verification', blocks: [], markdown: 'Complete text.'};
assert.equal(getAvailableSections(job).find(s => s.id === 'ext:saml-test')?.label, 'SAML certificate verification');

import { SourceBlocks } from '../src/components/dashboard/SourceContent';
const ordered = [{type: 'list' as const, ordered: true, start: 3, items: ['Third step', 'Fourth step']}];
const orderedScreen = renderToStaticMarkup(<SourceBlocks blocks={ordered} />);
assert.ok(orderedScreen.includes('<ol start="3">'));
job.all_data!['7.4.11']['ordered-section'] = {title: 'Ordered instructions', blocks: ordered};
assert.ok(generateHtml(job, new Set(['ext:ordered-section'])).includes(orderedScreen));

// Exercise the actual exported search renderer against its embedded search data.
import { runInNewContext } from 'node:vm';
const exportWithDuplicates = {...job, all_data: {'7.4.11': {known_issues: [
  {...original, markdown}, {...original, category: 'VPN', markdown},
]}}};
const duplicateHtml = generateHtml(exportWithDuplicates, new Set(['issues']));
const indexJson = duplicateHtml.match(/const _searchIndex = (.*);/)![1];
const index = JSON.parse(indexJson);
assert.equal(new Set(index.map((row: {compositeId: string}) => row.compositeId)).size, 2);
assert.equal(index[0].descHtml, screen);
const renderFunction = duplicateHtml.slice(duplicateHtml.indexOf('function _renderGlobalResults'), duplicateHtml.indexOf('// ── Rich-section version selector'));
const resultBody = {innerHTML: ''};
runInNewContext(renderFunction + '\n_renderGlobalResults(items);', {
  items: index, _sel: new Map(), _escHtml: (value: unknown) => String(value),
  document: {getElementById: () => resultBody},
});
assert.ok(resultBody.innerHTML.includes(screen), 'Downloaded HTML search retains shared formatted content');

import SpecialNotices from '../src/components/dashboard/SpecialNotices';
const versionedNotices = {...job, special_notices: [
  {version: '7.2.8', title: 'Shared title', content: 'Earlier instructions'},
  {version: '7.4.11', title: 'Shared title', content: 'Later instructions'},
]};
for (const rendered of [renderToStaticMarkup(<SpecialNotices job={versionedNotices} />), generateHtml(versionedNotices, new Set(['notices']))]) {
  for (const expected of ['7.2.8', '7.4.11', 'Earlier instructions', 'Later instructions']) assert.ok(rendered.includes(expected));
  assert.equal(rendered.split('Shared title').length - 1, 2);
}

assert.ok(html.includes('<h2 class="print-section-title">Special Notices</h2>'));
assert.ok(html.includes('<p class="print-version-label">FortiOS 7.4.11</p>'));

const mergedTable = {type: 'table' as const, headers: ['Device', 'Upgrade'],
  rows: [['Individual devices', 'Manual'], ['', 'Automatic']], rowSpans: [[2,1],[0,1]]};
const mergedMarkup = renderToStaticMarkup(<SourceBlocks blocks={[mergedTable]} />);
assert.ok(mergedMarkup.includes('rowspan="2">Individual devices</td>'));
assert.equal(mergedMarkup.split('<td').length - 1, 3);
job.all_data!['7.4.11']['merged-upgrade'] = {title:'Upgrade options',blocks:[mergedTable]};
assert.ok(generateHtml(job, new Set(['ext:merged-upgrade'])).includes(mergedMarkup));

const webMerged = {...mergedTable, cellMarkdown: [['Individual **devices**', '`manual`'], ['', '[Automatic](https://example.com/auto)']]};
const webMergedMarkup = renderToStaticMarkup(<SourceBlocks blocks={[webMerged]} />);
assert.ok(webMergedMarkup.includes('<strong>devices</strong>'));
assert.ok(webMergedMarkup.includes('<code>manual</code>'));
assert.ok(webMergedMarkup.includes('href="https://example.com/auto"'));
assert.ok(webMergedMarkup.includes('rowspan="2"'));

const cellContent = '- First item\n- Second item\n\n```\nconfig system\n    end\n```';
const complexCell = renderToStaticMarkup(<SourceBlocks blocks={[{type:'table',rows:[['First item Second item config system end']],cellMarkdown:[[cellContent]]}]} />);
assert.equal(complexCell.split('<li>').length - 1, 2);
assert.ok(complexCell.includes('<pre><code>config system\n    end'));

const nestedSource = renderToStaticMarkup(<SourceBlocks blocks={[{type:'list',ordered:true,items:['Step one'],itemBlocks:[[
  {type:'paragraph',text:'Step one'},
  {type:'table',rows:[['Nested']],cellBlocks:[[[{type:'code',text:'config system\n    end'},{type:'list',items:['Nested item']}]]]},
]]}]} />);
assert.equal(nestedSource.split('<table>').length-1,1);
assert.equal(nestedSource.split('<pre>').length-1,1);
assert.equal(nestedSource.split('<li>').length-1,2);

// Config analysis never returns identifiers or secrets; unused definitions are not evidence.
import { analyzeConfig, relevance } from '../src/config/analyze';
const config = `#config-version=FGT-secret-identifier
config system sdwan
 set status enable
 config members
  edit 1
   set interface "port one"
  next
 end
end
config vpn ipsec phase1-interface
 edit "secret-tunnel-name"
  set psksecret ENC sensitive-value
  set status disable
 next
end
config antivirus profile
 edit "unused-sensitive-name"
 next
end
config system ha
 set mode a-p
end`;
const profile = analyzeConfig(config);
assert.equal(profile['SD-WAN'], 'configured');
assert.equal(profile['IPsec VPN'], 'disabled');
assert.equal(profile['Security profiles'], 'unknown');
assert.equal(profile.HA, 'configured');
assert.equal(Object.keys(profile).length, 8);
assert.ok(!JSON.stringify(profile).match(/secret|sensitive|port one/));
assert.equal(relevance('SD-WAN member issue', profile).length, 1);
assert.equal(relevance('IPsec issue', profile).length, 0);
assert.throws(() => analyzeConfig('ENCRYPTED_SECRET_DATA'));
assert.throws(() => analyzeConfig('config system sdwan\n set status enable'));
assert.throws(() => analyzeConfig('config system sdwan\n execute reboot\nend'));
assert.equal(analyzeConfig('config vdom\n edit "private-name"\n config router bgp\n set as 65000\n end\n next\nend').BGP, 'configured');
assert.equal(analyzeConfig('config system virtual-wan-link\n set status disable\nend')['SD-WAN'], 'disabled');
const annotated = generateHtml({...job, localRelevance: {...profile, 'Security profiles': 'configured'}, all_data: {'7.4.11': {known_issues: [{category: 'SD-WAN', 'Bug ID': '42', Description: 'SD-WAN original text.'}]}}}, new Set(['issues']));
assert.ok(annotated.includes('Potentially relevant'));
assert.ok(annotated.includes('SD-WAN original text.'));
assert.ok(!annotated.includes('sensitive-value'));
const imageHtml = renderToStaticMarkup(<SourceContent markdown={'![external](https://untrusted.example/tracker)'} />);
assert.ok(!imageHtml.includes('<img'));
console.log('Config privacy and relevance checks passed');

// Selection errors are shown before transferring bytes; deployment limits drive the UI.
import { validatePdfSelection, pdfVersion } from '../src/utils/pdfSelection';
const uploadLimits = {max_files: 4, max_file_bytes: 50 * 1024**2, max_total_bytes: 150 * 1024**2};
const pdf = (version: string, mib = 1) => ({name: `fortios-v${version}-release-notes.pdf`, size: mib * 1024**2});
assert.equal(validatePdfSelection([pdf('7.2.8'), pdf('7.2.9'), pdf('7.4.3'), pdf('7.4.11')], uploadLimits), undefined);
assert.match(validatePdfSelection([pdf('7.2.8'), pdf('7.2.8')], uploadLimits)!, /one PDF/);
assert.match(validatePdfSelection([pdf('7.2.8', 51)], uploadLimits)!, /50 MiB/);
assert.match(validatePdfSelection(['7.2.8','7.2.9','7.4.3','7.4.11'].map(v => pdf(v, 40)), uploadLimits)!, /150 MiB/);
assert.match(validatePdfSelection([pdf('7.2.8', 0)], uploadLimits)!, /empty/);
assert.match(validatePdfSelection([{name: 'release.pdf', size: 100}], uploadLimits)!, /filename/);
assert.equal(pdfVersion('v123.4.11.pdf'), null);
assert.match(validatePdfSelection([pdf('7.2.8'),pdf('7.2.9')], {...uploadLimits, max_files: 1})!, /at most 1/);
console.log('PDF selection limits and duplicate/version validation passed');

import { localDateTime } from '../src/utils/dateTime';
assert.equal(localDateTime('2026-09-10T12:00:00'), localDateTime('2026-09-10T12:00:00Z'));
assert.equal(localDateTime('2026-09-10T08:00:00-04:00'), localDateTime('2026-09-10T12:00:00Z'));

// PDF checklist range rules must match scrape semantics and never invent releases.
import { pdfCatalog, pdfReleaseRange } from '../src/utils/pdfReleaseRange';
assert.deepEqual(pdfReleaseRange('7.4.9', '7.4.12').map(r => r.version), ['7.4.10', '7.4.11', '7.4.12']);
assert.deepEqual(pdfReleaseRange('7.6.3', '7.6.6', true).map(r => r.version), ['7.6.3', '7.6.4', '7.6.5', '7.6.6']);
assert.deepEqual(pdfReleaseRange('7.4.11', '7.6.1').map(r => r.version), ['7.4.12', '7.6.0', '7.6.1']);
assert.deepEqual(pdfReleaseRange(' 7.6.5 ', '7.6.6').map(r => r.version), ['7.6.6']);
for (const [from, to] of [['7.6.6', '7.6.5'], ['7.6.6', '7.6.6'], ['7.6.6', '7.6.999'], ['7.5.0', '7.6.6'], ['<script>', '7.6.6'], ['7.6', '7.6.6']]) {
  assert.throws(() => pdfReleaseRange(from, to));
}
assert.equal(new Set(pdfCatalog.releases.map(r => r.version)).size, pdfCatalog.releases.length);
assert.ok(pdfCatalog.releases.every(r => r.url.startsWith(`https://docs.fortinet.com/document/fortigate/${r.version}/fortios-release-notes/`)));
console.log('PDF range: numeric sorting, baseline inclusion, cross-branch selection, invalid/unknown versions and official links passed.');

import {reviewPackageHtml} from '../src/utils/reviewExport';
import type {ReviewDetail} from '../src/reviews';
import ReviewSource from '../src/components/ReviewSource';
const reviewFixture: ReviewDetail = {
  id: 'review', title: '</title><script>alert(1)</script>', customer: 'Example', site: 'Branch', prepared_by: 'Engineer',
  summary: 'Summary <script>inert</script>', rollback_notes: 'Restore backup', revision: 1,
  expected_versions: ['7.4.10', '7.4.11'], created_at: '2026-09-10', updated_at: '2026-09-10',
  job_ids: ['test'], jobs: [job], decisions: {finding: {status: 'needs_testing', note: 'Check failover <img src=x onerror=alert(1)>', reviewed_by: 'Named reviewer', updated_at: '2026-09-11T12:00:00'}},
  checklist: [{id: 'test', phase: 'before', text: 'Verify backup', done: false}],
  missing_versions: ['7.4.10'], unavailable_job_ids: [],
  findings: [{id: 'finding', job_id: 'test', version: '7.4.11', section: 'known_issues', source: {Description: text, markdown}}],
};
const reviewHtml = reviewPackageHtml(reviewFixture);
assert.ok(reviewHtml.includes(renderToStaticMarkup(<ReviewSource source={reviewFixture.findings[0].source} />)));
assert.ok(reviewHtml.includes('Named reviewer'));
assert.ok(reviewHtml.includes('Needs testing') && reviewHtml.includes('Restore backup') && reviewHtml.includes('Missing expected versions: 7.4.10'));
assert.ok(!reviewHtml.includes('<script>') && !reviewHtml.includes('<img'));
assert.ok(reviewHtml.includes('default-src &#x27;none&#x27;') || reviewHtml.includes("default-src 'none'"));
console.log('Review export preserves source renderer, reviewer annotations, completeness and inert user input.');

// Processing progress must use UTC timestamps, stop at completion, and reset on retry.
import {elapsedSeconds, pdfProgress, duration} from '../src/utils/jobProgress';
import PdfProcessingProgress from '../src/components/PdfProcessingProgress';
const progressJob = {id: 'progress', source: 'pdf' as const, from_version: '7.4.1', to_version: '7.4.2', use_selenium: false,
  status: 'running' as const, created_at: '2026-09-11T10:00:00', started_at: '2026-09-11T10:01:00',
  file_outcomes: [{name: 'one.pdf', status: 'completed'}, {name: 'two.pdf', status: 'running', progress: {phase: 'reading', pages_done: 5, total_pages: 10}}]};
assert.equal(elapsedSeconds(progressJob, Date.parse('2026-09-11T10:02:01Z')), 61);
assert.equal(duration(3661), '1:01:01');
assert.equal(pdfProgress(progressJob).percent, 70);
assert.match(pdfProgress(progressJob).label, /Reading page 6 of 10/);
assert.equal(elapsedSeconds({...progressJob, status: 'cancelled', completed_at: '2026-09-11T10:01:20'}, Date.now()), 20);
assert.equal(pdfProgress({...progressJob, status: 'pending', started_at: undefined}).percent, 50);
assert.equal(pdfProgress({...progressJob, status: 'completed'}).percent, 100);
assert.match(renderToStaticMarkup(<PdfProcessingProgress job={progressJob} />), /role="progressbar"/);
assert.equal(validatePdfSelection(Array.from({length: 6}, (_, i) => ({name: `v7.4.${i}.pdf`, size: 100})), {max_files: 100, max_file_bytes: 1000, max_total_bytes: 10000}), undefined);

import {reviewVersionRange} from '../src/utils/reviewVersionRange';
assert.deepEqual(reviewVersionRange('7.6.3','7.6.6',false), ['7.6.4','7.6.5','7.6.6']);
assert.deepEqual(reviewVersionRange('7.6.3','7.6.6',true), ['7.6.3','7.6.4','7.6.5','7.6.6']);
assert.deepEqual(reviewVersionRange('7.6.6','7.6.6',false), ['7.6.6']);
assert.deepEqual(reviewVersionRange('','',false), []);
assert.throws(()=>reviewVersionRange('7.6.6','7.6.3',false), /newer/);
assert.throws(()=>reviewVersionRange('7.6.6','8.0.999',false), /catalog/);

// Per-document timing distinguishes queued work, completed attempts and unknown history.
import {fileTime, filePages} from '../src/utils/pdfFileMetrics';
import PdfFileList from '../src/components/PdfFileList';
const measuredFile = {name: 'release.pdf', status: 'completed', elapsed_seconds: 125, page_count: 17};
assert.equal(fileTime(measuredFile, false, Date.now()), '02:05');
assert.equal(fileTime({...measuredFile, status:'running', started_at:'2026-09-11T12:00:00Z', elapsed_seconds:0},true,Date.parse('2026-09-11T12:00:07Z')), 'Elapsed 00:07');
assert.equal(fileTime({name:'old',status:'completed'},false,Date.now()), 'Time not recorded');
assert.equal(fileTime({name:'pending',status:'pending'},false,Date.now()), 'Waiting to start');
assert.equal(fileTime({name:'stopped',status:'failed',not_processed:true},false,Date.now()), 'Not processed');
assert.equal(fileTime({...measuredFile,duration_is_partial:true},false,Date.now()), 'At least 02:05');
assert.equal(filePages(measuredFile), '17 pages');
assert.equal(filePages({name:'x',status:'completed',page_count:1}), '1 page');
assert.equal(filePages({name:'x',status:'completed'}), 'Page count unavailable');
const documentList = renderToStaticMarkup(<PdfFileList files={[measuredFile, {...measuredFile,name:'failed.pdf',status:'failed',error:'Invalid PDF'}]} jobStatus="partial"/>);
assert(documentList.includes('aria-label="Completed"'));
assert(documentList.includes('aria-label="Not completed"'));
assert(documentList.includes('02:05') && documentList.includes('17 pages'));
console.log('Per-document time, page counts and accessible success/failure indicators passed.');

import "./consolidation";
