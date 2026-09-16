import {useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';
import {api} from '../api';
import JobCard from './JobCard';
import SessionArchive from './SessionArchive';
export default function ReportLibrary({compact=false}:{compact?:boolean}){
 const {data:jobs=[],isPending,error}=useQuery({queryKey:['jobs'],queryFn:api.listJobs,refetchInterval:5000});
 const [search,setSearch]=useState(''),[status,setStatus]=useState('all'),[source,setSource]=useState('all'),[page,setPage]=useState(0);
 const filtered=jobs.filter(j=>`${j.title||''} ${j.from_version} ${j.to_version} ${j.id} ${j.source} ${j.created_at}`.toLowerCase().includes(search.toLowerCase())&&(status==='all'||j.status===status)&&(source==='all'||j.source===source));
 const size=compact?5:15;const current=Math.min(page,Math.max(0,Math.ceil(filtered.length/size)-1));
 return <section id="reports" className={compact?'space-y-4':'max-w-screen-xl mx-auto p-6 space-y-5'}><div className="flex flex-wrap justify-between items-center gap-3"><h1 className="text-2xl font-semibold text-white">{compact?'Recent reports':'Report library'}</h1>{compact&&<Link className="text-brand-500 underline" to="/library">View all reports ({jobs.length})</Link>}</div><SessionArchive jobs={jobs}/>
 {!compact&&<div className="flex flex-wrap gap-3"><input aria-label="Search reports" placeholder="Search name, version, source, date or report ID" className="flex-1 min-w-56 rounded bg-navy-800 border border-navy-600 p-3 text-white" value={search} onChange={e=>{setSearch(e.target.value);setPage(0)}}/><select aria-label="Report status" className="rounded bg-navy-800 border border-navy-600 p-3 text-white" value={status} onChange={e=>{setStatus(e.target.value);setPage(0)}}>{['all','completed','partial','running','pending','failed','cancelled'].map(x=><option key={x} value={x}>{x==='all'?'All statuses':x}</option>)}</select><select aria-label="Report source" className="rounded bg-navy-800 border border-navy-600 p-3 text-white" value={source} onChange={e=>{setSource(e.target.value);setPage(0)}}><option value="all">All sources</option><option value="pdf">PDF</option><option value="scrape">Scrape</option></select></div>}
 {isPending&&<p role="status">Loading reports…</p>}{error&&<p role="alert" className="text-red-400">{error.message}</p>}
 {!isPending&&!filtered.length&&<div className="p-6 rounded-xl border border-dashed border-navy-600 text-gray-300">{jobs.length?'No reports match these filters.':'Your reports will appear here.'} <Link to="/#import" className="text-brand-500 underline">Import release notes</Link></div>}
 {filtered.slice(current*size,(current+1)*size).map(j=><JobCard job={j} key={j.id}/>)}
 {!compact&&filtered.length>size&&<div className="flex gap-4 text-gray-300"><button disabled={!current} onClick={()=>setPage(current-1)}>Previous</button><span>Page {current+1} of {Math.ceil(filtered.length/size)}</span><button disabled={(current+1)*size>=filtered.length} onClick={()=>setPage(current+1)}>Next</button></div>}
 </section>
}
