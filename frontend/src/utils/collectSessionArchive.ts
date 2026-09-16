import type {Job,JobDetail} from '../types';
import type {ReviewDetail} from '../reviews';
import {generateHtml,getAvailableSections} from './htmlExport';
import {reviewPackageHtml} from './reviewExport';
import {ARCHIVE_LIMIT,type ArchiveEntry} from './sessionZip';
/** Each JSON/HTML pair comes from one snapshot. Missing originals are explicit. */
export async function collectSessionArchive(jobs:Job[],reviews:{id:string}[],options:{workspaceId?:string;onProgress?:(message:string)=>void;fetcher?:typeof fetch}={}){
 const fetcher=options.fetcher||fetch,entries:ArchiveEntry[]=[],warnings:{path:string;reason:string}[]=[],enc=new TextEncoder();let total=0;
 const sha256=async(data:Uint8Array)=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',Uint8Array.from(data).buffer))).map(v=>v.toString(16).padStart(2,'0')).join('');
 const headers:Record<string,string>=options.workspaceId?{'X-Workspace-ID':options.workspaceId}:{};
 function add(name:string,data:Uint8Array){total+=data.length;if(total>ARCHIVE_LIMIT)throw Error('Archive exceeds 256 MiB. Download reports individually.');entries.push({name,data});}
 async function read(url:string,optional=false){
  const response=await fetcher(url,{headers});
  if(optional&&response.status===404){warnings.push({path:url,reason:'Original PDF unavailable; extracted report retained.'});return undefined;}
  if(!response.ok)throw Error('An item is unavailable, expired or no longer authorized. Refresh and export again.');
  const reader=response.body?.getReader();if(!reader)throw Error('Download unavailable');const chunks:Uint8Array[]=[];let size=0;
  for(;;){const {value,done}=await reader.read();if(done)break;size+=value.length;if(total+size>ARCHIVE_LIMIT){await reader.cancel();throw Error('Archive exceeds 256 MiB. Download reports individually.');}chunks.push(value);}
  const data=new Uint8Array(size);let offset=0;for(const c of chunks){data.set(c,offset);offset+=c.length;}return data;
 }
 for(const job of jobs){
  options.onProgress?.(`Collecting report ${job.from_version} → ${job.to_version}…`);
  const bytes=(await read(`/api/jobs/${job.id}`))!;const snapshot:JobDetail=JSON.parse(new TextDecoder().decode(bytes));add(`reports/${job.id}.json`,bytes);
  if(['completed','partial'].includes(snapshot.status))add(`reports/${job.id}.html`,enc.encode(generateHtml(snapshot,new Set(getAvailableSections(snapshot).map(s=>s.id)))));
  if(snapshot.status!=='completed')warnings.push({path:`reports/${job.id}.json`,reason:`Report is ${snapshot.status}; this archive is an unfinished snapshot.`});
  if(snapshot.source==='pdf')for(let i=0;i<(snapshot.file_outcomes?.length||0);i++){
   const data=await read(`/api/jobs/${job.id}/files/${i}`,true);if(data){
    const expected=snapshot.provenance?.documents?.[i]?.sha256;
    if(expected&&await sha256(data)!==expected)throw Error('Original PDF checksum differs from the imported source. Archive cancelled; investigate the retained file.');
    add(`sources/${job.id}/${i}.pdf`,data);
   }
  }
 }
 for(const review of reviews){const bytes=(await read(`/api/reviews/${review.id}`))!;const snapshot:ReviewDetail=JSON.parse(new TextDecoder().decode(bytes));add(`reviews/${review.id}.json`,bytes);add(`reviews/${review.id}.html`,enc.encode(reviewPackageHtml(snapshot)));}
 add('manifest.json',enc.encode(JSON.stringify({schema:1,created_at:new Date().toISOString(),complete:warnings.length===0,warnings,files:await Promise.all(entries.map(async e=>({path:e.name,bytes:e.data.length,sha256:await sha256(e.data)})))},null,2)));
 add('README.txt',enc.encode('Upgrade Review archive. JSON and HTML share the same saved snapshot. Check manifest.json for unavailable originals or unfinished reports. Available source PDFs are included. Open HTML locally and print to PDF. This personal export cannot restore an installation or browser session. Browser configuration analysis is excluded. Keep this archive secure.'));
 return {entries,warnings};
}
