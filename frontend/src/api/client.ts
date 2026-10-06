/**
 * Typed API client for the Group Insurance IDP backend.
 * Types mirror docs/API_CONTRACT.md exactly.
 */

// ---------- Enumerations ----------
export type DocumentType = 'BENEFIT_SCHEDULE' | 'CLAIMS' | 'CENSUS';
export type JobStatus = 'queued' | 'processing' | 'completed' | 'failed';
export type StageKey = 'uploaded' | 'ocr' | 'classifying' | 'extracting' | 'normalizing' | 'ready';
export type StageStatus = 'pending' | 'running' | 'done' | 'failed' | 'skipped';
export type FieldType = 'Number' | 'Text' | 'Date' | 'Flag' | 'Enum';
export type FieldScope = 'case' | 'group';
export type FieldStatus = 'extracted' | 'not_found' | 'needs_review';
export type GroupNoun = 'Plan' | 'Policy year' | 'Member';
/** `value` may be a number, "80/20", "01/01/2026", "Y" or null. */
export type FieldValue = number | string | boolean | null;

// ---------- Health ----------
export interface HealthLlm {
  provider: string;
  model: string;
  enabled: boolean;
}
export interface HealthCatalog {
  version: string;
  field_count: number;
}
export interface HealthResponse {
  status: string;
  service?: string;
  ocr_engine?: 'azure_document_intelligence' | 'mock' | string;
  llm?: HealthLlm;
  catalog?: HealthCatalog;
}

// ---------- Catalog ----------
export interface FieldSpec {
  field_code: string;
  name_en: string;
  name_th: string;
  keywords: string[];
  type: FieldType;
  granularity: string;
  scope: FieldScope;
  allowed_values: string[] | null;
  validation: string;
  example: string;
  source_document: string;
}
export interface CatalogResponse {
  version: string;
  source: string;
  doc_types: Record<DocumentType, FieldSpec[]>;
}

// ---------- Job / stages ----------
export interface Stage {
  key: StageKey;
  label: string;
  status: StageStatus;
  ms: number | null;
}

export interface PageClassification {
  page: number;
  role: string;
  is_relevant: boolean;
  continues_page: number | null;
  plan_columns: string[];
  topics: string[];
  summary: string;
}
export interface Classification {
  document_type: string;
  reasoning: string;
  source_hint: string | null;
  pages: PageClassification[];
}
export interface Shard {
  shard_id: string;
  label: string;
  page_nos: number[];
  shared_page_nos: number[];
  plan_columns: string[];
}

export type FieldVerification = "in_source" | "not_in_source" | "derived" | "edited" | "not_checked";

export interface FieldResult {
  field_code: string;
  name_en: string;
  name_th: string;
  type: FieldType;
  scope: FieldScope;
  value: FieldValue;
  raw_value: string | null;
  evidence: string | null;
  page: number | null;
  verification?: FieldVerification;
  status: FieldStatus;
  issues: string[];
  edited: boolean;
}
export interface RecordGroup {
  group_key: string;
  group_label: string | null;
  fields: FieldResult[];
}
export interface ResultSummary {
  total: number;
  extracted: number;
  needs_review: number;
  not_found: number;
}
export interface TimingsMs {
  ocr: number;
  classifying: number;
  extracting: number;
  normalizing: number;
  total: number;
}
export interface ExtractionResult {
  document_type: DocumentType;
  page_count: number;
  classification: Classification;
  shards: Shard[];
  group_noun: GroupNoun;
  case_fields: FieldResult[];
  groups: RecordGroup[];
  catalog: FieldSpec[];
  summary: ResultSummary;
  timings_ms: TimingsMs;
  llm_calls: number;
  notes: string[];
}

export interface Job {
  job_id: string;
  case_name: string;
  filenames: string[];
  status: JobStatus;
  error: string | null;
  created_at: string;
  stages: Stage[];
  result: ExtractionResult | null;
}

// ---------- Edits ----------
export interface FieldOverride {
  /** null targets `case_fields` */
  group_key: string | null;
  field_code: string;
  value: FieldValue;
}

// ---------- OCR ----------
export interface OcrPage {
  page_no: number;
  source_file: string;
  markdown: string;
  table_count: number;
}
export interface OcrResponse {
  pages: OcrPage[];
}

// ---------- Errors ----------
export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

async function parseError(res: Response): Promise<ApiError> {
  let detail = `${res.status} ${res.statusText}`;
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === 'string') detail = body.detail;
    else if (body.detail !== undefined) detail = JSON.stringify(body.detail);
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(res.status, detail);
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch (e) {
    throw new ApiError(0, e instanceof Error ? `Network error: ${e.message}` : 'Network error');
  }
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as T;
}

// ---------- Endpoints ----------
export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health');
}

export function getCatalog(): Promise<CatalogResponse> {
  return request<CatalogResponse>('/api/v1/catalog');
}

export interface SubmitOptions {
  docType?: DocumentType | '';
  caseName?: string;
}

export function submitDocument(files: File[], opts: SubmitOptions = {}): Promise<{ job_id: string }> {
  const form = new FormData();
  for (const f of files) form.append('files', f, f.name);
  if (opts.docType) form.append('doc_type', opts.docType);
  if (opts.caseName && opts.caseName.trim()) form.append('case_name', opts.caseName.trim());
  return request<{ job_id: string }>('/api/v1/documents', { method: 'POST', body: form });
}

export function getJob(jobId: string): Promise<Job> {
  return request<Job>(`/api/v1/documents/${encodeURIComponent(jobId)}`);
}

export function patchFields(jobId: string, overrides: FieldOverride[]): Promise<Job> {
  return request<Job>(`/api/v1/documents/${encodeURIComponent(jobId)}/fields`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ overrides }),
  });
}

export function getOcr(jobId: string): Promise<OcrResponse> {
  return request<OcrResponse>(`/api/v1/documents/${encodeURIComponent(jobId)}/ocr`);
}

export function exportUrl(jobId: string): string {
  return `/api/v1/documents/${encodeURIComponent(jobId)}/export`;
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.detail;
  if (e instanceof Error) return e.message;
  return String(e);
}
