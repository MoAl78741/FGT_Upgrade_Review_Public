import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { FEATURES, type FeatureProfile, type FeatureState, relevance } from './analyze';
const Context = createContext<{profile?: FeatureProfile; setProfile: (p?: FeatureProfile) => void}>({setProfile: () => {}});
export const useConfigAnalysis = () => useContext(Context);
export function ConfigProvider({children}: {children: ReactNode}) {
  const [profile, setProfile] = useState<FeatureProfile>();
  useEffect(() => { const clear = () => setProfile(undefined); window.addEventListener('pagehide', clear); return () => window.removeEventListener('pagehide', clear); }, []);
  return <Context.Provider value={{profile, setProfile}}>{children}</Context.Provider>;
}
export function RelevanceBadge({text}: {text: string}) {
  const {profile} = useConfigAnalysis();
  const reasons = relevance(text, profile);
  return reasons.length ? <aside className="relevance-note" aria-label="Potentially relevant"><strong>Potentially relevant</strong><ul>{reasons.map(r => <li key={r}>{r}</li>)}</ul></aside> : null;
}
export default function ConfigAnalysis() {
  const {profile, setProfile} = useConfigAnalysis();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const worker = useRef<Worker>();
  const timeout = useRef<ReturnType<typeof setTimeout>>();
  const generation = useRef(0);
  function clear() { generation.current++; worker.current?.terminate(); clearTimeout(timeout.current); setProfile(undefined); setBusy(false); setError(''); }
  useEffect(() => { const stop = () => { generation.current++; worker.current?.terminate(); clearTimeout(timeout.current); }; window.addEventListener('pagehide', stop); return () => { stop(); window.removeEventListener('pagehide', stop); }; }, []);
  async function read(file?: File) {
    clear();
    if (!file) return;
    if (file.size > 10 * 1024**2) { setError('Configuration exceeds 10 MiB.'); return; }
    setBusy(true);
    const current = generation.current;
    try {
      const text = await file.text();
      if (current !== generation.current) return;
      const w = new Worker(new URL('./analyze.worker.ts', import.meta.url), {type: 'module'});
      worker.current = w;
      const finish = () => { w.terminate(); clearTimeout(timeout.current); setBusy(false); };
      w.onmessage = e => { if (e.data.profile) setProfile(e.data.profile); else setError(e.data.error); finish(); };
      w.onerror = () => { setError('Analysis failed. Use an unencrypted plaintext backup.'); finish(); };
      timeout.current = setTimeout(() => { setError('Analysis timed out.'); finish(); }, 10000);
      w.postMessage(text);
    } catch { setError('Unable to read configuration.'); setBusy(false); }
  }
  return <section className="config-analysis border rounded-lg p-4 space-y-3" aria-label="Local configuration analysis">
    <h2 className="font-semibold">Find notes relevant to your configuration</h2>
    <p className="text-sm">Analysis stays in this browser tab. Configuration and feature results are never uploaded or saved. A detected setting does not prove a feature is running.</p>
    <label className="block text-sm">Choose plaintext FortiOS backup (10 MiB maximum)<input type="file" accept=".conf,.cfg,.txt" onChange={e => { void read(e.target.files?.[0]); e.target.value = ''; }} /></label>
    {busy && <p role="status">Analyzing locally…</p>}{error && <p role="alert">{error}</p>}
    {profile && <><div className="flex flex-wrap gap-3">{FEATURES.map(f => <label key={f}>{f} <select aria-label={`${f} state`} value={profile[f]} onChange={e => setProfile({...profile, [f]: e.target.value as FeatureState})}>{['configured', 'disabled', 'unknown'].map(s => <option key={s}>{s}</option>)}</select></label>)}</div><p className="text-sm">All notes remain visible. Badges explain possible relevance; unknown means insufficient evidence. You can correct these states manually.</p></>}
    <button type="button" onClick={clear} className="underline">Clear local analysis</button>
  </section>;
}
