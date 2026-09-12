import { req } from './api';
import type { JobDetail, RichBlock } from './types';
export const decisionLabels = {unreviewed: 'Unreviewed', needs_testing: 'Needs testing', action_required: 'Action required', not_applicable: 'Not applicable', reviewed: 'Reviewed'};
export type DecisionStatus = keyof typeof decisionLabels;
export type Decision = {status: DecisionStatus; note: string; reviewed_by?: string; updated_at?: string};
export type CheckItem = {id: string; phase: 'before' | 'after' | 'rollback'; text: string; done: boolean};
export type ReviewInput = {title: string; customer: string; site: string; prepared_by: string; summary: string; rollback_notes: string; expected_versions: string[]; range_from?: string | null; range_to?: string | null; range_include_from?: boolean | null};
export type Review = ReviewInput & {id: string; revision: number; created_at: string; updated_at: string; expires_at?: string; job_ids: string[]; decisions: Record<string, Decision>; checklist: CheckItem[]};
export type Finding = {reference?: {kind: 'pdf' | 'web'; url: string; page?: number; precision: 'section' | 'document'; name?: string} | null; id: string; job_id: string; version: string; section: string; source: {content?: string; blocks?: RichBlock[]; Description?: string; description?: string; markdown?: string; category?: string; title?: string; 'Bug ID'?: string; 'Feature ID'?: string}};
export type ReviewDetail = Review & {jobs: JobDetail[]; findings: Finding[]; missing_versions: string[]; unavailable_job_ids: string[]};
const json = (method: string, data: unknown) => ({method, body: JSON.stringify(data)});
export const reviews = {
  list: () => req<Review[]>('/reviews'),
  get: (id: string) => req<ReviewDetail>(`/reviews/${id}`),
  create: (title: string) => req<ReviewDetail>('/reviews', json('POST', {title})),
  edit: (id: string, data: ReviewInput & {revision: number}) => req<ReviewDetail>(`/reviews/${id}`, json('PUT', data)),
  link: (id: string, job_id: string, revision: number) => req<ReviewDetail>(`/reviews/${id}/jobs`, json('POST', {job_id, revision})),
  unlink: (id: string, job: string, revision: number) => req<ReviewDetail>(`/reviews/${id}/jobs/${job}?revision=${revision}`, {method: 'DELETE'}),
  decide: (id: string, finding: string, data: Decision & {revision: number}) => req<Review>(`/reviews/${id}/decisions/${finding}`, json('PUT', data)),
  checklist: (id: string, items: CheckItem[], revision: number) => req<Review>(`/reviews/${id}/checklist`, json('PUT', {items, revision})),
  duplicate: (id: string) => req<ReviewDetail>(`/reviews/${id}/duplicate`, {method: 'POST'}),
  delete: (id: string) => req<void>(`/reviews/${id}`, {method: 'DELETE'}),
};
