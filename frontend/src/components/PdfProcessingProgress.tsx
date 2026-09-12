import {useEffect, useState} from 'react';
import type {Job} from '../types';
import {activeJob, duration, elapsedSeconds, pdfProgress} from '../utils/jobProgress';
export default function PdfProcessingProgress({job}: {job: Job}) {
  const [now, setNow] = useState(Date.now);
  const active = activeJob(job);
  useEffect(() => {
    setNow(Date.now());
    if (!active) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active, job.id, job.started_at]);
  if (job.source !== 'pdf') return null;
  const {percent, label, file} = pdfProgress(job);
  return <section aria-label="PDF processing progress" className="space-y-2 my-3 text-sm">
    <div className="flex flex-wrap justify-between gap-2">
      <span>{label}</span>
      <span className="font-mono tabular-nums" data-testid="processing-timer">{job.status === 'pending' ? 'Timer starts when processing begins' : `Elapsed ${duration(elapsedSeconds(job, now))}`}</span>
    </div>
    {job.processing_timeout_seconds && <p className="text-xs text-gray-400">This attempt: {job.processing_timeout_seconds / 60}-minute processing limit</p>}
    {file && <p className="text-xs text-gray-400 truncate" title={file}>{file}</p>}
    <div role="progressbar" aria-label="PDF processing" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} aria-valuetext={`${percent}% estimated; ${label}`} className="h-2 rounded-full overflow-hidden" style={{backgroundColor: 'rgb(var(--accent) / 0.15)'}}>
      <div className={`h-full bg-brand-500 rounded-full transition-all duration-700 ${active ? 'animate-pulse' : ''}`} style={{width: `${percent}%`}} />
    </div>
    <p className="text-xs text-gray-400">{percent}%{active ? ' estimated' : ' of processing steps finished'}{job.status === 'partial' || job.status === 'failed' ? ' · Review file errors below.' : ''}</p>
  </section>;
}
