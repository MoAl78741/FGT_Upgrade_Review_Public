import {useEffect,useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {collectSessionArchive} from '../utils/collectSessionArchive';
import {reviews} from '../reviews';
import {useTeam} from '../contexts/TeamContext';
import {sessionZip,saveDownload} from '../utils/sessionZip';
import type {Job} from '../types';
export default function SessionArchive({jobs}:{jobs:Job[]}){
 const team=useTeam();const {data:items=[]}=useQuery({queryKey:['reviews'],queryFn:reviews.list,enabled:!team.enabled||!!team.permissions?.includes('reviews.read')});
 const [busy,setBusy]=useState(false),[message,setMessage]=useState(''),[now,setNow]=useState(Date.now());useEffect(()=>{const t=setInterval(()=>setNow(Date.now()),60000);return()=>clearInterval(t)},[]);
 const expiries=[...jobs,...items].flatMap(x=>x.expires_at?[new Date(/[Zz]|[+-]\d{2}:?\d{2}$/.test(x.expires_at)?x.expires_at:x.expires_at+'Z').getTime()]:[]).filter(Number.isFinite);
 const earliest=expiries.length?Math.min(...expiries):null;const remaining=earliest?Math.max(0,Math.ceil((earliest-now)/60000)):null;
 const canExport=!team.enabled||!!team.permissions?.includes('reports.export');
 async function download(){setBusy(true);setMessage('Preparing archive…');try{
 const {entries,warnings}=await collectSessionArchive(jobs,(!team.enabled||team.permissions?.includes('reviews.export'))?items:[],{workspaceId:team.workspace_id,onProgress:setMessage});
 saveDownload(sessionZip(entries),'upgrade-review-session.zip');setMessage(warnings.length?`Archive downloaded with ${warnings.length} warning(s). See manifest.json for missing sources or unfinished reports.`:'Archive downloaded. Keep it in a secure location.');
 }catch(e){setMessage(e instanceof Error?e.message:String(e))}finally{setBusy(false)}}

 if(!jobs.length&&!items.length)return null;
 return <div className="rounded-lg border border-navy-600 p-3 text-sm text-gray-300 flex flex-wrap items-center gap-3">{remaining!==null&&<p role={remaining<60?'alert':'status'} className={remaining<60?'text-amber-400':''}>Earliest source or review expiry: {remaining<60?`${remaining} minutes`:`${Math.floor(remaining/60)}h ${remaining%60}m`} remaining. Download before it expires.</p>}{canExport&&<button className="rounded bg-brand-500 text-white px-3 py-2" disabled={busy} onClick={()=>void download()}>{busy?'Preparing…':'Download session archive'}</button>}{message&&<p role="status">{message}</p>}</div>
}
