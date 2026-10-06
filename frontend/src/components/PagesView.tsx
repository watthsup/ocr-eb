import { useEffect, useMemo } from 'react';
import { AlertCircle, CheckCircle2, Columns3, Eye, EyeOff, FileText, GitBranch, Link2, Loader2, RefreshCw, Table2, Tags } from 'lucide-react';
import type { ExtractionResult, OcrPage, OcrResponse, PageClassification } from '../api/client';
import Collapsible from './Collapsible';

interface Props {
  result: ExtractionResult;
  ocr: OcrResponse | null;
  loading: boolean;
  error: string | null;
  onLoad: () => void;
  onSelectPage?: (page: number) => void;
}

interface MergedPage {
  page: number;
  cls: PageClassification | undefined;
  ocr: OcrPage | undefined;
}

export default function PagesView({ result, ocr, loading, error, onLoad, onSelectPage }: Props) {
  useEffect(() => {
    if (!ocr && !loading && !error) onLoad();
  }, [ocr, loading, error, onLoad]);

  const pages = useMemo<MergedPage[]>(() => {
    const nos = new Set<number>();
    result.classification.pages.forEach((p) => nos.add(p.page));
    ocr?.pages.forEach((p) => nos.add(p.page_no));
    return [...nos].sort((a, b) => a - b).map((n) => ({
      page: n,
      cls: result.classification.pages.find((p) => p.page === n),
      ocr: ocr?.pages.find((p) => p.page_no === n),
    }));
  }, [result.classification.pages, ocr]);

  return (
    <div className="pages-list">
      {result.shards.length > 0 && (
        <div className="subcard">
          <div className="section-title"><GitBranch size={12} /> Extraction shards ({result.shards.length} parallel call{result.shards.length === 1 ? '' : 's'})</div>
          <div className="shard-grid">
            {result.shards.map((s) => (
              <div key={s.shard_id} className="shard-card">
                <div className="shard-title">
                  <Columns3 size={13} color="#C41230" /> {s.label}
                  <span className="shard-id">{s.shard_id}</span>
                </div>
                <div className="kv-row">
                  <span className="k">Pages</span>
                  <span className="v">{s.page_nos.map((p) => <span key={p} className="page-chip">p.{p}</span>)}</span>
                </div>
                {s.shared_page_nos.length > 0 && (
                  <div className="kv-row">
                    <span className="k">Shared</span>
                    <span className="v">{s.shared_page_nos.map((p) => <span key={p} className="page-chip" title="Context page shared across shards">p.{p}</span>)}</span>
                  </div>
                )}
                {s.plan_columns.length > 0 && (
                  <div className="kv-row">
                    <span className="k">Columns</span>
                    <span className="v">{s.plan_columns.map((c) => <span key={c} className="chip chip-xs chip-red thai">{c}</span>)}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="section-title" style={{ marginBottom: 0 }}>
        <FileText size={12} /> Pages ({pages.length})
        {loading && <span className="chip chip-xs"><Loader2 size={11} className="spin" /> loading OCR text…</span>}
        {ocr && <span className="chip chip-xs chip-success"><CheckCircle2 size={11} /> OCR text loaded</span>}
      </div>

      {error && (
        <div className="banner banner-error" role="alert">
          <AlertCircle size={15} />
          <div className="banner-body">
            <strong>Could not load raw OCR</strong>
            {error}
          </div>
          <button type="button" className="btn btn-outline btn-xs" onClick={onLoad}><RefreshCw size={12} /> Retry</button>
        </div>
      )}

      {pages.length === 0 && !loading && <p className="muted small">No page metadata available.</p>}

      {pages.map(({ page, cls, ocr: op }) => (
        <div key={page} className={`page-card ${cls && !cls.is_relevant ? 'dropped' : ''}`}>
          <div className="page-card-head">
            <span className="page-no"><FileText size={14} color="#C41230" /> Page {page}</span>
            {cls && <span className="chip chip-info">{cls.role}</span>}
            {cls && (cls.is_relevant ? (
              <span className="badge badge-success"><CheckCircle2 size={11} /> Hydrated</span>
            ) : (
              <span className="badge badge-neutral"><EyeOff size={11} /> Dropped</span>
            ))}
            {cls?.continues_page !== null && cls?.continues_page !== undefined && (
              <span className="chip chip-xs chip-warning" title="Continuation of an earlier page"><Link2 size={11} /> continues p.{cls.continues_page}</span>
            )}
            {op && <span className="chip chip-xs" title="Tables detected by layout analysis"><Table2 size={11} /> {op.table_count} table{op.table_count === 1 ? '' : 's'}</span>}
            {op && <span className="src" title={op.source_file}>{op.source_file}</span>}
            {onSelectPage && (
              <button
                type="button"
                className="btn btn-outline btn-xs"
                style={{ marginLeft: 'auto' }}
                onClick={() => onSelectPage(page)}
                title={`View page ${page} in document preview`}
              >
                <Eye size={12} /> View Document
              </button>
            )}
          </div>
          <div className="page-card-body">
            {cls?.plan_columns && cls.plan_columns.length > 0 && (
              <div className="kv-row">
                <span className="k"><Columns3 size={10} style={{ verticalAlign: -1 }} /> Plan cols</span>
                <span className="v">{cls.plan_columns.map((c) => <span key={c} className="chip chip-xs chip-red thai">{c}</span>)}</span>
              </div>
            )}
            {cls?.topics && cls.topics.length > 0 && (
              <div className="kv-row">
                <span className="k"><Tags size={10} style={{ verticalAlign: -1 }} /> Topics</span>
                <span className="v">{cls.topics.map((t) => <span key={t} className="chip chip-xs thai">{t}</span>)}</span>
              </div>
            )}
            {cls?.summary && <p className="page-summary">{cls.summary}</p>}
            {op ? (
              <Collapsible title={`Raw OCR markdown · ${op.markdown.length.toLocaleString()} chars`}>
                <pre className="ocr-pre">{op.markdown || '(empty)'}</pre>
              </Collapsible>
            ) : loading ? (
              <div className="skeleton" style={{ height: 34 }} />
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}
