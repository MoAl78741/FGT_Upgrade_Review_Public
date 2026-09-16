import {pdfTimeoutHeaders} from "./utils/processingPreferences";
import type { Job, JobDetail } from "./types";

const BASE = "/api";
let workspaceId: string | undefined;
export function setWorkspaceHeader(value?: string) { workspaceId = value; }
const workspaceHeaders = (): Record<string, string> => workspaceId ? {"X-Workspace-ID": workspaceId} : {};

type Capabilities = {edition_label: string; pro_upgrade_url: string | null; version: string; build_number: string; build_revision: string; source_code_url: string; edition: string; scraping: boolean; selenium: boolean; retention_hours: number | null; max_files: number; max_file_bytes: number; max_total_bytes: number; max_pages: number; timeout_minutes: number; workers: number};
let ready: Promise<Capabilities> | undefined;
function bootstrap(): Promise<Capabilities> {
  if (!ready) {
    const start = () => req<Capabilities>('/capabilities');
    ready = (async () => globalThis.navigator?.locks ? await navigator.locks.request('fgt-session-bootstrap', start) : await start())().catch(error => { ready = undefined; throw error; });
  }
  return ready;
}

export async function req<T>(path: string, init?: RequestInit): Promise<T> {
  if (path !== '/capabilities') await bootstrap();
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...workspaceHeaders() },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    if (res.status === 401) window.dispatchEvent(new Event("auth-expired"));
    throw new Error(typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? `HTTP ${res.status}`));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  capabilities: async () => {await bootstrap();return req<Capabilities>('/capabilities');},
  cancelJob: (id: string) => req<Job>(`/jobs/${id}/cancel`, {method: "POST"}),
  retryJob: (id: string) => req<Job>(`/jobs/${id}/retry`, {method: "POST", headers: {"Content-Type": "application/json", ...workspaceHeaders(), ...pdfTimeoutHeaders()}}),
  listJobs: () => req<Job[]>("/jobs"),

  getJob: (id: string) => req<JobDetail>(`/jobs/${id}`),

  createJob: (from_version: string, to_version: string, use_selenium: boolean, grid_url?: string, force_rescrape?: boolean, include_from: boolean = false) =>
    req<Job>("/jobs", {
      method: "POST",
      body: JSON.stringify({ from_version, to_version, use_selenium, include_from, force_rescrape: force_rescrape ?? false }),
    }),

  uploadPdfs: async (files: File[]): Promise<Job> => {
    await bootstrap();
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    const res = await fetch(`${BASE}/jobs/upload`, { method: "POST", body: fd, headers: {...workspaceHeaders(), ...pdfTimeoutHeaders()} });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      if (res.status === 401) window.dispatchEvent(new Event("auth-expired"));
    throw new Error(typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? `HTTP ${res.status}`));
    }
    return res.json();
  },

  deleteJob: (id: string) => req<void>(`/jobs/${id}`, { method: "DELETE" }),
};
