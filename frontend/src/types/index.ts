export type JobStatus = "pending" | "running" | "completed" | "failed" | "partial" | "cancelled" | "uploading";

export interface FileOutcome {
  name: string;
  status: string;
  error?: string;
  version?: string;
  page_count?: number | null;
  started_at?: string;
  completed_at?: string;
  elapsed_seconds?: number | null;
  duration_is_partial?: boolean;
  not_processed?: boolean;
  progress?: {phase: string; pages_done: number; total_pages: number};
}

export interface Job {
  title?: string | null;
  id: string;
  from_version: string;
  include_from?: boolean;
  to_version: string;
  status: JobStatus;
  use_selenium: boolean;
  source?: "scrape" | "pdf";
  created_at: string;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
  log?: string;
  expires_at?: string;
  processing_timeout_seconds?: number | null;
  file_outcomes?: FileOutcome[];
  warnings?: string[];
  provenance?: {source?: string; parser_revision?: string; document_revision?: string; section_policy?: string};
}

export interface TableItem {
  "Bug ID": string;
  Description: string;
  markdown?: string;
}

export interface Feature {
  category: string;
  "Feature ID": string;
  Description: string;
  markdown?: string;
}

export interface KnownIssue {
  category: string;
  "Bug ID": string;
  Description: string;
  markdown?: string;
}

export interface Notice {
  version?: string;
  title: string;
  content: string;
  blocks?: RichBlock[];
  markdown?: string;
}

export interface RichBlock {
  type: "heading" | "paragraph" | "list" | "table" | "code";
  level?: number;
  text?: string;
  bold?: boolean;
  items?: string[];
  ordered?: boolean;
  start?: number;
  headers?: string[];
  rows?: string[][];
  rowSpans?: number[][];
  colSpans?: number[][];
  headerColSpans?: number[];
  headerMarkdown?: string[];
  cellMarkdown?: string[][];
  cellBlocks?: RichBlock[][][];
  itemBlocks?: RichBlock[][];
  markdown?: string;
}

export interface RichSection {
  title: string;
  blocks: RichBlock[];
  markdown?: string;
}

export interface VersionData {
  changes_cli?: TableItem[];
  changes_default?: TableItem[];
  changes_tablesize?: TableItem[];
  new_features?: Feature[];
  known_issues?: KnownIssue[];
  _section_urls?: Record<string, string>;
  // Extended sections from full-document scraper (slug keys)
  [slug: string]: TableItem[] | Feature[] | KnownIssue[] | RichSection | Record<string, string> | undefined;
}

export interface JobDetail extends Job {
  localConsolidation?: string[];
  localRelevance?: import("../config/analyze").FeatureProfile;
  versions?: string[];
  all_data?: Record<string, VersionData>;
  special_notices?: Notice[];
}
