import {useEffect, useState} from 'react';
import {CheckCircle2, XCircle, Clock, Loader2} from 'lucide-react';
import type {FileOutcome} from '../types';
import {fileTime, filePages} from '../utils/pdfFileMetrics';
const labels: Record<string, string> = {completed: 'Completed', failed: 'Failed', cancelled: 'Cancelled', interrupted: 'Interrupted', pending: 'Queued', running: 'Processing'};
export default function PdfFileList({files, jobStatus}: {files?: FileOutcome[]; jobStatus: string}) {
  const [now, setNow] = useState(Date.now);
  const running = jobStatus === 'running' && !!files?.some(f => f.status === 'running');
  useEffect(() => {
    setNow(Date.now());
    if (!running) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [running]);
  if (!files?.length) return null;
  return <div className="space-y-2 my-3">
    <ul aria-label="PDF documents" className="divide-y divide-navy-600 border border-navy-600 rounded-lg overflow-hidden">
      {files.map((file, index) => {
        const active = file.status === 'running' && jobStatus === 'running';
        const queued = file.status === 'pending' && ['pending', 'running', 'uploading'].includes(jobStatus);
        const status = file.status === 'completed' ? 'Completed' : active ? 'Processing' : queued ? 'Queued' : labels[file.status] === 'Processing' || labels[file.status] === 'Queued' ? 'Not completed' : labels[file.status] || 'Not completed';
        return <li key={index} className="p-3 flex items-start gap-3 text-sm" data-testid="pdf-document">
          {file.status === 'completed' ? <CheckCircle2 aria-label="Completed" className="w-5 h-5 shrink-0 text-emerald-600 mt-0.5"/> : active ? <Loader2 aria-label="Processing" className="w-5 h-5 shrink-0 text-brand-500 animate-spin mt-0.5"/> : queued ? <Clock aria-label="Queued" className="w-5 h-5 shrink-0 text-gray-300 mt-0.5"/> : <XCircle aria-label="Not completed" className="w-5 h-5 shrink-0 text-red-600 mt-0.5"/>}
          <div className="min-w-0 flex-1">
            <p className="font-medium text-white break-words">{file.name}</p>
            <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1 text-gray-300"><span>{status}</span><span>{filePages(file)}</span><span className="font-mono tabular-nums" data-testid="file-duration">{!queued && file.status === 'pending' ? 'Not processed' : fileTime(file, active, now)}</span></div>
            {file.error && <p className="text-red-500 mt-1 break-words">{file.error}</p>}
          </div>
        </li>;
      })}
    </ul>
    <p className="text-xs text-gray-300">Times exclude waiting for other PDFs. Page counts appear when each PDF is opened. Older imports may have no recorded time.</p>
  </div>;
}
