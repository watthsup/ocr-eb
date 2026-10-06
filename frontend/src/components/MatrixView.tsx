import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ArrowDown, ArrowUp, ArrowUpDown, Briefcase, CheckCircle2, ChevronLeft, ChevronRight, Grid3X3, PencilLine, Search } from 'lucide-react';
import type { ExtractionResult, FieldResult, FieldSpec, RecordGroup } from '../api/client';
import { formatValue, isEmptyValue, pluralize } from '../utils/format';
import { compareValues } from '../utils/naturalSort';
import { StatusBadge } from './Badges';

type Lookup = Map<string, Map<string, FieldResult>>;

function buildLookup(groups: RecordGroup[]): Lookup {
  const m: Lookup = new Map();
  for (const g of groups) m.set(g.group_key, new Map(g.fields.map((f) => [f.field_code, f])));
  return m;
}

/** Catalog group-scope fields in catalog order; fall back to the first group's fields if the catalog is empty. */
function groupSpecs(result: ExtractionResult): FieldSpec[] {
  const fromCatalog = result.catalog.filter((s) => s.scope === 'group');
  if (fromCatalog.length) return fromCatalog;
  const first = result.groups[0];
  return first ? first.fields.map((f) => ({ field_code: f.field_code, name_en: f.name_en, name_th: f.name_th, keywords: [], type: f.type, granularity: '', scope: 'group', allowed_values: null, validation: '', example: '', source_document: '' })) : [];
}

function CaseFieldsCard({ fields }: { fields: FieldResult[] }) {
  if (!fields.length) return null;
  return (
    <div className="subcard case-card">
      <div className="section-title"><Briefcase size={12} /> Case-level fields ({fields.length})</div>
      <div className="case-grid">
        {fields.map((f) => (
          <div key={f.field_code} className={`case-field ${f.status}`} title={[f.evidence ?? '', f.page !== null ? `page ${f.page}` : ''].filter(Boolean).join('\n')}>
            <div className="ck">
              <span>{f.name_en}</span>
              <span className="mono">{f.field_code}</span>
            </div>
            <div className={`cv ${isEmptyValue(f.value) ? 'empty' : ''}`}>
              {isEmptyValue(f.value) ? 'not found' : formatValue(f.value)}
              {f.edited && <PencilLine size={11} style={{ marginLeft: 5, verticalAlign: 'middle', color: 'var(--status-info-text)' }} />}
            </div>
            <div style={{ marginTop: 5 }}><StatusBadge status={f.status} compact /></div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CellValue({ f }: { f: FieldResult | undefined }) {
  if (!f || f.status === 'not_found' || isEmptyValue(f.value)) {
    return <td className="cell not_found" title={f?.issues?.join('\n') || 'Not found'}>—</td>;
  }
  const tip = [formatValue(f.value), f.evidence ? `“${f.evidence}”` : '', f.page !== null ? `page ${f.page}` : '', ...f.issues].filter(Boolean).join('\n');
  return (
    <td className={`cell ${f.status} ${f.edited ? 'edited' : ''}`} title={tip}>
      {formatValue(f.value)}
      {f.status === 'needs_review' && <span className="cell-flag"><AlertTriangle size={11} /></span>}
    </td>
  );
}

/* ------------------------------------------------------------------ */
/* Benefit schedule / claims: fields as rows, groups as columns          */
/* ------------------------------------------------------------------ */
function ComparisonMatrix({ result }: { result: ExtractionResult }) {
  const specs = useMemo(() => groupSpecs(result), [result]);
  const lookup = useMemo(() => buildLookup(result.groups), [result.groups]);
  const [onlyExtracted, setOnlyExtracted] = useState(true);

  // Filter to rows that actually have at least one extracted value across groups
  const extractedSpecs = useMemo(() => {
    return specs.filter((s) => {
      return result.groups.some((g) => {
        const f = lookup.get(g.group_key)?.get(s.field_code);
        return f && f.status !== 'not_found' && !isEmptyValue(f.value);
      });
    });
  }, [specs, result.groups, lookup]);

  const visibleSpecs = onlyExtracted && extractedSpecs.length > 0 ? extractedSpecs : specs;

  const asPrinted = (code: string): string => {
    for (const g of result.groups) {
      const f = lookup.get(g.group_key)?.get(code);
      if (f?.evidence) return f.evidence;
    }
    return '';
  };

  if (!result.groups.length) {
    return <div className="empty-state" style={{ padding: 40 }}><p>No {pluralize(result.group_noun, 2).toLowerCase()} were extracted for this document.</p></div>;
  }

  return (
    <>
      <CaseFieldsCard fields={result.case_fields} />
      <div className="toolbar" style={{ borderBottom: 'none', paddingBottom: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <span className="section-title" style={{ marginBottom: 0 }}>
            <Grid3X3 size={12} /> {visibleSpecs.length} {onlyExtracted ? 'extracted' : ''} fields × {result.groups.length} {pluralize(result.group_noun, result.groups.length)}
          </span>
          <button
            type="button"
            className={`filter-pill ${onlyExtracted ? 'active' : ''}`}
            onClick={() => setOnlyExtracted((v) => !v)}
            title="Toggle between showing only extracted rows vs all template catalog rows"
          >
            <CheckCircle2 size={13} /> Extracted rows only ({extractedSpecs.length})
          </button>
          {onlyExtracted && extractedSpecs.length < specs.length && (
            <button
              type="button"
              className="btn btn-outline btn-xs"
              onClick={() => setOnlyExtracted(false)}
            >
              Show all {specs.length} template rows
            </button>
          )}
        </div>
        <div className="legend" style={{ marginLeft: 'auto' }}>
          <span><span className="legend-swatch" style={{ background: 'var(--bg-card)' }} /> Extracted</span>
          <span><span className="legend-swatch" style={{ background: 'var(--status-warning-bg)', borderColor: 'var(--status-warning-border)' }} /> Needs review</span>
          <span><span className="legend-swatch" style={{ background: 'var(--bg-subtle)' }} /> — Not found</span>
          <span><span className="legend-swatch" style={{ boxShadow: 'inset 3px 0 0 var(--status-info-text)' }} /> Edited</span>
        </div>
      </div>
      <div className="matrix-wrap">
        <table className="matrix">
          <thead>
            <tr>
              <th className="sticky-col col-field">Field</th>
              <th className="sticky-col col-printed">As printed</th>
              <th className="sticky-col col-code">Field code</th>
              {result.groups.map((g) => (
                <th key={g.group_key} className="group-col" title={g.group_key}>
                  {g.group_label || g.group_key}
                  {g.group_label && g.group_label !== g.group_key && <span className="group-key">{g.group_key}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleSpecs.map((s) => {
              const printed = asPrinted(s.field_code);
              return (
                <tr key={s.field_code}>
                  <td className="sticky-col col-field" title={s.name_th}>
                    <div className="field-en">{s.name_en}</div>
                    <div className="field-type">{s.type}{s.allowed_values ? ` · ${s.allowed_values.join(' | ')}` : ''}</div>
                  </td>
                  <td className="sticky-col col-printed printed" title={printed || s.name_th}>{printed || <span className="muted">{s.name_th || '—'}</span>}</td>
                  <td className="sticky-col col-code code">{s.field_code}</td>
                  {result.groups.map((g) => <CellValue key={g.group_key} f={lookup.get(g.group_key)?.get(s.field_code)} />)}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ */
/* Census: members as rows, fields as columns; sort/search/paginate     */
/* ------------------------------------------------------------------ */
const GROUP_COL = '__group__';
type SortDir = 'asc' | 'desc';

function CensusGrid({ result }: { result: ExtractionResult }) {
  const specs = useMemo(() => groupSpecs(result), [result]);
  const lookup = useMemo(() => buildLookup(result.groups), [result.groups]);
  const [onlyExtractedCols, setOnlyExtractedCols] = useState(true);
  const [query, setQuery] = useState('');
  const [sortKey, setSortKey] = useState<string>(GROUP_COL);
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [pageSize, setPageSize] = useState(50);
  const [page, setPage] = useState(1);

  // Filter to columns that actually have at least one extracted value across members
  const extractedSpecs = useMemo(() => {
    return specs.filter((s) => {
      return result.groups.some((g) => {
        const f = lookup.get(g.group_key)?.get(s.field_code);
        return f && f.status !== 'not_found' && !isEmptyValue(f.value);
      });
    });
  }, [specs, result.groups, lookup]);

  const visibleSpecs = onlyExtractedCols && extractedSpecs.length > 0 ? extractedSpecs : specs;

  useEffect(() => setPage(1), [query, pageSize, sortKey, sortDir, onlyExtractedCols]);

  const cellValue = (g: RecordGroup, code: string) => (code === GROUP_COL ? g.group_label || g.group_key : lookup.get(g.group_key)?.get(code)?.value ?? null);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = result.groups;
    if (q) {
      list = list.filter((g) => {
        if ((g.group_label || g.group_key).toLowerCase().includes(q)) return true;
        return g.fields.some((f) => formatValue(f.value).toLowerCase().includes(q) || (f.evidence ?? '').toLowerCase().includes(q));
      });
    }
    const sorted = [...list].sort((a, b) => compareValues(cellValue(a, sortKey), cellValue(b, sortKey)));
    if (sortDir === 'desc') sorted.reverse();
    return sorted;
  }, [result.groups, lookup, query, sortKey, sortDir]);

  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  const safePage = Math.min(page, pageCount);
  const visible = rows.slice((safePage - 1) * pageSize, safePage * pageSize);

  const toggleSort = (key: string) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else {
      setSortKey(key);
      setSortDir('asc');
    }
  };
  const SortIcon = ({ k }: { k: string }) => (sortKey !== k ? <ArrowUpDown size={11} style={{ opacity: 0.5 }} /> : sortDir === 'asc' ? <ArrowUp size={11} /> : <ArrowDown size={11} />);

  return (
    <>
      <CaseFieldsCard fields={result.case_fields} />
      <div className="toolbar">
        <div className="input-with-icon grow">
          <Search size={14} />
          <input className="input input-sm" placeholder="Search members, values…" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search members" />
        </div>
        <select className="select input-sm" style={{ width: 'auto' }} value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))} aria-label="Rows per page">
          {[25, 50, 100].map((n) => <option key={n} value={n}>{n} / page</option>)}
        </select>
        <button
          type="button"
          className={`filter-pill ${onlyExtractedCols ? 'active' : ''}`}
          onClick={() => setOnlyExtractedCols((v) => !v)}
          title="Toggle between showing only extracted columns vs all catalog columns"
        >
          <CheckCircle2 size={13} /> Extracted columns only ({extractedSpecs.length})
        </button>
        {onlyExtractedCols && extractedSpecs.length < specs.length && (
          <button
            type="button"
            className="btn btn-outline btn-xs"
            onClick={() => setOnlyExtractedCols(false)}
          >
            Show all {specs.length} columns
          </button>
        )}
        <span className="count">{rows.length.toLocaleString()} of {result.groups.length.toLocaleString()} {pluralize(result.group_noun, result.groups.length).toLowerCase()} · {visibleSpecs.length} columns</span>
      </div>
      <div className="matrix-wrap">
        <table className="matrix">
          <thead>
            <tr>
              <th className={`sticky-col col-field sortable ${sortKey === GROUP_COL ? 'sorted' : ''}`} style={{ minWidth: 150, maxWidth: 200 }} onClick={() => toggleSort(GROUP_COL)}>
                <span className="th-inner">{result.group_noun} <SortIcon k={GROUP_COL} /></span>
              </th>
              {visibleSpecs.map((s) => (
                <th key={s.field_code} className={`sortable ${sortKey === s.field_code ? 'sorted' : ''}`} onClick={() => toggleSort(s.field_code)} title={`${s.name_th}\n${s.field_code} · ${s.type}`}>
                  <span className="th-inner">{s.name_en} <SortIcon k={s.field_code} /></span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 && (
              <tr><td colSpan={visibleSpecs.length + 1} style={{ textAlign: 'center', padding: 32, color: 'var(--text-muted)' }}>No members match the search.</td></tr>
            )}
            {visible.map((g) => (
              <tr key={g.group_key}>
                <td className="sticky-col col-field" style={{ minWidth: 150, maxWidth: 200, fontWeight: 600 }} title={g.group_key}>
                  {g.group_label || g.group_key}
                  {g.group_label && g.group_label !== g.group_key && <div className="field-type">{g.group_key}</div>}
                </td>
                {visibleSpecs.map((s) => <CellValue key={s.field_code} f={lookup.get(g.group_key)?.get(s.field_code)} />)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pageCount > 1 && (
        <div className="pagination">
          <span>Showing {(safePage - 1) * pageSize + 1}–{Math.min(safePage * pageSize, rows.length)} of {rows.length.toLocaleString()}</span>
          <div className="pages">
            <button type="button" className="btn btn-outline btn-xs" disabled={safePage <= 1} onClick={() => setPage(safePage - 1)}><ChevronLeft size={13} /> Prev</button>
            <span className="page-num">{safePage} / {pageCount}</span>
            <button type="button" className="btn btn-outline btn-xs" disabled={safePage >= pageCount} onClick={() => setPage(safePage + 1)}>Next <ChevronRight size={13} /></button>
          </div>
        </div>
      )}
    </>
  );
}

export default function MatrixView({ result }: { result: ExtractionResult }) {
  return result.document_type === 'CENSUS' ? <CensusGrid result={result} /> : <ComparisonMatrix result={result} />;
}
