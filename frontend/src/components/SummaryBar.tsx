import { useState, type ReactNode } from 'react';
import {
  AlertTriangle,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleDashed,
  Clock,
  FileStack,
  Layers3,
  ListChecks,
  StickyNote,
} from 'lucide-react';
import type { ExtractionResult, Job } from '../api/client';
import { formatMs, pluralize } from '../utils/format';
import { DocTypeBadge } from './Badges';
import Collapsible from './Collapsible';
import StageTimings from './StageTimings';

interface Props {
  job: Job;
  result: ExtractionResult;
  /** Rendered top-right of the summary (e.g. the export button). */
  actions?: ReactNode;
  defaultCollapsed?: boolean;
}

export default function SummaryBar({ job, result, actions, defaultCollapsed = false }: Props) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const { summary, classification, timings_ms } = result;
  const groupCount = result.groups.length;
  const total = summary.total || 1;
  const pct = (n: number) => `${Math.round((n / total) * 100)}% of ${summary.total}`;

  return (
    <div className={`card-body summary-bar-wrap ${collapsed ? 'is-collapsed' : ''}`} style={{ paddingBottom: collapsed ? 12 : 16 }}>
      <div className="dash-header">
        <div className="dash-title">
          <h2>
            <DocTypeBadge type={result.document_type} />
            <span>{job.case_name || 'Extraction results'}</span>
          </h2>
          <div className="dash-meta">
            <span className="chip"><FileStack size={12} /> {result.page_count} page{result.page_count === 1 ? '' : 's'}</span>
            <span className="chip"><Layers3 size={12} /> {groupCount} {pluralize(result.group_noun, groupCount)}</span>
            <span className="chip"><Brain size={12} /> {result.llm_calls} LLM call{result.llm_calls === 1 ? '' : 's'}</span>
            <span className="chip" title={`OCR ${formatMs(timings_ms.ocr)} · Classify ${formatMs(timings_ms.classifying)} · Extract ${formatMs(timings_ms.extracting)} · Normalize ${formatMs(timings_ms.normalizing)}`}><Clock size={12} /> {formatMs(timings_ms.total)} total</span>
            <span className="sep">·</span>
            <span className="mono" title={job.filenames.join('\n')}>{job.filenames.length} file{job.filenames.length === 1 ? '' : 's'}</span>
            <span className="sep">·</span>
            <span className="mono" title="Job ID">#{job.job_id.slice(0, 8)}</span>
          </div>
        </div>

        <div className="summary-actions-bar">
          {actions}
          <button
            type="button"
            className="btn btn-outline btn-sm overview-toggle-btn"
            onClick={() => setCollapsed((v) => !v)}
            title={collapsed ? 'Expand overview statistics' : 'Fold overview to save vertical space'}
            aria-expanded={!collapsed}
          >
            {collapsed ? (
              <>
                <ChevronDown size={14} /> <span>Overview</span>
              </>
            ) : (
              <>
                <ChevronUp size={14} /> <span>Fold</span>
              </>
            )}
          </button>
        </div>
      </div>

      {collapsed ? (
        /* Compact Overview Strip */
        <div className="collapsed-summary-strip fade-in">
          <span className="chip chip-sm chip-success">
            <CheckCircle2 size={12} /> <strong>{summary.extracted.toLocaleString()}</strong> extracted ({pct(summary.extracted)})
          </span>
          {summary.needs_review > 0 && (
            <span className="chip chip-sm chip-warning">
              <AlertTriangle size={12} /> <strong>{summary.needs_review.toLocaleString()}</strong> needs review
            </span>
          )}
          <span className="chip chip-sm chip-neutral">
            <CircleDashed size={12} /> <strong>{summary.not_found.toLocaleString()}</strong> not found
          </span>
          <span className="chip chip-sm">
            <ListChecks size={12} /> {summary.total.toLocaleString()} total target fields
          </span>
          <span className="chip chip-sm chip-info" title={`OCR: ${formatMs(timings_ms.ocr)} · Classify: ${formatMs(timings_ms.classifying)} · Extract: ${formatMs(timings_ms.extracting)} · Normalize: ${formatMs(timings_ms.normalizing)}`}>
            <Clock size={12} /> <strong>{formatMs(timings_ms.total)}</strong> total (OCR {formatMs(timings_ms.ocr)} · LLM {formatMs(timings_ms.classifying + timings_ms.extracting)})
          </span>
          <span className="chip chip-sm chip-neutral">
            <Brain size={12} /> {classification.document_type}
          </span>
        </div>
      ) : (
        /* Expanded Overview Details */
        <div className="expanded-summary-details fade-in">
          <div className="stat-tiles" role="list">
            <div className="stat-tile brand" role="listitem">
              <span className="stat-label"><ListChecks size={12} /> Target fields</span>
              <span className="stat-value">{summary.total.toLocaleString()}</span>
              <span className="stat-sub">{result.catalog.length} in catalog × groups</span>
            </div>
            <div className="stat-tile success" role="listitem">
              <span className="stat-label"><CheckCircle2 size={12} /> Extracted</span>
              <span className="stat-value">{summary.extracted.toLocaleString()}</span>
              <span className="stat-sub">{pct(summary.extracted)}</span>
            </div>
            <div className="stat-tile warning" role="listitem">
              <span className="stat-label"><AlertTriangle size={12} /> Needs review</span>
              <span className="stat-value">{summary.needs_review.toLocaleString()}</span>
              <span className="stat-sub">{pct(summary.needs_review)}</span>
            </div>
            <div className="stat-tile neutral" role="listitem">
              <span className="stat-label"><CircleDashed size={12} /> Not found</span>
              <span className="stat-value">{summary.not_found.toLocaleString()}</span>
              <span className="stat-sub">{pct(summary.not_found)}</span>
            </div>
            <div className="stat-tile neutral" role="listitem">
              <span className="stat-label"><Clock size={12} /> Pipeline Total</span>
              <span className="stat-value">{formatMs(timings_ms.total)}</span>
              <span className="stat-sub" title={`OCR ${formatMs(timings_ms.ocr)} · classify ${formatMs(timings_ms.classifying)} · extract ${formatMs(timings_ms.extracting)} · normalize ${formatMs(timings_ms.normalizing)}`}>
                OCR {formatMs(timings_ms.ocr)} · LLM {formatMs(timings_ms.classifying + timings_ms.extracting)}
              </span>
            </div>
          </div>

          {/* Pipeline Stage Execution Breakdown */}
          <StageTimings job={job} result={result} defaultOpen={true} />

          <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <Collapsible
              title={
                <span style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}>
                  <Brain size={13} /> Classification: {classification.document_type}
                  {classification.source_hint && <span className="chip chip-xs chip-info">hint: {classification.source_hint}</span>}
                </span>
              }
            >
              <p className="thai" style={{ whiteSpace: 'pre-wrap' }}>{classification.reasoning || 'No reasoning returned.'}</p>
              <p className="small muted" style={{ marginTop: 8 }}>
                {classification.pages.filter((p) => p.is_relevant).length} of {classification.pages.length} pages hydrated into extraction ·{' '}
                {result.shards.length} parallel shard{result.shards.length === 1 ? '' : 's'}
              </p>
            </Collapsible>
            {result.notes.length > 0 && (
              <Collapsible title={<span style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}><StickyNote size={13} /> Pipeline notes ({result.notes.length})</span>}>
                <ul className="notes-list thai">
                  {result.notes.map((n, i) => <li key={i}>{n}</li>)}
                </ul>
              </Collapsible>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
