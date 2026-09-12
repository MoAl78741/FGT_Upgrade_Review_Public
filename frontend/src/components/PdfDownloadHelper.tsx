import { useState } from 'react';
import { ExternalLink, CheckCircle, List } from 'lucide-react';
import { pdfCatalog, pdfReleaseRange } from '../utils/pdfReleaseRange';
import { pdfVersion } from '../utils/pdfSelection';

type Props = {files: File[]; maxFiles?: number};

export default function PdfDownloadHelper({files, maxFiles}: Props) {
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [includeFrom, setIncludeFrom] = useState(false);
  const [results, setResults] = useState<ReturnType<typeof pdfReleaseRange> | null>(null);
  const [error, setError] = useState('');
  const selected = new Set(files.map(f => pdfVersion(f.name)).filter(Boolean));
  function find() {
    try {setResults(pdfReleaseRange(from, to, includeFrom)); setError('');}
    catch(e) {setResults(null); setError((e as Error).message);}
  }
  function reset() {setResults(null); setError('');}
  return <section aria-label="Find release note PDFs" className="mb-6 rounded-xl border border-navy-600 bg-navy-900/40 p-4">
    <h3 className="text-sm font-semibold text-white mb-1">Find the PDFs for your version range</h3>
    <p className="text-xs text-gray-400 mb-4">Choose your current and target versions, then open each release’s page and click <strong>Download PDF</strong>. Add the downloaded files below.</p>
    <div className="flex flex-col sm:flex-row sm:items-end gap-3">
      {([['From version', from, setFrom, '7.6.3'], ['To version', to, setTo, '7.6.6']] as const).map(([label, value, setter, placeholder]) => <label key={label} className="flex-1 text-xs text-gray-400">
        <span className="block mb-1.5">{label}</span>
        <input value={value} list="pdf-release-versions" placeholder={placeholder} maxLength={10} autoComplete="off"
          onChange={e => {setter(e.target.value); reset();}}
          onKeyDown={e => {if(e.key === 'Enter') {e.preventDefault(); find();}}}
          className="w-full bg-navy-900 border border-navy-600 rounded-lg px-3 py-2.5 text-sm text-white font-mono focus:outline-none focus:border-brand-500" />
      </label>)}
      <datalist id="pdf-release-versions">{[...pdfCatalog.releases].reverse().map(r => <option key={r.version} value={r.version} />)}</datalist>
      <button type="button" onClick={find} className="flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 bg-brand-500 hover:bg-brand-600 text-white text-sm font-semibold"><List className="w-4 h-4" />Find PDF links</button>
    </div>
    <label className="flex items-center gap-2 mt-3 text-xs text-gray-400"><input type="checkbox" checked={includeFrom} onChange={e => {setIncludeFrom(e.target.checked); reset();}} />Include the starting version’s PDF</label>
    <p className="text-xs text-gray-500 mt-2">Includes published releases after From through To, across release branches. This is a release-note checklist, not a supported firmware upgrade path.</p>
    {error && <p role="alert" className="mt-3 text-sm text-red-400">{error}</p>}
    {results && <details open className="mt-4 border-t border-navy-600 pt-3">
      <summary className="cursor-pointer text-sm font-semibold text-white">{results.length} PDF links · {results.filter(r => selected.has(r.version)).length} selected for upload</summary>
      {maxFiles && results.length > maxFiles && <p className="text-xs text-amber-400 mt-2">Upload up to {maxFiles} PDFs per job. These {Math.ceil(results.length / maxFiles)} batches will create separate reports.</p>}
      <ol className="mt-3 space-y-2 max-h-80 overflow-y-auto pr-1" aria-label="Release note download links">
        {results.map((r, i) => <li key={r.version} className="flex flex-wrap items-center gap-2 rounded-lg border border-navy-700 bg-navy-800 px-3 py-2">
          <span className="font-mono text-sm text-white">FortiOS {r.version}</span>
          {maxFiles && results.length > maxFiles && <span className="text-xs text-gray-500">Batch {Math.floor(i / maxFiles) + 1}</span>}
          {selected.has(r.version) && <span className="flex items-center gap-1 text-xs text-emerald-500"><CheckCircle className="w-3.5 h-3.5" />Selected</span>}
          <a href={r.url} target="_blank" rel="noopener noreferrer" className="ml-auto inline-flex items-center gap-1 text-sm text-brand-500 hover:underline" aria-label={`Get FortiOS ${r.version} PDF from Fortinet`}>Get PDF <ExternalLink className="w-3.5 h-3.5" /></a>
        </li>)}
      </ol>
    </details>}
    <p className="mt-3 text-xs text-gray-500">Bundled version catalog checked {pdfCatalog.checked_at}. <a className="underline hover:text-brand-500" href={pdfCatalog.source} target="_blank" rel="noopener noreferrer">Fortinet document library</a> · Links require internet access; PDF uploads work offline.</p>
  </section>;
}
