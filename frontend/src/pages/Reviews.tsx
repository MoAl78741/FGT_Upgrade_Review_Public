import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { reviews } from '../reviews';
import {useTeam} from '../contexts/TeamContext';
import { api } from '../api';
import { localDateTime } from '../utils/dateTime';

export default function Reviews() {
  const team = useTeam();
  const [title, setTitle] = useState(''), [search, setSearch] = useState('');
  const navigate = useNavigate(), qc = useQueryClient();
  const {data, error} = useQuery({queryKey: ['reviews'], queryFn: reviews.list});
  const {data: caps} = useQuery({queryKey: ['capabilities'], queryFn: api.capabilities});
  const create = useMutation({mutationFn: () => reviews.create(title.trim()), onSuccess: r => {qc.invalidateQueries({queryKey: ['reviews']}); navigate(`/reviews/${r.id}`);}});
  return <div className="max-w-screen-xl mx-auto p-6 space-y-6">
    <h1 className="text-2xl font-semibold text-white">Upgrade reviews</h1>
    <p className="text-gray-300">An upgrade review is your working record for a planned upgrade. Add one or more source reports, record which release notes need action, and track testing and rollback tasks.</p>
    <div className="rounded-xl border border-navy-600 bg-navy-800 p-4 space-y-2 text-sm text-gray-300">
      <p><strong className="text-white">Report:</strong> the release notes from one import batch.</p>
      <p><strong className="text-white">Review:</strong> selected reports plus your decisions, checklist, customer details, and review export. Source text stays unchanged.</p>
      <p>You can read and export reports without creating a review. <Link to="/" className="text-brand-500 underline">Go to Home to import or open reports</Link>.</p>
    </div>
    {caps?.edition === 'public' && <p className="text-amber-400">Reviews belong to this browser session and expire after 24 hours. Source reports may expire sooner. Export your work before leaving.</p>}
    <form onSubmit={e => {e.preventDefault(); create.mutate();}} className="flex flex-wrap gap-3">
      <label className="flex-1 text-gray-400">Review name<input className="block w-full p-3 rounded border bg-navy-800 text-white" value={title} maxLength={160} onChange={e => setTitle(e.target.value)} placeholder="Branch firewall upgrade" required /></label>
      <button disabled={!title.trim() || create.isPending || (team.enabled && !team.permissions?.includes('reviews.write'))} className="self-end p-3 bg-brand-500 text-white rounded disabled:opacity-50">{create.isPending ? 'Creating…' : 'Create review'}</button>
    </form>
    {(error || create.error) && <p role="alert" className="text-red-400">{(error || create.error)?.message}</p>}
    <label className="block text-gray-400">Search reviews<input className="block w-full p-3 rounded border bg-navy-800 text-white" value={search} onChange={e => setSearch(e.target.value)} placeholder="Name, customer, or site" /></label>
    <div className="space-y-3">{data?.filter(r => `${r.title} ${r.customer} ${r.site}`.toLowerCase().includes(search.toLowerCase())).map(r => <Link className="block rounded-xl border border-navy-600 bg-navy-800 p-4 hover:border-brand-500" key={r.id} to={`/reviews/${r.id}`}>
      <h2 className="font-semibold text-white">{r.title}</h2><p className="text-gray-400">{[r.customer, r.site].filter(Boolean).join(' · ') || 'Customer and site not set'}</p>
      <p className="text-xs text-gray-500">{r.job_ids.length} import batches · Updated {localDateTime(r.updated_at)}</p>
    </Link>)}</div>
    {data?.length === 0 && <p className="text-gray-400">No reviews yet. Give your planned upgrade a name above, then add its source reports.</p>}
  </div>;
}
