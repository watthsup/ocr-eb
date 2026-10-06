import type { DocumentType, FieldStatus, FieldValue, GroupNoun } from '../api/client';

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return '—';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(ms < 10_000 ? 2 : 1)} s`;
  const m = Math.floor(ms / 60_000);
  const s = Math.round((ms % 60_000) / 1000);
  return `${m}m ${s.toString().padStart(2, '0')}s`;
}

export function formatValue(value: FieldValue | undefined): string {
  if (value === null || value === undefined || value === '') return '';
  if (typeof value === 'number') return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 4 });
  if (typeof value === 'boolean') return value ? 'Y' : 'N';
  return String(value);
}

/** Value as it should appear in an edit box (no thousands separators). */
export function editableValue(value: FieldValue | undefined): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'boolean') return value ? 'Y' : 'N';
  return String(value);
}

export function isEmptyValue(value: FieldValue | undefined): boolean {
  return value === null || value === undefined || value === '';
}

export function truncate(text: string | null | undefined, max = 60): string {
  if (!text) return '';
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

export const DOC_TYPE_LABEL: Record<DocumentType, string> = {
  BENEFIT_SCHEDULE: 'Benefit Schedule',
  CLAIMS: 'Claims History',
  CENSUS: 'Census',
};

export function docTypeLabel(type: string | null | undefined): string {
  if (!type) return 'Unknown';
  return (DOC_TYPE_LABEL as Record<string, string>)[type] ?? type;
}

export const STATUS_LABEL: Record<FieldStatus, string> = {
  extracted: 'Extracted',
  needs_review: 'Needs Review',
  not_found: 'Not Found / Empty',
};

export function pluralize(noun: GroupNoun | string, n: number): string {
  return n === 1 ? noun : `${noun}s`;
}

export function shortVersion(v: string | null | undefined, len = 7): string {
  if (!v) return '—';
  return v.length > len ? v.slice(0, len) : v;
}

/** Coerce the string typed in an edit box into the wire value for a field type. */
export function coerceInput(text: string, type: string): FieldValue {
  const t = text.trim();
  if (t === '') return null;
  if (type === 'Number') {
    const n = Number(t.replace(/,/g, ''));
    if (Number.isFinite(n)) return n;
  }
  return t;
}
