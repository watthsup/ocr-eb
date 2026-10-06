import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, CircleDashed, Search } from 'lucide-react';
import type { ExtractionResult, FieldOverride, FieldResult, FieldValue } from '../api/client';
import { formatValue, isEmptyValue, pluralize } from '../utils/format';
import { PageChip, StatusBadge, VerificationChip } from './Badges';
import EditableValue from './EditableValue';

const PAGE_SIZE = 100;
const CASE_KEY = '__case__';

export interface FieldRow {
  key: string;
  groupKey: string | null;
  groupLabel: string;
  field: FieldResult;
}

export type FieldFilterMode = 'extracted' | 'review' | 'all' | 'empty';

export function buildRows(result: ExtractionResult): FieldRow[] {
  const rows: FieldRow[] = result.case_fields.map((f) => ({ key: `${CASE_KEY}::${f.field_code}`, groupKey: null, groupLabel: 'Case', field: f }));
  for (const g of result.groups) {
    for (const f of g.fields) {
      rows.push({ key: `${g.group_key}::${f.field_code}`, groupKey: g.group_key, groupLabel: g.group_label || g.group_key, field: f });
    }
  }
  return rows;
}

interface Props {
  result: ExtractionResult;
  savingKey: string | null;
  onOverride: (override: FieldOverride, rowKey: string) => void;
  onSelectPage?: (page: number) => void;
}

export default function FieldsView({ result, savingKey, onOverride, onSelectPage }: Props) {
  const [query, setQuery] = useState('');
  const [group, setGroup] = useState<string>('all');
  const [filterMode, setFilterMode] = useState<FieldFilterMode>('extracted');
  const [page, setPage] = useState(1);

  const rows = useMemo(() => buildRows(result), [result]);

  const extractedCount = useMemo(
    () => rows.filter((r) => r.field.status === 'extracted' || (!isEmptyValue(r.field.value) && r.field.status !== 'not_found')).length,
    [rows],
  );
  const reviewCount = useMemo(() => rows.filter((r) => r.field.status === 'needs_review').length, [rows]);
  const emptyCount = useMemo(() => rows.filter((r) => r.field.status === 'not_found' || isEmptyValue(r.field.value)).length, [rows]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows.filter((r) => {
      if (group === CASE_KEY && r.groupKey !== null) return false;
      if (group !== 'all' && group !== CASE_KEY && r.groupKey !== group) return false;

      // Filter modes: by default show only extracted fields!
      if (filterMode === 'extracted') {
        const hasVal = !isEmptyValue(r.field.value);
        const isExtracted = r.field.status === 'extracted' || (hasVal && r.field.status !== 'not_found');
        if (!isExtracted && r.field.status !== 'needs_review') return false;
      } else if (filterMode === 'review') {
        if (r.field.status !== 'needs_review') return false;
      } else if (filterMode === 'empty') {
        if (!(r.field.status === 'not_found' || isEmptyValue(r.field.value))) return false;
      }

      if (q) {
        const f = r.field;
        const hay = [f.field_code, f.name_en, f.name_th, formatValue(f.value), f.raw_value ?? '', f.evidence ?? '', r.groupLabel].join('\u0001').toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [rows, query, group, filterMode]);

  useEffect(() => setPage(1), [query, group, filterMode, result.document_type]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const visible = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  const commit = (row: FieldRow, value: FieldValue) => {
    onOverride({ group_key: row.groupKey, field_code: row.field.field_code, value }, row.key);
  };

  return (
    <div>
      <div className="toolbar">
        <div className="input-with-icon grow">
          <Search size={14} />
          <input className="input input-sm" placeholder="Search code, name, value, evidence…" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search fields" />
        </div>
        <select className="select input-sm" style={{ width: 'auto', minWidth: 140 }} value={group} onChange={(e) => setGroup(e.target.value)} aria-label="Filter by group">
          <option value="all">All groups</option>
          {result.case_fields.length > 0 && <option value={CASE_KEY}>Case</option>}
          {result.groups.map((g) => (
            <option key={g.group_key} value={g.group_key}>{g.group_label || g.group_key}</option>
          ))}
        </select>

        <div className="filter-pill-group" role="group" aria-label="Field filters">
          <button
            type="button"
            className={`filter-pill ${filterMode === 'extracted' ? 'active' : ''}`}
            onClick={() => setFilterMode('extracted')}
            title="Show only fields that were actually extracted from the document"
          >
            <CheckCircle2 size={13} /> Extracted <span className="tab-count">{extractedCount}</span>
          </button>
          <button
            type="button"
            className={`filter-pill ${filterMode === 'review' ? 'active' : ''}`}
            onClick={() => setFilterMode('review')}
            title="Show fields flagged for human review"
          >
            <AlertTriangle size={13} /> Needs review <span className="tab-count">{reviewCount}</span>
          </button>
          <button
            type="button"
            className={`filter-pill ${filterMode === 'all' ? 'active' : ''}`}
            onClick={() => setFilterMode('all')}
            title="Show all catalog fields from the template"
          >
            All template <span className="tab-count">{rows.length}</span>
          </button>
          <button
            type="button"
            className={`filter-pill ${filterMode === 'empty' ? 'active' : ''}`}
            onClick={() => setFilterMode('empty')}
            title="Show empty / not found fields"
          >
            <CircleDashed size={13} /> Not found <span className="tab-count">{emptyCount}</span>
          </button>
        </div>

        <span className="count">
          {filtered.length.toLocaleString()} {filterMode === 'extracted' ? 'extracted' : ''} rows · {result.groups.length} {pluralize(result.group_noun, result.groups.length)}
        </span>
      </div>

      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ minWidth: 220 }}>Field</th>
              <th>Group</th>
              <th style={{ minWidth: 180 }}>Value</th>
              <th>Evidence</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 && (
              <tr className="row-empty"><td colSpan={5}>No fields match the current filters.</td></tr>
            )}
            {visible.map((r) => {
              const f = r.field;
              const tooltip = [f.evidence ?? '', f.raw_value ? `raw: ${f.raw_value}` : '', f.page !== null ? `page ${f.page}` : ''].filter(Boolean).join('\n');
              return (
                <tr key={r.key}>
                  <td>
                    <div className="field-cell-name">{f.name_en}</div>
                    {f.name_th && <div className="field-cell-th">{f.name_th}</div>}
                    <div className="field-code">{f.field_code} · {f.type}</div>
                  </td>
                  <td>
                    <div className={`group-cell ${r.groupKey === null ? 'case' : ''}`}>
                      {r.groupLabel}
                      {r.groupKey !== null && r.groupKey !== r.groupLabel && <span className="group-key">{r.groupKey}</span>}
                    </div>
                  </td>
                  <td>
                    <EditableValue field={f} saving={savingKey === r.key} disabled={savingKey !== null && savingKey !== r.key} onCommit={(v) => commit(r, v)} />
                  </td>
                  <td className="evidence-cell">
                    <div className="evidence-row">
                      {f.evidence ? <span className="evidence-text" title={tooltip}>{f.evidence}</span> : <span className="muted small">—</span>}
                      <PageChip
                        page={f.page}
                        onClick={f.page !== null && onSelectPage ? () => onSelectPage(f.page!) : undefined}
                      />
                    </div>
                  </td>
                  <td>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, alignItems: 'flex-start' }}>
                      <StatusBadge status={f.status} compact />
                      <VerificationChip verification={f.verification} />
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {pageCount > 1 && (
        <div className="pagination">
          <span>
            Showing {(safePage - 1) * PAGE_SIZE + 1}–{Math.min(safePage * PAGE_SIZE, filtered.length)} of {filtered.length.toLocaleString()}
          </span>
          <div className="pages">
            <button type="button" className="btn btn-outline btn-xs" disabled={safePage <= 1} onClick={() => setPage(safePage - 1)}><ChevronLeft size={13} /> Prev</button>
            <span className="page-num">{safePage} / {pageCount}</span>
            <button type="button" className="btn btn-outline btn-xs" disabled={safePage >= pageCount} onClick={() => setPage(safePage + 1)}>Next <ChevronRight size={13} /></button>
          </div>
        </div>
      )}
    </div>
  );
}
