import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, Braces, Download, FileSpreadsheet, FileStack, Grid3X3, Table2, X } from 'lucide-react';
import { errorMessage, exportUrl, getOcr, patchFields, type FieldOverride, type Job, type OcrResponse } from '../api/client';
import FieldsView, { buildRows } from './FieldsView';
import JsonView from './JsonView';
import MatrixView from './MatrixView';
import PagesView from './PagesView';
import SummaryBar from './SummaryBar';

type Tab = 'fields' | 'matrix' | 'pages' | 'json';

interface Props {
  job: Job;
  onJobUpdate: (job: Job) => void;
  onSelectPage?: (page: number) => void;
  showSummary?: boolean;
}

export default function ResultsDashboard({ job, onJobUpdate, onSelectPage, showSummary = true }: Props) {
  const result = job.result;
  const [tab, setTab] = useState<Tab>('fields');
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [ocr, setOcr] = useState<OcrResponse | null>(null);
  const [ocrLoading, setOcrLoading] = useState(false);
  const [ocrError, setOcrError] = useState<string | null>(null);

  // Reset per-job state when a new job arrives.
  useEffect(() => {
    setTab('fields');
    setOcr(null);
    setOcrError(null);
    setOcrLoading(false);
    setSaveError(null);
    setSavingKey(null);
  }, [job.job_id]);

  const loadOcr = useCallback(async () => {
    setOcrLoading(true);
    setOcrError(null);
    try {
      setOcr(await getOcr(job.job_id));
    } catch (e) {
      setOcrError(errorMessage(e));
    } finally {
      setOcrLoading(false);
    }
  }, [job.job_id]);

  const handleOverride = useCallback(
    async (override: FieldOverride, rowKey: string) => {
      setSavingKey(rowKey);
      setSaveError(null);
      try {
        const updated = await patchFields(job.job_id, [override]);
        onJobUpdate(updated);
      } catch (e) {
        setSaveError(`Could not save ${override.field_code}${override.group_key ? ` (${override.group_key})` : ''}: ${errorMessage(e)}`);
      } finally {
        setSavingKey(null);
      }
    },
    [job.job_id, onJobUpdate],
  );

  const rowCount = useMemo(() => (result ? buildRows(result).length : 0), [result]);

  if (!result) return null;

  const matrixLabel = result.document_type === 'CENSUS' ? 'Grid' : 'Matrix';

  return (
    <div className="ui-card fade-in review-panel-card">
      {showSummary && (
        <SummaryBar
          job={job}
          result={result}
          actions={
            <a className="btn btn-primary" href={exportUrl(job.job_id)} download title="Download the business review workbook (reflects your edits)">
              <Download size={16} /> Export Review Template (.xlsx)
            </a>
          }
        />
      )}

      <div className="dash-toolbar">
        <div className="dash-toolbar-left">
          <div className="tab-group" role="tablist" aria-label="Result views">
            <button type="button" role="tab" aria-selected={tab === 'fields'} className={`tab-button ${tab === 'fields' ? 'active' : ''}`} onClick={() => setTab('fields')}>
              <Table2 size={14} /> Fields <span className="tab-count">{rowCount.toLocaleString()}</span>
            </button>
            <button type="button" role="tab" aria-selected={tab === 'matrix'} className={`tab-button ${tab === 'matrix' ? 'active' : ''}`} onClick={() => setTab('matrix')}>
              <Grid3X3 size={14} /> {matrixLabel} <span className="tab-count">{result.groups.length}</span>
            </button>
            <button type="button" role="tab" aria-selected={tab === 'pages'} className={`tab-button ${tab === 'pages' ? 'active' : ''}`} onClick={() => setTab('pages')}>
              <FileStack size={14} /> Pages <span className="tab-count">{result.page_count}</span>
            </button>
            <button type="button" role="tab" aria-selected={tab === 'json'} className={`tab-button ${tab === 'json' ? 'active' : ''}`} onClick={() => setTab('json')}>
              <Braces size={14} /> JSON
            </button>
          </div>

          <a
            className="btn-export-pulse"
            href={exportUrl(job.job_id)}
            download
            title="Download the business review workbook (reflects your edits)"
          >
            <FileSpreadsheet size={15} className="export-pulse-icon" />
            <span>Export Review Template</span>
            <span className="export-pulse-badge">.xlsx</span>
          </a>
        </div>
        <span className="small muted">Edit values inline in the Fields tab · changes are saved to the job and included in the export</span>
      </div>

      {saveError && (
        <div className="banner banner-error" role="alert" style={{ margin: '12px 20px 0', borderRadius: 'var(--radius-sm)' }}>
          <AlertCircle size={15} style={{ flexShrink: 0, marginTop: 1 }} />
          <div className="banner-body">{saveError}</div>
          <button type="button" className="btn-icon" onClick={() => setSaveError(null)} aria-label="Dismiss"><X size={14} /></button>
        </div>
      )}

      <div role="tabpanel">
        {tab === 'fields' && <FieldsView result={result} savingKey={savingKey} onOverride={handleOverride} onSelectPage={onSelectPage} />}
        {tab === 'matrix' && <MatrixView result={result} />}
        {tab === 'pages' && <PagesView result={result} ocr={ocr} loading={ocrLoading} error={ocrError} onLoad={loadOcr} onSelectPage={onSelectPage} />}
        {tab === 'json' && <JsonView result={result} jobId={job.job_id} />}
      </div>
    </div>
  );
}
