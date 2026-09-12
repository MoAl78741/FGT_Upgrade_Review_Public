import {useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';
import {api} from '../api';
import {useTeam} from '../contexts/TeamContext';
import PdfUploadForm from '../components/PdfUploadForm';
import NewScrapeForm from '../components/NewScrapeForm';
import ReportLibrary from '../components/ReportLibrary';
export default function Home(){
 const team=useTeam();const {data:caps}=useQuery({queryKey:['capabilities'],queryFn:api.capabilities});const [mode,setMode]=useState('pdf');
 const canImport=!team.enabled||team.permissions?.includes('reports.import');
 return <div className="max-w-screen-xl mx-auto px-6 py-8 space-y-8">
 <section className="flex flex-wrap items-center justify-between gap-5"><div><h1 className="text-3xl font-semibold text-white">{caps?.edition==='public'?'Make release notes easier to review':'Your upgrade workspace'}</h1><p className="mt-3 text-gray-300">Compare releases, find changes, and export the original source alongside your assessment.</p></div><Link to="/example" className="rounded-lg border border-brand-500 text-brand-500 px-4 py-3">Explore an example report</Link></section>
 {caps?.edition==='private'&&<ReportLibrary compact />}
 {canImport&&<section id="import" className="space-y-4"><div className="flex gap-3 items-center"><h2 className="text-xl text-white font-semibold">Import release notes</h2>{caps?.scraping&&<div className="flex gap-2"><button className="rounded border border-navy-600 px-3 py-2 text-gray-300" aria-pressed={mode==='pdf'} onClick={()=>setMode('pdf')}>Upload PDFs</button><button className="rounded border border-navy-600 px-3 py-2 text-gray-300" aria-pressed={mode==='scrape'} onClick={()=>setMode('scrape')}>Scrape documentation</button></div>}</div><p className="text-sm text-gray-400">{caps?.edition==='public'?'Your temporary session lasts up to 24 hours. Clearing cookies loses access. Download your work before expiry.':'Pro keeps reports on this installation until you delete them.'}</p>{mode==='scrape'&&caps?.scraping?<NewScrapeForm/>:<PdfUploadForm/>}</section>}
 {caps?.edition==='public'&&<ReportLibrary compact/>}
 <p className="text-sm text-gray-400">Want to record decisions? <Link className="underline text-brand-500" to="/reviews">Create an upgrade review</Link> from your imported reports. Only upload documents you are authorized to process.</p>
 </div>
}
