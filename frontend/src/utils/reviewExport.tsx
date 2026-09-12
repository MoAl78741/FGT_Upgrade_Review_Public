import {renderToStaticMarkup} from 'react-dom/server';
import ReviewSource from '../components/ReviewSource';
import {sourceContentCss} from '../components/dashboard/SourceContent';
import {exportFontCss} from '../styles/exportFonts';
import {decisionLabels, type ReviewDetail} from '../reviews';
import {localDateTime} from './dateTime';

export function reviewPackageHtml(review: ReviewDetail): string {
  const body = renderToStaticMarkup(<main>
    <header><p>Upgrade review package · Revision {review.revision}</p><h1>{review.title}</h1><p>{[review.customer, review.site].filter(Boolean).join(' · ')}</p><p>Prepared by: {review.prepared_by || 'Not recorded'} · Updated: {localDateTime(review.updated_at)}</p></header>
    <section><h2>Review summary</h2><p className="source-text">{review.summary || 'No reviewer summary recorded.'}</p><p>{review.findings.length} source findings · {review.findings.filter(f => !review.decisions[f.id] || review.decisions[f.id].status === 'unreviewed').length} unreviewed · {review.checklist.filter(i => i.done).length}/{review.checklist.length} checklist actions complete</p><p>This package records source evidence and reviewer decisions. It does not certify that a firmware upgrade is safe or specify a supported upgrade path.</p></section>
    <section><h2>Evidence and completeness</h2>
      <p>Expected versions: {review.expected_versions.join(', ') || 'Not specified'}</p>
      {!!review.missing_versions.length && <p className="warning">Missing expected versions: {review.missing_versions.join(', ')}</p>}
      {!!review.unavailable_job_ids.length && <p className="warning">{review.unavailable_job_ids.length} source batches are unavailable. Their content is absent from this package.</p>}
      {review.jobs.map(job => <article key={job.id}><h3>{job.versions?.join(', ')} · {job.status}</h3><p>Source: {job.source} · Imported: {localDateTime(job.created_at)} · Parser: {String(job.provenance?.parser_revision ?? 'Not recorded')}</p><p>Document revision: {typeof job.provenance?.document_revision === 'string' ? job.provenance.document_revision : JSON.stringify(job.provenance?.document_revision ?? 'See source change log')}</p>
        {job.warnings?.map((w, i) => <p className="warning" key={i}>{w}</p>)}
        {job.file_outcomes?.map((f, i) => <p key={i}>{String(f.name)}: {String(f.status)} {f.error ? `— ${String(f.error)}` : ''}</p>)}
        {Object.entries(job.all_data ?? {}).map(([version, data]) => <div key={version}><h4>{version}</h4>{data._section_status ? <ul>{Object.entries(data._section_status).map(([section, state]) => <li key={section}>{section.replace(/[-_]/g, ' ')}: {state === 'not_captured' ? 'not captured / not found' : state === 'captured_empty' ? 'captured, no rows' : 'captured'}</li>)}</ul> : <p>Section completeness was not recorded for this source.</p>}</div>)}
      </article>)}
      <p>Missing sections do not establish that no changes exist. All source notices and copyright information remain applicable.</p>
    </section>
    <section><h2>Testing and rollback checklist</h2>{review.checklist.length ? <ul>{review.checklist.map(item => <li key={item.id}>{item.done ? 'Complete' : 'Pending'} · {item.phase}: {item.text}</li>)}</ul> : <p>No test actions recorded.</p>}<h3>Rollback notes</h3><p className="source-text">{review.rollback_notes || 'No rollback notes recorded.'}</p></section>
    <section><h2>Source findings and reviewer annotations</h2>{review.findings.map(f => <article className="finding" key={f.id}>
      <h3>{f.version} · {f.source.title || f.source['Bug ID'] || f.source['Feature ID'] || f.section.replace(/[-_]/g, ' ')}</h3><p>{f.section.replace(/[-_]/g, ' ')}{f.source.category ? ` · ${f.source.category}` : ''} · Source batch: {f.job_id}</p>
      {f.reference && <p>{f.reference.kind === 'pdf' ? `Source PDF: ${f.reference.name || 'Uploaded document'} · ${f.reference.page ? `section begins on page ${f.reference.page}` : 'page not recorded'}` : <a href={f.reference.url} rel="noopener noreferrer">Original web section</a>}</p>}
      <div className="original"><ReviewSource source={f.source} /></div>
      <aside><strong>Reviewer decision: {decisionLabels[review.decisions[f.id]?.status ?? 'unreviewed']}</strong><p className="source-text">{review.decisions[f.id]?.note || 'No reviewer note.'}</p>{review.decisions[f.id]?.updated_at && <p>Saved: {localDateTime(review.decisions[f.id].updated_at!)}{review.decisions[f.id].reviewed_by ? ` · ${review.decisions[f.id].reviewed_by}` : ""}</p>}</aside>
    </article>)}</section>
  </main>);
  const title = renderToStaticMarkup(<title>{review.title}</title>);
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; font-src data:; img-src data:; base-uri 'none'; form-action 'none'">${title}<style>${exportFontCss}\n${sourceContentCss}\nbody{font-family:Outfit,sans-serif;color:#182535;background:#fff;margin:0}main{max-width:1000px;margin:auto;padding:32px}h1{font-size:28px}h2{border-bottom:2px solid #1564a1;padding-bottom:8px;margin-top:32px}h3{margin-top:22px}.finding{margin-bottom:24px;break-inside:avoid}.original{border:1px solid #cbd5e1;padding:14px}aside{border-left:3px solid #1564a1;padding:10px 16px;background:#eff6ff;margin-top:10px}.warning{color:#943500}p,li{line-height:1.5}article,section{overflow-wrap:anywhere}table{table-layout:auto}h2,h3,h4{break-after:avoid}tr,aside{break-inside:avoid}@media print{@page{size:A4;margin:16mm}main{max-width:none;padding:0}body{font-size:10pt}.original{padding:8px}thead{display:table-header-group}}</style></head><body>${body}</body></html>`;
}

export function downloadReviewPackage(review: ReviewDetail) {
  const url = URL.createObjectURL(new Blob([reviewPackageHtml(review)], {type: 'text/html;charset=utf-8'}));
  const a = document.createElement('a');a.href = url;a.download = `upgrade-review-${review.id}-r${review.revision}.html`;a.click();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
