import type {FileOutcome} from '../types';
import {duration} from './jobProgress';
export function fileTime(file: FileOutcome, running: boolean, now: number): string {
  if (file.not_processed) return 'Not processed';
  if (file.status === 'pending') return 'Waiting to start';
  let seconds = file.elapsed_seconds;
  if (running && file.started_at) {
    const start = Date.parse(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(file.started_at) ? file.started_at : file.started_at + 'Z');
    if (Number.isFinite(start)) seconds = Math.max(seconds ?? 0, (now - start) / 1000);
  }
  if (typeof seconds !== 'number' || !Number.isFinite(seconds)) return 'Time not recorded';
  return `${file.duration_is_partial ? 'At least ' : running ? 'Elapsed ' : ''}${duration(Math.max(0, Math.floor(seconds)))}`;
}
export function filePages(file: FileOutcome): string {
  const pages = file.page_count ?? (file.progress?.total_pages || undefined);
  return typeof pages === 'number' && Number.isInteger(pages) && pages >= 0 ? `${pages} ${pages === 1 ? 'page' : 'pages'}` : 'Page count unavailable';
}
