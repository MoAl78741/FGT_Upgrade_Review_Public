import {useState} from 'react';
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query';
import {api, req} from '../api';
import {useTeam} from '../contexts/TeamContext';
import {readPdfTimeout, savePdfTimeout} from '../utils/processingPreferences';

type Values = {timeout_minutes: number; max_files: number; max_pages: number; workers: number};
type Installation = {values: Values; defaults: Values; bounds: Values};
const field = 'block w-full mt-1 p-2 bg-navy-900 border border-navy-600 rounded text-white';
const button = 'rounded px-3 py-2 bg-brand-500 text-white disabled:opacity-50';
const labels: Record<keyof Values, string> = {timeout_minutes: 'Default PDF timeout (minutes)', max_files: 'PDFs per batch', max_pages: 'Pages per PDF', workers: 'Simultaneous jobs'};

function InstallationForm({data, changed}: {data: Installation; changed: () => Promise<unknown>}) {
  const [draft, setDraft] = useState(data.values);
  const [message, setMessage] = useState('');
  const mutation = useMutation({mutationFn: (reset: boolean) => req<Installation>('/settings/processing', {method: reset ? 'DELETE' : 'PUT', ...(reset ? {} : {body: JSON.stringify(draft)})}), onSuccess: async result => {setDraft(result.values);setMessage('Installation settings saved. Applies to new uploads and retries.');await changed();}});
  return <form className="space-y-3 border-t border-navy-600 pt-4" onSubmit={e => {e.preventDefault();setMessage('');mutation.mutate(false);}}>
    <h3 className="font-semibold text-white">Installation settings</h3>
    <p className="text-xs text-gray-400">Administrator controls for all Pro domains. Saved on the server and retained after restart. Running jobs keep their existing limits.</p>
    {(Object.keys(labels) as (keyof Values)[]).map(key => <label key={key} className="block text-sm text-gray-300">{labels[key]}<input className={field} type="number" min={1} max={data.bounds[key]} step={1} required value={Number.isNaN(draft[key]) ? '' : draft[key]} disabled={mutation.isPending} onChange={e => setDraft({...draft, [key]: e.target.valueAsNumber})}/><span className="text-xs text-gray-400">Maximum {data.bounds[key]}</span></label>)}
    <p className="text-xs text-gray-400">Lower simultaneous jobs if the machine feels slow. More files or pages may need a longer timeout. Upload byte limits and storage quotas remain operator-controlled.</p>
    <div className="flex gap-3"><button className={button} disabled={mutation.isPending}>Save installation settings</button><button className="text-gray-300 underline text-sm" type="button" disabled={mutation.isPending} onClick={() => {setMessage('');mutation.mutate(true);}}>Restore deployment defaults</button></div>
    {message && <p role="status" className="text-sm text-emerald-400">{message}</p>}
    {mutation.error && <p role="alert" className="text-sm text-red-400">{mutation.error.message}</p>}
  </form>;
}

export default function ProcessingSettings({localOnly=false}:{localOnly?:boolean}) {
  const team = useTeam(), qc = useQueryClient();
  const caps = useQuery({queryKey: ['capabilities'], queryFn: api.capabilities});
  const canManage = !localOnly && caps.data?.edition === 'private' && (!team.enabled || team.user?.is_admin);
  const installation = useQuery({queryKey: ['processing-settings'], queryFn: () => req<Installation>('/settings/processing'), enabled: !!canManage});
  const [timeout, setTimeout] = useState(readPdfTimeout), [message, setMessage] = useState(''), [error, setError] = useState('');
  if (!caps.data) return <p className="text-gray-400">Loading processing settings…</p>;
  return <section className="space-y-4">
    <h3 className="text-white font-semibold">PDF processing</h3>
    <p className="text-sm text-gray-400">Current limit: {caps.data.timeout_minutes} minutes per batch, {caps.data.max_files} PDFs, {caps.data.max_pages} pages per PDF. Up to {caps.data.max_file_bytes / 1024**2} MiB per file and {caps.data.max_total_bytes / 1024**2} MiB per batch.</p>
    <form className="space-y-3" onSubmit={e => {e.preventDefault();setError('');try {savePdfTimeout(timeout);setMessage('Preference saved for new uploads and retries in this browser.');} catch {setError('Browser storage is unavailable. The server default will be used.');}}}>
      <label className="block text-sm text-gray-300">My PDF timeout (minutes)<input className={field} type="number" min={1} max={caps.data.timeout_minutes} step={1} placeholder={`Server default (${caps.data.timeout_minutes})`} value={timeout} onChange={e => {setTimeout(e.target.value);setMessage('');}} /></label>
      <p className="text-xs text-gray-400">Leave blank to follow the server default. This timeout covers the whole batch, not each file. Changes apply to new uploads and retries, not work already processing.</p>
      <button className={button}>Save my preference</button>
      {message && <p role="status" className="text-sm text-emerald-400">{message}</p>}{error && <p role="alert" className="text-sm text-red-400">{error}</p>}
    </form>
    {canManage ? installation.data ? <InstallationForm data={installation.data} changed={async () => {await Promise.all([qc.invalidateQueries({queryKey: ['capabilities']}), qc.invalidateQueries({queryKey: ['processing-settings']})]);}}/> : <p className="text-sm text-gray-400">{installation.error?.message || 'Loading installation settings…'}</p> : <p className="text-xs text-gray-400">{caps.data.edition === 'public' ? 'Public limits are set by the hosting operator. Your preference cannot raise these limits.' : 'An installation administrator can change the server limits.'}</p>}
  </section>;
}
