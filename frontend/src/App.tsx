import { useCallback, useEffect, useRef, useState } from 'react';
import { Columns2, Download, FileText, Table2, UploadCloud, X } from 'lucide-react';
import {
  errorMessage,
  exportUrl,
  getCatalog,
  getJob,
  submitDocument,
  type CatalogResponse,
  type DocumentType,
  type Job,
} from './api/client';
import DocumentViewer from './components/DocumentViewer';
import EmptyState from './components/EmptyState';
import ErrorBoundary from './components/ErrorBoundary';
import Header from './components/Header';
import ProgressTracker from './components/ProgressTracker';
import ResultsDashboard from './components/ResultsDashboard';
import DashboardSkeleton from './components/Skeleton';
import SummaryBar from './components/SummaryBar';
import UploadPanel from './components/UploadPanel';
import { DocTypeBadge } from './components/Badges';

const POLL_MS = 1500;
const MAX_POLL_FAILURES = 4;

function isActive(job: Job | null): boolean {
  return !!job && (job.status === 'queued' || job.status === 'processing');
}

type ViewMode = 'split' | 'results' | 'document';

export default function App() {
  const [catalog, setCatalog] = useState<CatalogResponse | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const startedAt = useRef<number | null>(null);
  const pollFailures = useRef(0);

  // Document preview & review state
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([]);
  const [selectedPage, setSelectedPage] = useState(1);
  const [viewMode, setViewMode] = useState<ViewMode>('split');
  const [showUploadModal, setShowUploadModal] = useState(false);

  // Field catalog (for the header chip).
  useEffect(() => {
    getCatalog()
      .then((c) => {
        setCatalog(c);
        setCatalogError(null);
      })
      .catch((e) => setCatalogError(errorMessage(e)));
  }, []);

  // Poll the job while it is queued / processing.
  useEffect(() => {
    if (!isActive(job)) return;
    const id = job!.job_id;
    let cancelled = false;
    const timer = window.setInterval(async () => {
      try {
        const next = await getJob(id);
        if (cancelled) return;
        pollFailures.current = 0;
        setJob(next);
      } catch (e) {
        if (cancelled) return;
        pollFailures.current += 1;
        if (pollFailures.current >= MAX_POLL_FAILURES) {
          setError(`Lost contact with the job: ${errorMessage(e)}`);
          setJob((j) => (j && j.job_id === id ? { ...j, status: 'failed', error: j.error ?? errorMessage(e) } : j));
        }
      }
    }, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [job?.job_id, job?.status]);

  // Wall-clock elapsed ticker for the stepper.
  const running = submitting || isActive(job);
  useEffect(() => {
    if (!running) return;
    const tick = () => startedAt.current !== null && setElapsedMs(Date.now() - startedAt.current);
    tick();
    const t = window.setInterval(tick, 250);
    return () => window.clearInterval(t);
  }, [running]);

  const handleSubmit = useCallback(async (files: File[], docType: DocumentType | '', caseName: string) => {
    setError(null);
    setJob(null);
    setUploadedFiles(files);
    setSelectedPage(1);
    setViewMode('split');
    setShowUploadModal(false);
    setSubmitting(true);
    startedAt.current = Date.now();
    setElapsedMs(0);
    pollFailures.current = 0;
    try {
      const { job_id } = await submitDocument(files, { docType, caseName });
      const first = await getJob(job_id);
      setJob(first);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSubmitting(false);
    }
  }, []);

  const handleJobUpdate = useCallback((next: Job) => setJob(next), []);

  const completed = job?.status === 'completed' && job.result !== null;
  const hasActiveSession = running || completed || uploadedFiles.length > 0 || job !== null;

  return (
    <>
      <Header catalog={catalog} catalogError={catalogError} />
      <main className={`app-container ${hasActiveSession ? 'review-mode' : ''}`}>
        {!hasActiveSession ? (
          /* Initial Welcome State */
          <div className="workspace-grid">
            <div className="left-column">
              <UploadPanel busy={running} onSubmit={handleSubmit} />
            </div>

            <section aria-live="polite">
              <EmptyState />
            </section>
          </div>
        ) : (
          /* Active / Review Workspace with Side-by-Side Comparison */
          <div className="review-workspace fade-in">
            {/* 1. Top Overview Panel (Collapsible to save vertical screen space) */}
            {completed && job && job.result && (
              <div className="ui-card overview-panel-card fade-in" style={{ marginBottom: 16 }}>
                <SummaryBar
                  job={job}
                  result={job.result}
                  defaultCollapsed={false}
                  actions={
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <a
                        className="btn btn-primary btn-sm"
                        href={exportUrl(job.job_id)}
                        download
                        title="Download the business review workbook (reflects your edits)"
                      >
                        <Download size={15} /> Export Review Template (.xlsx)
                      </a>
                      <button
                        type="button"
                        className="btn btn-outline btn-sm"
                        onClick={() => setShowUploadModal(true)}
                        disabled={running}
                        title="Upload another document"
                      >
                        <UploadCloud size={14} /> Upload new
                      </button>
                    </div>
                  }
                />
              </div>
            )}

            {/* 2. Layout Mode Toolbar */}
            <div className="review-workspace-bar">
              <div className="review-bar-left">
                <span className="review-case-badge">
                  {job?.result && <DocTypeBadge type={job.result.document_type} />}
                  <span>{job?.case_name || (uploadedFiles[0]?.name ?? 'Document Review')}</span>
                </span>
                {uploadedFiles.length > 0 ? (
                  <span className="chip chip-xs">
                    {uploadedFiles.length} file{uploadedFiles.length === 1 ? '' : 's'} in viewer
                  </span>
                ) : (
                  <span className="chip chip-xs chip-warning">
                    No document attached to viewer
                  </span>
                )}
                {!completed && (
                  <button
                    type="button"
                    className="btn btn-outline btn-xs"
                    onClick={() => setShowUploadModal(true)}
                    disabled={running}
                    title="Upload another document"
                  >
                    <UploadCloud size={13} /> Upload another
                  </button>
                )}
              </div>

              <div className="review-bar-right">
                <div className="view-toggle-group" role="group" aria-label="Review layout mode">
                  <button
                    type="button"
                    className={`view-toggle-btn ${viewMode === 'split' ? 'active' : ''}`}
                    onClick={() => setViewMode('split')}
                    title="Compare document and review panel side-by-side"
                  >
                    <Columns2 size={14} /> Side-by-Side Review
                  </button>
                  <button
                    type="button"
                    className={`view-toggle-btn ${viewMode === 'results' ? 'active' : ''}`}
                    onClick={() => setViewMode('results')}
                    title="Focus on review panel only"
                  >
                    <Table2 size={14} /> Review Panel Only
                  </button>
                  <button
                    type="button"
                    className={`view-toggle-btn ${viewMode === 'document' ? 'active' : ''}`}
                    onClick={() => setViewMode('document')}
                    title="Focus on original document preview only"
                  >
                    <FileText size={14} /> Document Only
                  </button>
                </div>
              </div>
            </div>

            {/* 3. Anchored Comparison Grid (Document Viewer & Review Panel) */}
            <div className={`review-grid ${viewMode}`}>
              {/* Left Module: Original Document Section */}
              {(viewMode === 'split' || viewMode === 'document') && (
                <section aria-label="Original Document Section" className="review-anchor-pane">
                  <ErrorBoundary resetKey={job?.job_id}>
                    <DocumentViewer
                      files={uploadedFiles}
                      selectedPage={selectedPage}
                      onPageChange={setSelectedPage}
                      title={job?.case_name || job?.filenames[0]}
                      isProcessing={running}
                      onFilesAdded={(newFiles) => setUploadedFiles(newFiles)}
                    />
                  </ErrorBoundary>
                </section>
              )}

              {/* Right Module: Review Panel Section (Anchored beside Document) */}
              {(viewMode === 'split' || viewMode === 'results') && (
                <section aria-live="polite" aria-label="Extraction Review Section" className="review-anchor-pane">
                  <ErrorBoundary resetKey={job?.job_id}>
                    {running && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                        <ProgressTracker job={job} submitting={submitting} elapsedMs={elapsedMs} error={error} />
                        <DashboardSkeleton />
                      </div>
                    )}

                    {completed && job && (
                      <ResultsDashboard
                        job={job}
                        onJobUpdate={handleJobUpdate}
                        onSelectPage={(p) => setSelectedPage(p)}
                        showSummary={false} // Rendered at the top as dedicated collapsible overview!
                      />
                    )}

                    {!running && !completed && job?.status === 'failed' && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                        <ProgressTracker job={job} submitting={submitting} elapsedMs={elapsedMs} error={error} />
                      </div>
                    )}
                  </ErrorBoundary>
                </section>
              )}
            </div>

            {/* Upload Modal Dialog */}
            {showUploadModal && (
              <div className="upload-modal-backdrop" onClick={() => !running && setShowUploadModal(false)}>
                <div className="upload-modal-dialog" onClick={(e) => e.stopPropagation()}>
                  <button
                    type="button"
                    className="btn-icon upload-modal-close"
                    onClick={() => setShowUploadModal(false)}
                    aria-label="Close upload dialog"
                  >
                    <X size={16} />
                  </button>
                  <UploadPanel busy={running} onSubmit={handleSubmit} />
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </>
  );
}
