import {useEffect,useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {api} from '../api';
import {reviews} from '../reviews';
import {useTeam} from '../contexts/TeamContext';
import {ARCHIVE_LIMIT,sessionZip,saveDownload,type ArchiveEntry} from '../utils/sessionZip';
import type {Job} from '../types';
export default function SessionArchive({jobs}:{jobs:Job[]}){
 const team=useTeam();const {data:items=[]}=useQuery({queryKey:['reviews'],queryFn:reviews.list,enabled:!team.enabled||!!team.permissions?.includes('reviews.read')});
 const [busy,setBusy]=useState(false),[message,setMessage]=useState(''),[now,setNow]=useState(Date.now());useEffect(()=>{const t=setInterval(()=>setNow(Date.now()),60000);return()=>clearInterval(t)},[]);
 const expiries=[...jobs,...items].flatMap(x=>x.expires_at?[new Date(/[Zz]|[+-]\d{2}:?\d{2}$/.test(x.expires_at)?x.expires_at:x.expires_at+'Z').getTime()]:[]).filter(Number.isFinite);
 const earliest=expiries.length?Math.min(...expiries):null;const remaining=earliest?Math.max(0,Math.ceil((earliest-now)/60000)):null;
 const canExport=!team.enabled||!!team.permissions?.includes('reports.export');
 async function download(){setBusy(true);setMessage('Preparing archive…');const entries:ArchiveEntry[]=[];let total=0;
 const add=async(path:string,name:string,method='GET')=>{const response=await fetch(path,{method,headers:{...(team.workspace_id?{'X-Workspace-ID':team.workspace_id}:{}),...(method==='POST'?{'Content-Type':'application/json'}:{})},...(method==='POST'?{body:'{}'}:{})});if(!response.ok)throw Error('An item is unavailable or expired. Refresh and export remaining reports.');const reader=response.body?.getReader();if(!reader)throw Error('Download unavailable');const chunks:Uint8Array[]=[];let size=0;for(;;){const {value,done}=await reader.read();if(done)break;total+=value.length;size+=value.length;if(total>ARCHIVE_LIMIT){await reader.cancel();throw Error('Archive exceeds 256 MiB. Download reports individually.')}chunks.push(value)}const data=new Uint8Array(size);let p=0;for(const c of chunks){data.set(c,p);p+=c.length}entries.push({name,data});};
 try{for(const j of jobs){setMessage(`Collecting report ${j.from_version} → ${j.to_version}…`);await add(`/api/jobs/${j.id}`,`reports/${j.id}.json`);if(['completed','partial'].includes(j.status))await add(`/api/jobs/${j.id}/export`,`reports/${j.id}.html`,'POST');const detail=await api.getJob(j.id);if(j.source==='pdf')for(let i=0;i<(detail.file_outcomes?.length||0);i++)await add(`/api/jobs/${j.id}/files/${i}`,`sources/${j.id}/${i}.pdf`);}
 if(!team.enabled||team.permissions?.includes('reviews.export'))for(const review of items){await add(`/api/reviews/${review.id}`,`reviews/${review.id}.json`);await add(`/api/reviews/${review.id}/export`,`reviews/${review.id}.html`)}
 entries.push({name:'README.txt',data:new TextEncoder().encode('Upgrade Review archive. JSON contains original imported data and saved decisions. Review HTML can be opened offline and printed to PDF. Source PDFs are included when available. This is a personal export, not an installation restore archive. No browser configuration analysis is included. Secure this archive; it contains your documents and notes.')});saveDownload(sessionZip(entries),'upgrade-review-session.zip');setMessage('Archive downloaded. Keep it in a secure location.');}catch(e){setMessage(e instanceof Error?e.message:String(e))}finally{setBusy(false)}}
 if(!jobs.length&&!items.length)return null;
 return <div className="rounded-lg border border-navy-600 p-3 text-sm text-gray-300 flex flex-wrap items-center gap-3">{remaining!==null&&<p role={remaining<60?'alert':'status'} className={remaining<60?'text-amber-400':''}>Earliest source or review expiry: {remaining<60?`${remaining} minutes`:`${Math.floor(remaining/60)}h ${remaining%60}m`} remaining. Download before it expires.</p>}{canExport&&<button className="rounded bg-brand-500 text-white px-3 py-2" disabled={busy} onClick={()=>void download()}>{busy?'Preparing…':'Download session archive'}</button>}{message&&<p role="status">{message}</p>}</div>
}
