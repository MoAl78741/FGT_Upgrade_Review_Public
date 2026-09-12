import type { Job } from '../types';
export const activeJob = (job: Job) => ['pending', 'uploading', 'running'].includes(job.status);
export function elapsedSeconds(job: Job, now: number): number {
  const timestamp = (value: string) => Date.parse(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : value + 'Z');
  const start = timestamp(job.started_at || job.created_at);
  const end = job.completed_at ? timestamp(job.completed_at) : activeJob(job) ? now : start;
  return Number.isFinite(start) && Number.isFinite(end) ? Math.max(0, Math.floor((end - start) / 1000)) : 0;
}
export function duration(seconds: number): string {
  const h = Math.floor(seconds / 3600), m = Math.floor(seconds / 60) % 60, s = seconds % 60;
  return [ ...(h ? [String(h)] : []), String(m).padStart(2, '0'), String(s).padStart(2, '0') ].join(':');
}
export function pdfProgress(job: Job) {
  const files = job.file_outcomes ?? [];
  const done = files.filter(f => ['completed', 'failed', 'cancelled', 'interrupted'].includes(f.status)).length;
  const index = files.findIndex(f => f.status === 'running');
  const current = files[index], progress = current?.progress;
  let fraction = 0, stage = 'Preparing PDF';
  if (progress?.phase === 'reading') {
    fraction = progress.total_pages ? Math.min(1, progress.pages_done / progress.total_pages) * .8 : 0;
    stage = `Reading page ${Math.min(progress.pages_done + 1, progress.total_pages)} of ${progress.total_pages}`;
  } else if (progress?.phase === 'formatting') { fraction = .85; stage = 'Formatting sections and notices'; }
  else if (progress?.phase === 'finalizing') { fraction = .95; stage = 'Finalizing descriptions'; }
  const active = activeJob(job);
  const percent = job.status === 'completed' ? 100 : Math.min(active ? 99 : 100, Math.round((done + (job.status === 'running' ? fraction : 0)) / Math.max(1, files.length) * 100));
  const label = job.status === 'pending' ? 'Waiting for an available worker' : job.status === 'uploading' ? 'Receiving PDFs' : job.status === 'running' && current ? `File ${index + 1} of ${files.length} · ${stage}` : `${done} of ${files.length} files finished`;
  return {percent, label, file: job.status === 'running' ? current?.name : undefined};
}
