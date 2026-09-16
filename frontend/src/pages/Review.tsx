import PdfFileList from "../components/PdfFileList";
import {req} from '../api';
import {pdfCatalog, compareVersions} from '../utils/pdfReleaseRange';
import {reviewVersionRange} from '../utils/reviewVersionRange';
import { useEffect, useState } from 'react';
import {useDraft,useDrafts} from '../contexts/DraftContext';
import ExportPreview from '../components/ExportPreview';
import SourcePreview from '../components/SourcePreview';
import {reviewPackageHtml} from '../utils/reviewExport';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../api';
import { reviews, decisionLabels, type ReviewInput, type ReviewDetail, type Finding, type Decision, type DecisionStatus, type CheckItem } from '../reviews';
import ReviewSource from '../components/ReviewSource';
import {downloadReviewPackage} from '../utils/reviewExport';
import {useTeam} from '../contexts/TeamContext';
import {AuditHistory} from './Account';
import { localDateTime } from '../utils/dateTime';

const inputStyle = 'block w-full p-2 rounded border border-navy-600 bg-navy-900 text-white';
const buttonStyle = 'rounded bg-brand-500 text-white px-3 py-2 disabled:opacity-40';

function DetailsForm({review, save, busy}: {review: ReviewDetail; save: (data: ReviewInput) => Promise<unknown>; busy: boolean}) {
  const [draft, setDraft] = useState<ReviewInput>({title: review.title, customer: review.customer, site: review.site, prepared_by: review.prepared_by, summary: review.summary, rollback_notes: review.rollback_notes, expected_versions: review.expected_versions, range_from: review.range_from, range_to: review.range_to, range_include_from: review.range_include_from});
  const saved = [...review.expected_versions].sort(compareVersions);
  const [from, setFrom] = useState(review.range_from ?? saved[0] ?? ''), [to, setTo] = useState(review.range_to ?? saved[saved.length - 1] ?? '');
  const [includeFrom, setIncludeFrom] = useState(review.range_include_from ?? (saved.length > 0)), [rangeEdited, setRangeEdited] = useState(false);
  const draftState=useDraft({draft,from,to,includeFrom});
  let versions = review.expected_versions, rangeError = '';
  if (rangeEdited) {
    try { versions = reviewVersionRange(from, to, includeFrom); } catch(e) { rangeError = (e as Error).message; }
  }
  return <form onSubmit={async e => {e.preventDefault(); if (!rangeError) {try {await save({...draft, expected_versions: versions, ...(rangeEdited ? {range_from: from.trim(), range_to: to.trim(), range_include_from: includeFrom} : {})});draftState.markSaved();}catch{/* Shared mutation error is displayed below. */}}}} className="space-y-3">
    <div className="grid sm:grid-cols-2 gap-3">{([['title', 'Review name'], ['customer', 'Customer'], ['site', 'Site'], ['prepared_by', 'Prepared by']] as const).map(([key, label]) => <label key={key} className="text-sm text-gray-400">{label}<input disabled={busy} required={key === 'title'} maxLength={160} className={inputStyle} value={draft[key]} onChange={e => setDraft({...draft, [key]: e.target.value})} /></label>)}</div>
    <fieldset className="border border-navy-600 rounded-lg p-3 space-y-3">
      <legend className="px-1 text-sm text-gray-400">Release range</legend>
      <div className="grid sm:grid-cols-2 gap-3">
        <label className="text-sm text-gray-400">From version<input disabled={busy} className={inputStyle} list="review-release-versions" maxLength={10} value={from} onChange={e => {setFrom(e.target.value);setRangeEdited(true);}} placeholder="7.6.3" /></label>
        <label className="text-sm text-gray-400">To version<input disabled={busy} className={inputStyle} list="review-release-versions" maxLength={10} value={to} onChange={e => {setTo(e.target.value);setRangeEdited(true);}} placeholder="7.6.6" /></label>
      </div>
      <datalist id="review-release-versions">{[...pdfCatalog.releases].reverse().map(r => <option key={r.version} value={r.version} />)}</datalist>
      <label className="flex gap-2 text-sm text-gray-400"><input disabled={busy} type="checkbox" checked={includeFrom} onChange={e => {setIncludeFrom(e.target.checked);setRangeEdited(true);}} />Include the starting version’s notes</label>
      {rangeError ? <p role="alert" className="text-amber-400 text-sm">{rangeError}</p> : <div className="flex flex-wrap gap-2 text-sm text-gray-400" aria-label="Expected releases">{versions.length ? versions.map(v => <span key={v} className="border border-navy-600 rounded px-2 py-1">{v}</span>) : 'No release range selected.'}</div>}
      <p className="text-xs text-gray-400">Includes published releases through To. This is a release-note checklist, not a firmware upgrade path. Existing saved selections stay unchanged until you edit the range.</p>
    </fieldset>
    <label className="block text-sm text-gray-400">Review summary<textarea disabled={busy} maxLength={8000} className={inputStyle} rows={3} value={draft.summary} onChange={e => setDraft({...draft, summary: e.target.value})} /></label>
    <label className="block text-sm text-gray-400">Rollback notes<textarea disabled={busy} maxLength={8000} className={inputStyle} rows={3} value={draft.rollback_notes} onChange={e => setDraft({...draft, rollback_notes: e.target.value})} /></label>
    <p className="text-xs text-gray-400">These notes are saved on this installation. Do not paste raw configurations or secrets. Browser configuration analysis remains separate and temporary.</p>
    <button className={buttonStyle} disabled={busy || !!rangeError}>Save review details</button><span role="status" className="text-sm text-gray-400 ml-3">{busy?'Saving…':draftState.dirty?'Unsaved changes':'Saved'}</span>
  </form>;
}

function FindingCard({finding, decision, save, busy, next}: {finding: Finding; decision?: Decision; save: (value: Decision) => Promise<unknown>; busy: boolean; next:()=>void}) {
  const team=useTeam();const canSource=!team.enabled||team.permissions?.includes('reports.export');
  const [status, setStatus] = useState<DecisionStatus>(decision?.status ?? 'unreviewed');
  const [note, setNote] = useState(decision?.note ?? '');
  const draftState=useDraft({status,note});const [sourceOpen,setSourceOpen]=useState(false);
  return <article className="border border-navy-600 rounded-lg p-4 space-y-3">
    <div className="flex flex-wrap gap-2 text-sm"><strong className="text-white">{finding.version} · {finding.source['Bug ID'] || finding.source['Feature ID'] || finding.source.title || finding.section}</strong><span className="text-gray-400">{finding.source.category} · {finding.section.replace(/[-_]/g, ' ')}</span><Link to={`/reports/${finding.job_id}`} target="_blank" rel="noopener noreferrer" className="ml-auto text-brand-500 underline">Open source report</Link></div>
    {finding.reference?.available===false?<p className="text-amber-400 text-sm">Original PDF unavailable; extracted source text is retained below.</p>:finding.reference && canSource ? <a className="inline-block text-sm text-brand-500 underline" href={finding.reference.url} target="_blank" rel="noopener noreferrer">{finding.reference.kind === 'pdf' ? finding.reference.page ? `Open source PDF · section starts on page ${finding.reference.page}` : 'Open source PDF · page not recorded' : 'Open original web section'}</a> : <p className="text-xs text-gray-500">Original page link not recorded for this source.</p>}
    {canSource&&finding.reference?.available!==false&&finding.reference?.kind==='pdf'&&<button type="button" className="text-brand-500 underline" onClick={()=>setSourceOpen(true)}>Compare with source PDF</button>}
    {sourceOpen&&finding.reference&&<SourcePreview reference={finding.reference} onClose={()=>setSourceOpen(false)}><ReviewSource source={finding.source}/></SourcePreview>}
    <ReviewSource source={finding.source} />
    <form onSubmit={async e => {e.preventDefault();try{await save({status,note});draftState.markSaved();}catch{/* Shared error */}}} className="space-y-2 border-t border-navy-600 pt-3">
      <label className="block text-sm text-gray-400">Decision<select disabled={busy} aria-label="Decision" className={inputStyle} value={status} onChange={e => setStatus(e.target.value as DecisionStatus)}>{Object.entries(decisionLabels).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select></label>
      <label className="block text-sm text-gray-400">Reviewer note<textarea aria-label="Reviewer note" disabled={busy} className={inputStyle} value={note} maxLength={4000} required={status === 'not_applicable'} onChange={e => setNote(e.target.value)} /></label>
      <button className={buttonStyle} disabled={busy}>Save decision</button><button type="button" className={buttonStyle+" ml-2"} disabled={busy} onClick={async()=>{try{await save({status,note});draftState.markSaved();next();}catch{/* Shared error */}}}>Save and next</button><span role="status" className="text-sm text-gray-400 ml-3">{busy?'Saving…':draftState.dirty?'Unsaved changes':'Saved'}</span>
      {decision?.updated_at && <span className="text-xs text-gray-500 ml-2">Saved {localDateTime(decision.updated_at)}</span>}
    </form>
  </article>;
}

function Checklist({items, save, busy}: {items: CheckItem[]; save: (items: CheckItem[]) => Promise<unknown>; busy: boolean}) {
  const [draft, setDraft] = useState(items), [text, setText] = useState(''), [phase, setPhase] = useState<CheckItem['phase']>('before');
  const draftState=useDraft(draft);
  return <div className="space-y-3">
    {draft.map(item => <div key={item.id} className="flex gap-2 items-center"><input disabled={busy} aria-label={`Completed: ${item.text}`} type="checkbox" checked={item.done} onChange={e => setDraft(draft.map(i => i.id === item.id ? {...i, done: e.target.checked} : i))} /><span className="flex-1 text-gray-300">{item.phase}: {item.text}</span><button onClick={() => setDraft(draft.filter(i => i.id !== item.id))} className="text-red-400" aria-label={`Remove checklist item: ${item.text}`}>Remove</button></div>)}
    <form className="flex flex-wrap gap-2" onSubmit={e => {e.preventDefault();if (text.trim()) {setDraft([...draft, {id: crypto.randomUUID(), phase, text: text.trim(), done: false}]);setText('');}}}>
      <select disabled={busy} aria-label="Test phase" className={inputStyle + ' sm:w-auto'} value={phase} onChange={e => setPhase(e.target.value as CheckItem['phase'])}><option value="before">Before upgrade</option><option value="after">After upgrade</option><option value="rollback">Rollback</option></select>
      <input disabled={busy} aria-label="Checklist action" className={inputStyle + ' flex-1'} value={text} maxLength={1000} onChange={e => setText(e.target.value)} placeholder="Verify configuration backup" /><button className={buttonStyle} disabled={draft.length >= 100 || !text.trim()}>Add action</button>
    </form>
    <button disabled={busy} className={buttonStyle} onClick={async () => {try{await save(draft);draftState.markSaved();}catch{/* Shared error */}}}>Save checklist</button><span role="status" className="text-sm text-gray-400 ml-3">{busy?'Saving…':draftState.dirty?'Unsaved changes':'Saved'}</span>
  </div>;
}

export default function ReviewPage() {
  const team = useTeam();const drafts=useDrafts();const [preview,setPreview]=useState(false);
  const [selected,setSelected]=useState<string[]>([]),[bulkStatus,setBulkStatus]=useState<DecisionStatus>('reviewed'),[bulkNote,setBulkNote]=useState(''),[bulkPreview,setBulkPreview]=useState(false);
  const {id = ''} = useParams(), qc = useQueryClient(), navigate = useNavigate();
  const [jobId, setJobId] = useState(''), [filter, setFilter] = useState(''), [statusFilter, setStatusFilter] = useState('all'), [page, setPage] = useState(0);
  const query = useQuery({queryKey: ['review', id], queryFn: () => reviews.get(id)});
  const imports = useQuery({queryKey: ['jobs'], queryFn: api.listJobs});
  const mutation = useMutation({mutationFn: (task: () => Promise<unknown>) => task(), onSuccess: async () => {await qc.invalidateQueries({queryKey: ['review', id]});qc.invalidateQueries({queryKey: ['reviews']});qc.invalidateQueries({queryKey: ['audit']});}});
  useEffect(()=>{const move=(e:KeyboardEvent)=>{if(!e.altKey||!['ArrowDown','ArrowUp'].includes(e.key))return;const nodes=Array.from(document.querySelectorAll<HTMLElement>('[id^="finding-"]'));const at=nodes.findIndex(n=>n.contains(document.activeElement));const next=nodes[Math.max(0,Math.min(nodes.length-1,at+(e.key==='ArrowDown'?1:-1)))];if(next){e.preventDefault();next.focus();next.scrollIntoView({block:'center'})}};window.addEventListener('keydown',move);return()=>window.removeEventListener('keydown',move)},[]);
  const r = query.data;
  if (!r) return <p className="p-6 text-gray-400">{query.error?.message || 'Loading review…'}</p>;
  const busy = mutation.isPending || (team.enabled && !team.permissions?.includes('reviews.write'));
  const counts = Object.fromEntries(Object.keys(decisionLabels).map(s => [s, r.findings.filter(f => (r.decisions[f.id]?.status ?? 'unreviewed') === s).length]));
  const filtered = r.findings.filter(f => f.section === 'special_notices' || (statusFilter === 'all' || (r.decisions[f.id]?.status ?? 'unreviewed') === statusFilter) && JSON.stringify(f.source).toLowerCase().includes(filter.toLowerCase()));
  return <div className="max-w-screen-xl mx-auto p-6 space-y-6">
    {preview&&<ExportPreview html={reviewPackageHtml(r)} onClose={()=>setPreview(false)}/>}
    {drafts.dirty&&<p role="status" className="sticky top-36 z-20 p-3 border border-amber-500 bg-navy-800 text-amber-400">Unsaved edits — save each changed section before exporting or completing this review.</p>}
    <h1 className="text-2xl font-semibold text-white">{r.title}</h1>
    <div className="flex gap-3 items-center text-gray-300"><span>{r.completed_at ? 'Review completed · '+localDateTime(r.completed_at) : 'Review in progress'}</span><button className={buttonStyle} disabled={busy} onClick={()=>{if(drafts.dirty){window.alert('Save your edits before completing or reopening the review.');return;}if(window.confirm(r.completed_at?'Reopen this review?':'Mark this review complete? Configured domain recipients will be notified. This does not certify upgrade safety.'))mutation.mutate(()=>req('/reviews/'+id+'/completion',{method:'POST',body:JSON.stringify({revision:r.revision,completed:!r.completed_at})}));}}>{r.completed_at?'Reopen review':'Complete review'}</button></div>
    <p className="text-sm text-gray-300">Upgrade review · Add source reports below, record decisions in Review findings, then finish your checklist and export the review package.</p>
    <p className="text-gray-400">{r.jobs.length} available batches · {r.findings.length} findings · {counts.unreviewed} unreviewed · {counts.needs_testing} need testing · {counts.action_required} actions required · {r.checklist.filter(i => i.done).length}/{r.checklist.length} checklist actions complete</p>
    {r.expires_at && <p className="text-amber-400">Temporary review expires {localDateTime(r.expires_at)}. Source batches keep their own expiry.</p>}
    {r.missing_versions.length > 0 && <p role="alert" className="text-amber-400">Missing expected versions: {r.missing_versions.join(', ')}</p>}
    {r.unavailable_job_ids.length > 0 && <p role="alert" className="text-red-400">{r.unavailable_job_ids.length} source batches were deleted or expired. Their findings are unavailable.</p>}
    {mutation.error && <div role="alert" className="text-red-400">{mutation.error.message} <button className="underline" onClick={() => query.refetch()}>Reload review</button></div>}
    <details className="border border-navy-600 rounded-lg p-4" open={!r.jobs.length}><summary className="font-semibold text-white mb-3 cursor-pointer">Review details</summary><DetailsForm key={`${id}-details`} review={r} busy={busy} save={data => mutation.mutateAsync(() => reviews.edit(id, {...data, revision: r.revision}))} /></details>
    <section className="border border-navy-600 rounded-lg p-4 space-y-3"><h2 className="font-semibold text-white">Source reports</h2>
      <p className="text-sm text-gray-400">Import PDFs within your edition’s upload limits, then add each completed batch here. Original reports stay unchanged.</p><Link to="/" className="text-brand-500 underline">Home — import another batch</Link>
      {r.jobs.map(j => <div key={j.id} className="flex gap-3 items-center text-gray-300"><Link className="underline flex-1" to={`/reports/${j.id}`}>{j.versions?.join(', ')} · {j.status}</Link><button disabled={busy} className="text-red-400" onClick={() => mutation.mutate(() => reviews.unlink(id, j.id, r.revision))}>Remove from review</button></div>)}
      <div className="flex flex-wrap gap-2"><select aria-label="Source report" value={jobId} className={inputStyle + ' flex-1'} onChange={e => setJobId(e.target.value)}><option value="">Choose a source report</option>{imports.data?.filter(j => ['completed', 'partial'].includes(j.status) && !r.job_ids.includes(j.id)).map(j => <option key={j.id} value={j.id}>{j.from_version} → {j.to_version} · {localDateTime(j.created_at)}</option>)}</select><button className={buttonStyle} disabled={busy || !jobId} onClick={() => mutation.mutate(() => reviews.link(id, jobId, r.revision))}>Add report</button></div>
    </section>
    <details className="border border-navy-600 rounded-lg p-4"><summary className="font-semibold text-white mb-3 cursor-pointer">Source completeness and import outcomes</summary>
      <p className="text-sm text-gray-400">An absent section does not mean there were no changes. Verify incomplete sources before finishing the review.</p>
      {r.jobs.map(job => <div key={job.id} className="my-3 text-sm text-gray-300"><h3 className="font-semibold">{job.versions?.join(', ')} · {job.status}</h3>{job.warnings?.map((w, i) => <p className="text-amber-400" key={i}>{w}</p>)}
        <PdfFileList files={job.file_outcomes} jobStatus={job.status} />
        {Object.entries(job.all_data ?? {}).map(([version, data]) => <div key={version}><h4>{version}</h4>{data._section_status ? <ul>{Object.entries(data._section_status).map(([section, state]) => <li key={section}>{section.replace(/[-_]/g, ' ')}: {state === 'not_captured' ? 'not captured / not found' : state === 'captured_empty' ? 'captured, no rows' : 'captured'}</li>)}</ul> : <p className="text-amber-400">Section completeness not recorded for this source.</p>}</div>)}
      </div>)}
    </details>
    <details className="border border-navy-600 rounded-lg p-4"><summary className="font-semibold text-white mb-3 cursor-pointer">Testing and rollback checklist</summary><Checklist key={JSON.stringify(r.checklist)} items={r.checklist} busy={busy} save={items => mutation.mutateAsync(() => reviews.checklist(id, items, r.revision))} /></details>
    <section className="space-y-3"><h2 className="text-lg font-semibold text-white">Review findings</h2><p className="text-xs text-gray-400">Special notices remain included when filtering by text or decision. Alt + Up/Down moves between visible findings.</p><div className="flex flex-wrap gap-3"><input aria-label="Search review findings" className={inputStyle + ' flex-1'} placeholder="Search original text" value={filter} onChange={e => {if(drafts.confirmDiscard()){setFilter(e.target.value);setPage(0);}}} /><select aria-label="Filter by decision" className={inputStyle + ' sm:w-auto'} value={statusFilter} onChange={e => {if(drafts.confirmDiscard()){setStatusFilter(e.target.value);setPage(0);}}}><option value="all">All decisions</option>{Object.entries(decisionLabels).map(([s, label]) => <option key={s} value={s}>{label}</option>)}</select></div>
      <details className="border border-navy-600 rounded p-3"><summary className="text-brand-500 cursor-pointer">Bulk decisions ({selected.length} selected)</summary><p className="text-sm text-gray-400 my-2">Only checked findings are changed, including selections on other pages. Existing decisions are replaced. Up to 100 findings.</p><select aria-label="Bulk decision" className={inputStyle} value={bulkStatus} onChange={e=>{setBulkStatus(e.target.value as DecisionStatus);setBulkPreview(false)}}>{Object.entries(decisionLabels).map(([k,l])=><option key={k} value={k}>{l}</option>)}</select><textarea aria-label="Bulk decision note" maxLength={4000} placeholder="Reason for this decision" className={inputStyle} value={bulkNote} onChange={e=>{setBulkNote(e.target.value);setBulkPreview(false)}}/><button disabled={!selected.length||busy||drafts.dirty} className={buttonStyle} onClick={()=>setBulkPreview(true)}>Preview changes</button><button className="ml-3 text-gray-400" onClick={()=>{setSelected([]);setBulkPreview(false)}}>Clear selection</button>{bulkPreview&&<div className="p-3 space-y-3"><p className="text-amber-400">Apply {decisionLabels[bulkStatus]} to exactly {selected.length} findings:</p><ul className="max-h-48 overflow-auto text-gray-300">{r.findings.filter(f=>selected.includes(f.id)).map(f=><li key={f.id}>{f.version} · {f.source['Bug ID']||f.source['Feature ID']||f.section}</li>)}</ul><button className={buttonStyle} disabled={busy||drafts.dirty||(bulkStatus==='not_applicable'&&!bulkNote.trim())} onClick={()=>mutation.mutate(async()=>{await req('/reviews/'+id+'/bulk-decisions',{method:'PUT',body:JSON.stringify({revision:r.revision,finding_ids:selected,status:bulkStatus,note:bulkNote})});setSelected([]);setBulkPreview(false);setBulkNote('')})}>Apply to selected findings</button></div>}</details>
      {filtered.slice(page * 25, page * 25 + 25).map((f,index) => <div key={f.id} id={'finding-'+f.id} tabIndex={-1}><label className="flex gap-2 text-sm text-gray-400 mb-2"><input aria-label={`Select finding ${f.source['Bug ID']||f.source['Feature ID']||f.id}`} type="checkbox" checked={selected.includes(f.id)} disabled={busy||(!selected.includes(f.id)&&selected.length>=100)} onChange={e=>{setSelected(e.target.checked?[...selected,f.id]:selected.filter(x=>x!==f.id));setBulkPreview(false)}}/>Select for bulk decision</label><FindingCard key={`${f.id}-${r.decisions[f.id]?.updated_at || ''}`} finding={f} decision={r.decisions[f.id]} busy={busy} next={()=>{const following=filtered[page*25+index+1];if(!following)return;const target=document.getElementById('finding-'+following.id);if(target){target.scrollIntoView({block:'center',behavior:'smooth'});target.focus()}else if(drafts.confirmDiscard())setPage(page+1)}} save={value => mutation.mutateAsync(() => reviews.decide(id, f.id, {...value, revision: r.revision}))} /></div>)}
      <div className="flex gap-3 text-gray-400"><button disabled={page === 0} onClick={() => {if(drafts.confirmDiscard())setPage(page-1)}}>Previous</button><span>{filtered.length} matching findings · Page {page + 1}</span><button disabled={(page + 1) * 25 >= filtered.length} onClick={() => {if(drafts.confirmDiscard())setPage(page+1)}}>Next</button></div>
    </section>
    <section className="border border-navy-600 rounded-lg p-4 space-y-3"><h2 className="font-semibold text-white">Export review package</h2><p className="text-sm text-gray-400">Includes all findings, source completeness, saved reviewer decisions, and checklists. Unsaved edits are excluded. Open the downloaded HTML and use Print → Save as PDF for a PDF copy.</p><button className={buttonStyle} disabled={mutation.isPending||(team.enabled&&!team.permissions?.includes('reviews.export'))} onClick={() => {if(drafts.dirty){window.alert("Save your edits before exporting.");return;}downloadReviewPackage(r)}}>Download review package</button><button className={buttonStyle+" ml-3"} disabled={drafts.dirty||(team.enabled&&!team.permissions?.includes('reviews.export'))} onClick={()=>setPreview(true)}>Preview export</button></section>
    <AuditHistory targetId={id} />
    <button className={buttonStyle} disabled={busy} onClick={() => mutation.mutate(async () => {const copy = await reviews.duplicate(id);navigate(`/reviews/${copy.id}`);})}>Duplicate preparation details</button>
    <button className="text-red-400 ml-4" disabled={mutation.isPending||(team.enabled&&!team.permissions?.includes('reviews.delete'))} onClick={() => {if(window.confirm('Delete this review and its decisions? Original imports will be kept.')) mutation.mutate(async () => {await reviews.delete(id);navigate('/reviews');});}}>Delete review</button>
  </div>;
}
