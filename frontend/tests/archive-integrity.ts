import assert from 'node:assert/strict';
import {collectSessionArchive} from '../src/utils/collectSessionArchive';
import type {JobDetail} from '../src/types';
const job:JobDetail={id:'saved',from_version:'7.6.6',to_version:'7.6.6',created_at:'2026-09-15',use_selenium:false,status:'completed',source:'pdf',versions:['7.6.6'],all_data:{'7.6.6':{known_issues:[{'Bug ID':'42',category:'System',Description:'Snapshot evidence sentinel'}]}},file_outcomes:[{name:'source.pdf',status:'completed'}]};
async function run(){
 const calls:string[]=[];
 const fetcher=(async(url:any)=>{calls.push(String(url));return String(url).includes('/files/')?new Response(null,{status:404}):Response.json(job)}) as typeof fetch;
 const result=await collectSessionArchive([job],[],{fetcher});
 assert.equal(calls.filter(x=>x==='/api/jobs/saved').length,1,'JSON and HTML must share one snapshot');
 assert(!calls.some(x=>x.includes('/export')),'A separately fetched export could observe a newer revision');
 const text=(name:string)=>new TextDecoder().decode(result.entries.find(e=>e.name===name)!.data);
 assert(text('reports/saved.json').includes('Snapshot evidence sentinel'));
 assert(text('reports/saved.html').includes('Snapshot evidence sentinel'));
 const manifest=JSON.parse(text('manifest.json'));assert.equal(manifest.complete,false);assert.equal(manifest.warnings.length,1);
 assert(manifest.files.every((f:any)=>/^[a-f0-9]{64}$/.test(f.sha256)));
 await assert.rejects(()=>collectSessionArchive([job],[],{fetcher:(async()=>new Response(null,{status:403})) as typeof fetch}),/authorized/);
 await assert.rejects(()=>collectSessionArchive([job],[],{fetcher:(async()=>new Response(null,{status:404})) as typeof fetch}),/expired/);
 const corrupted={...job,provenance:{documents:[{name:'source.pdf',sha256:'0'.repeat(64)}]}};
 await assert.rejects(()=>collectSessionArchive([corrupted],[],{fetcher:(async(url:any)=>String(url).includes('/files/')?new Response('changed PDF'):Response.json(corrupted)) as typeof fetch}),/checksum/);
 console.log('Archive integrity: consistent snapshots, explicit missing sources, hashes, corruption and authorization checks passed.');
}
void run().catch(error=>{console.error(error);process.exitCode=1});
