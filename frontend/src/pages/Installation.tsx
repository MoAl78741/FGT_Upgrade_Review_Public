import {useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {api, req} from '../api';
import {useTeam} from '../contexts/TeamContext';
import {Link} from 'react-router-dom';

export default function Installation() {
  const team=useTeam(), [report,setReport]=useState<object>(), [error,setError]=useState(''), [loading,setLoading]=useState(false);
  const {data:caps}=useQuery({queryKey:['capabilities'],queryFn:api.capabilities});
  async function preview() {
    setLoading(true);setError('');setReport(undefined);
    try {setReport(await req<object>('/support/diagnostics'));} catch(e) {setError(e instanceof Error?e.message:'Unable to load diagnostics.');} finally {setLoading(false);}
  }
  function download() {
    if(!report)return;
    const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));
    const a=document.createElement('a');a.href=url;a.download='upgrade-review-diagnostics.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  if(caps?.edition==='public')return <section className="max-w-3xl mx-auto p-6 space-y-5 text-gray-300"><h1 className="text-2xl font-semibold text-white">Help with your review</h1><h2 className="text-lg font-semibold">Importing documents</h2><p>Upload PDFs you already have, or expand “Help me find PDFs” on Home to select a release range. Each filename needs a FortiOS version. If none is found, enter the version beside the selected file before processing.</p><h2 className="text-lg font-semibold">Incomplete or failed imports</h2><p>Open the processing details to see per-file errors. Retry uses the current limits and keeps successful results. Remove duplicate versions or correct file problems before retrying.</p><h2 className="text-lg font-semibold">Keep your work</h2><p>Download a session archive from Home or Reports before the earliest expiry. It contains authorized report data, rendered HTML, available original PDFs and saved reviews. Open HTML locally to read or print it later. It does not restore a browser session.</p><p>Never paste raw configurations into reviewer notes. Use the report’s local configuration analysis instead.</p><a className="text-brand-500 underline" href="/pro">Explore persistent storage and team features in Pro</a></section>;
  if(team.enabled&&!team.user?.is_admin)return <p className="p-8 text-gray-400">Ask your installation administrator for setup or support diagnostics.</p>;
  return <div className="max-w-3xl mx-auto p-6 space-y-6 text-gray-300">
    <h1 className="text-2xl font-semibold text-white">Setup & support</h1>
    <p>Installation maintenance, backups, and troubleshooting. Use Home for day-to-day imports and reports.</p>
    <p>Pro edition · {caps?.version ? `Version ${caps.version}, build ${caps.build_number}`:'Checking build…'}</p>
    <ol className="list-decimal pl-5 space-y-5">
      <li><h2 className="font-semibold text-white">Set up access</h2><p>Use HTTPS for LAN access. {team.enabled?'Named accounts are enabled. Create individual accounts and assign customer workspaces in Account & administration.':'For a team, create the first administrator with the local setup command, then enable TEAM_AUTH_ENABLED and restart.'}</p>{team.enabled?<Link className="underline text-brand-500" to="/account">Manage accounts</Link>:<pre className="whitespace-pre-wrap bg-navy-800 p-3 rounded mt-2">python -m backend.manage_team bootstrap --username reviewer</pre>}</li>
      <li><h2 className="font-semibold text-white">Import your first documents</h2><p>Choose a version range to find the official PDF download links, then upload up to {caps?.max_files ?? 4} PDFs per batch. Create a review and add further batches when your upgrade spans more versions.</p><Link className="underline text-brand-500" to="/">Open PDF import</Link></li>
      <li><h2 className="font-semibold text-white">Prepare a recoverable backup</h2><p>Stop the application and run the local backup command against its database and upload volumes. Store the archive securely: it includes source PDFs, reviewer notes and account password hashes. The tool refuses to overwrite an existing archive.</p><pre className="whitespace-pre-wrap bg-navy-800 p-3 rounded mt-2">python -m backend.maintenance backup /backups/installation.zip</pre></li>
      <li><h2 className="font-semibold text-white">Verify restore before upgrading</h2><p>Use empty database and upload locations for a restore test, then start the intended new build against that copy. Verify sign-in, a source PDF, review decisions and export before switching your installation. Restoring ends old sign-in sessions. Keep the original data and image for rollback.</p><pre className="whitespace-pre-wrap bg-navy-800 p-3 rounded mt-2">python -m backend.maintenance restore /backups/installation.zip</pre><p className="text-sm mt-2">These are operator commands, not browser actions. Set DB_PATH and UPLOADS_DIR to the intended installation; Docker commands and volume preparation are in OPERATIONS.md in the corresponding source.</p></li>
    </ol>
    <section className="border-t border-navy-600 pt-5 space-y-3"><h2 className="font-semibold text-white">Support diagnostics</h2><p>Preview build information, processing limits, schema availability and job counts. The diagnostic file excludes document contents, filenames, customer names, account identities, logs, configuration analysis and filesystem paths. Downloading does not send it to support.</p>
      <button className="rounded bg-brand-500 text-white px-4 py-2 disabled:opacity-50" disabled={loading} onClick={preview}>{loading?'Preparing…':'Preview diagnostics'}</button>
      {error&&<p role="alert" className="text-red-400">{error}</p>}{report&&<><pre className="bg-navy-800 p-4 rounded overflow-auto text-xs">{JSON.stringify(report,null,2)}</pre><button className="underline text-brand-500" onClick={download}>Download diagnostics</button></>}
    </section>
  </div>;
}
