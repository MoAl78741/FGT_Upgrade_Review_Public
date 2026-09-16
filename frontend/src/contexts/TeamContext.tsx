import {createContext, useContext, useEffect, useState, type ReactNode} from 'react';
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query';
import {req, setWorkspaceHeader} from '../api';

export type TeamUser = {id: string; username: string; is_admin: boolean; active: boolean; must_change_password?: boolean};
export type TeamState = {enabled: boolean; authenticated: boolean; setup_required?: boolean; user?: TeamUser; workspace_id?: string; role?: string; permissions?: string[]; workspaces?: {id: string; name: string; role: string}[]};
const Context = createContext<TeamState>({enabled: false, authenticated: false});
export const useTeam = () => useContext(Context);
const field = 'block w-full rounded border border-navy-600 bg-navy-800 text-white p-3';
export const teamRequest = <T,>(path: string, method='GET', data?: unknown) => req<T>('/auth'+path, {method, ...(data === undefined ? {} : {body: JSON.stringify(data)})});

function InitialPasswordChange({onChanged}: {onChanged: () => Promise<unknown>}) {
  const [password, setPassword] = useState(''), [confirmation, setConfirmation] = useState(''), [error, setError] = useState('');
  const change = useMutation({mutationFn: () => teamRequest('/password', 'POST', {new_password: password}), onSuccess: async () => {setPassword('');setConfirmation('');await onChanged();}});
  const logout = useMutation({mutationFn: () => teamRequest('/logout', 'POST'), onSuccess: () => window.location.assign('/')});
  return <main className="max-w-md mx-auto p-8 space-y-5">
    <h1 className="text-2xl text-white font-semibold">Change your initial password</h1>
    <p className="text-gray-400">Choose a new password to finish setup. Use at least 14 characters.</p>
    <form className="space-y-4" onSubmit={e => {e.preventDefault();if(password !== confirmation) {setError('Passwords do not match.');return;}setError('');change.mutate();}}>
      <label className="block text-gray-400">New password<input type="password" className={field} autoComplete="new-password" minLength={14} maxLength={256} required value={password} onChange={e => setPassword(e.target.value)} /></label>
      <label className="block text-gray-400">Confirm new password<input type="password" className={field} autoComplete="new-password" minLength={14} maxLength={256} required value={confirmation} onChange={e => setConfirmation(e.target.value)} /></label>
      {(error || change.error) && <p role="alert" className="text-red-400">{error || change.error?.message}</p>}
      <button className="bg-brand-500 text-white rounded p-3" disabled={change.isPending}>Change password and continue</button>
    </form>
    <button className="underline text-gray-400" disabled={logout.isPending} onClick={() => logout.mutate()}>Sign out</button>
  </main>;
}

export function TeamProvider({children}: {children: ReactNode}) {
  const qc = useQueryClient();
  const state = useQuery({queryKey: ['auth'], queryFn: async () => {const s = await teamRequest<TeamState>('/status');setWorkspaceHeader(s.enabled ? s.workspace_id : undefined);return s;}, retry: false});
  const [username, setUsername] = useState(''), [password, setPassword] = useState('');
  const login = useMutation({mutationFn: () => teamRequest('/login','POST',{username, password}), onSuccess: async () => {setPassword('');qc.removeQueries({predicate: q => q.queryKey[0] !== 'auth'});await state.refetch();}});
  useEffect(() => {const expired = () => {qc.removeQueries({predicate: q => q.queryKey[0] !== 'auth'});void state.refetch();};window.addEventListener('auth-expired', expired);return () => window.removeEventListener('auth-expired', expired);}, [qc, state.refetch]);
  if (state.error) return <div className="max-w-lg mx-auto p-8 text-red-400"><p>Unable to check account access: {state.error.message}</p><button className="underline" onClick={() => state.refetch()}>Try again</button></div>;
  if (!state.data) return <p className="p-8 text-gray-400">Checking account access…</p>;
  if (state.data.enabled && !state.data.authenticated) return <main className="max-w-md mx-auto p-8 space-y-5">
    <h1 className="text-2xl text-white font-semibold">Sign in to Upgrade Review</h1><p className="text-gray-400">Pro team edition</p>
    {state.data.setup_required ? <p className="text-amber-400">An installation administrator must create the first account using the local setup command. See the Pro installation guide.</p> : <form onSubmit={e => {e.preventDefault();login.mutate();}} className="space-y-4">
      <label className="block text-gray-400">Username<input className={field} autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} required maxLength={80} /></label>
      <label className="block text-gray-400">Password<input type="password" className={field} autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required maxLength={256} /></label>
      {login.error && <p role="alert" className="text-red-400">{login.error.message}</p>}<button className="bg-brand-500 text-white rounded p-3" disabled={login.isPending}>{login.isPending ? 'Signing in…' : 'Sign in'}</button>
    </form>}
  </main>;
  if (state.data.enabled && state.data.user?.must_change_password) return <InitialPasswordChange onChanged={async () => {qc.removeQueries({predicate: q => q.queryKey[0] !== 'auth'});await state.refetch();}} />;
  return <Context.Provider value={state.data}>{children}</Context.Provider>;
}

export function WorkspaceBar() {
  const team = useTeam();
  const mutation = useMutation({mutationFn: (id: string) => teamRequest('/workspace', 'POST', {workspace_id: id}), onSuccess: () => window.location.assign('/reviews')});
  const logout = useMutation({mutationFn: () => teamRequest('/logout', 'POST'), onSuccess: () => window.location.assign('/')});
  if (!team.enabled) return null;
  return <div className="border-b border-navy-600 px-6 py-3 flex flex-wrap items-center gap-3 text-sm text-gray-300">
    <label className="flex gap-2 items-center">Domain<select aria-label="Administrative domain" className="bg-navy-800 border border-navy-600 rounded p-2" value={team.workspace_id || ''} disabled={mutation.isPending} onChange={e => {if(window.confirm('Switch administrative domain? Unsaved edits in this tab will be lost.')) mutation.mutate(e.target.value);}}><option value="" disabled>Choose workspace</option>{team.workspaces?.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></label>
    <span>{team.user?.username} · {team.role || 'No workspace assigned'}</span>
    <button className="ml-auto underline" disabled={logout.isPending} onClick={() => logout.mutate()}>Sign out</button>
    <p className="w-full text-xs text-gray-300">Your domain is an isolated customer workspace. Its assigned access profile controls available report and review operations. Use Account & access to manage your password and permissions.</p>
    {(mutation.error || logout.error) && <p role="alert" className="text-red-400">{(mutation.error || logout.error)?.message}</p>}
  </div>;
}
